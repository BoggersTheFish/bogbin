from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
from typing import Any

from .genesis import Genesis
from .signing import canonical_bytes, public_key_info, sign_object, verify_object_signature


CLAIM_FORMAT = "BOGMESH-signed-claim-11.0"


class BogMesh:
    """Local-first signed claim exchange with deterministic conflict policies."""

    def __init__(self, workspace: Any) -> None:
        self.workspace = workspace
        self.genesis = Genesis(workspace)
        self.dir = workspace.bogos / "mesh"
        self.claims_dir = self.dir / "claims"
        self.peers_dir = self.dir / "peers"
        self.state_path = self.dir / "state.json"
        self.claims_dir.mkdir(parents=True, exist_ok=True)
        self.peers_dir.mkdir(parents=True, exist_ok=True)

    def trust_peer(self, public_key: str | Path) -> dict:
        source = Path(public_key)
        info = public_key_info(source)
        target = self.peers_dir / f"{info['key_id']}.pub"
        shutil.copy2(source, target)
        return {"format": "BOGMESH-peer-trust-receipt-11.0", "key_id": info["key_id"], "execution_status": "completed"}

    def propose(
        self,
        namespace: str,
        value: Any,
        *,
        context: dict | None = None,
        authority: int = 0,
        support: int = 1,
        capability_scope: list[str] | None = None,
    ) -> dict:
        unsigned = {
            "format": CLAIM_FORMAT,
            "namespace": namespace,
            "value": value,
            "context": context or {},
            "authority": authority,
            "support": support,
            "capability_scope": sorted(set(capability_scope or [])),
            "proposer_key_id": public_key_info(self.genesis.trusted_keys[0])["key_id"],
        }
        claim_id = _stable_hash(unsigned)
        claim = {**unsigned, "claim_id": claim_id, "signature": sign_object({**unsigned, "claim_id": claim_id}, self.genesis.private_key)}
        _write_json(self.claims_dir / f"{claim_id}.json", claim)
        return self.resolve(namespace)

    def import_claim(self, path: str | Path) -> dict:
        source = Path(path)
        claim = json.loads(source.read_text())
        failures = self._verify_claim(claim)
        if not failures:
            _write_json(self.claims_dir / f"{claim['claim_id']}.json", claim)
        return {
            "format": "BOGMESH-import-receipt-11.0",
            "claim_id": claim.get("claim_id"),
            "failures": failures,
            "execution_status": "completed" if not failures else "blocked",
        }

    def resolve(self, namespace: str) -> dict:
        valid, quarantined = [], []
        for path in sorted(self.claims_dir.glob("*.json")):
            claim = json.loads(path.read_text())
            if claim.get("namespace") != namespace:
                continue
            failures = self._verify_claim(claim)
            (quarantined if failures else valid).append({"claim": claim, "failures": failures})
        groups: dict[str, list[dict]] = {}
        for item in valid:
            context_key = json.dumps(item["claim"]["context"], sort_keys=True, separators=(",", ":"))
            groups.setdefault(context_key, []).append(item["claim"])
        outcomes = []
        for context_key, claims in sorted(groups.items()):
            by_value: dict[str, list[dict]] = {}
            for claim in claims:
                by_value.setdefault(_stable_hash({"value": claim["value"]}), []).append(claim)
            ranked = []
            for value_hash, supporters in by_value.items():
                ranked.append({
                    "value_hash": value_hash,
                    "value": supporters[0]["value"],
                    "pressure": sum(item["support"] for item in supporters),
                    "authority": max(item["authority"] for item in supporters),
                    "claims": sorted(item["claim_id"] for item in supporters),
                })
            ranked.sort(key=lambda item: (-item["authority"], -item["pressure"], item["value_hash"]))
            if len(ranked) == 1:
                policy = "converge"
                selected = ranked[0]
            elif ranked[0]["authority"] > ranked[1]["authority"] or ranked[0]["pressure"] > ranked[1]["pressure"]:
                policy = "winner"
                selected = ranked[0]
            else:
                policy = "split"
                selected = None
            outcomes.append({"context": json.loads(context_key), "policy": policy, "selected": selected, "candidates": ranked})
        state = {
            "format": "BOGMESH-state-11.0",
            "namespace": namespace,
            "outcomes": outcomes,
            "quarantined_claims": [item["claim"].get("claim_id") for item in quarantined],
        }
        state["state_root_sha256"] = _stable_hash(state)
        _write_json(self.state_path, state)
        receipt = {
            **state,
            "format": "BOGMESH-conflict-receipt-11.0",
            "conflict_detected": any(len(outcome["candidates"]) > 1 for outcome in outcomes),
            "context_split": any(outcome["policy"] == "split" for outcome in outcomes) or len(outcomes) > 1,
            "execution_status": "completed",
        }
        return self.genesis.record("mesh-resolve", receipt)

    def verify(self) -> dict:
        failures = []
        for path in sorted(self.claims_dir.glob("*.json")):
            failures.extend({"path": str(path), "reason": item["reason"]} for item in self._verify_claim(json.loads(path.read_text())))
        if self.state_path.is_file():
            state = json.loads(self.state_path.read_text())
            root = state.pop("state_root_sha256", None)
            if root != _stable_hash(state):
                failures.append({"path": str(self.state_path), "reason": "mesh state root mismatch"})
        return {
            "format": "BOGMESH-verification-receipt-11.0",
            "mesh_verified": not failures,
            "failures": failures,
            "execution_status": "completed" if not failures else "blocked",
        }

    def _verify_claim(self, claim: dict) -> list[dict]:
        failures = []
        unsigned = dict(claim)
        signature = unsigned.pop("signature", {})
        claim_id = unsigned.get("claim_id")
        material = dict(unsigned)
        material.pop("claim_id", None)
        if claim.get("format") != CLAIM_FORMAT or claim_id != _stable_hash(material):
            failures.append({"path": str(claim_id), "reason": "mesh claim format or hash mismatch"})
        trusted = self.genesis.trusted_keys + sorted(self.peers_dir.glob("*.pub"))
        if not verify_object_signature(unsigned, signature, trusted)["verified"]:
            failures.append({"path": str(claim_id), "reason": "mesh claim signature is not trusted"})
        if not isinstance(claim.get("support"), int) or claim.get("support", 0) < 1:
            failures.append({"path": str(claim_id), "reason": "mesh support must be a positive integer"})
        if not claim.get("capability_scope"):
            failures.append({"path": str(claim_id), "reason": "mesh claim has no capability scope"})
        return failures


def _stable_hash(obj: Any) -> str:
    return hashlib.sha256(canonical_bytes(obj)).hexdigest()


def _write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")
