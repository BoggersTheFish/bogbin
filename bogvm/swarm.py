from __future__ import annotations

import hashlib
from typing import Any

from .genesis import Genesis
from .signing import canonical_bytes


class BogPilotSwarm:
    """Deterministic candidate tournament. Pilot proposes; Genesis admits."""

    def __init__(self, workspace: Any) -> None:
        self.genesis = Genesis(workspace)

    def tournament(self, hypothesis: str, candidates: list[dict], budget: dict | None = None) -> dict:
        budget = {"cells": 32, "cost": 10_000, "memory": 64 * 1024 * 1024, **(budget or {})}
        cells, total_cost = [], 0
        for index, proposal in enumerate(candidates[: budget["cells"]], 1):
            cost = int(proposal.get("cost", 1))
            total_cost += cost
            failures = []
            action = proposal.get("action")
            if action not in {"write", "reject"}:
                failures.append({"path": str(action), "reason": "candidate action is outside verifier surface"})
            if cost < 0 or total_cost > budget["cost"]:
                failures.append({"path": str(index), "reason": "candidate exceeds swarm cost budget"})
            if int(proposal.get("memory", 0)) > budget["memory"]:
                failures.append({"path": str(index), "reason": "candidate exceeds swarm memory budget"})
            if action == "write" and (not proposal.get("path") or ".." in proposal["path"].split("/")):
                failures.append({"path": str(proposal.get("path")), "reason": "candidate write path is unsafe"})
            score = int(proposal.get("score", 0))
            proof = {"index": index, "proposal": proposal, "score": score, "cost": cost, "failures": failures}
            cells.append({
                "format": "BOGCELL-hypothesis-receipt-12.0",
                **proof,
                "proof_sha256": _stable_hash(proof),
                "execution_status": "completed" if not failures else "blocked",
            })
        eligible = [cell for cell in cells if cell["execution_status"] == "completed" and cell["proposal"]["action"] != "reject"]
        eligible.sort(key=lambda cell: (-cell["score"], cell["cost"], cell["proof_sha256"]))
        selected = eligible[0] if eligible else None
        admission = None
        if selected:
            proposal = selected["proposal"]
            admission = self.genesis.fs_write(proposal["path"], proposal.get("data", ""), capability="BogPilotSwarm")
        receipt = {
            "format": "BOGPILOT-swarm-receipt-12.0",
            "hypothesis_sha256": hashlib.sha256(hypothesis.encode()).hexdigest(),
            "budget": budget,
            "hypothesis_tree": cells,
            "selected_proof_sha256": selected["proof_sha256"] if selected else None,
            "admission": admission,
            "pilot_had_direct_authority": False,
            "verifier_selected_best_path": selected is not None,
            "execution_status": "completed" if selected and admission["execution_status"] == "completed" else "blocked",
        }
        return self.genesis.record("pilot-swarm", receipt)

    @staticmethod
    def replay(receipt: dict) -> dict:
        failures = []
        cells = receipt.get("hypothesis_tree", [])
        for cell in cells:
            proof = {key: cell[key] for key in ("index", "proposal", "score", "cost", "failures")}
            if cell.get("proof_sha256") != _stable_hash(proof):
                failures.append({"path": str(cell.get("index")), "reason": "swarm cell proof mismatch"})
        eligible = [cell for cell in cells if cell.get("execution_status") == "completed" and cell.get("proposal", {}).get("action") != "reject"]
        eligible.sort(key=lambda cell: (-cell["score"], cell["cost"], cell["proof_sha256"]))
        expected = eligible[0]["proof_sha256"] if eligible else None
        if expected != receipt.get("selected_proof_sha256"):
            failures.append({"path": "selection", "reason": "swarm best-path selection mismatch"})
        return {
            "format": "BOGPILOT-swarm-replay-receipt-12.0",
            "swarm_replay_verified": not failures,
            "failures": failures,
            "execution_status": "completed" if not failures else "blocked",
        }


def _stable_hash(obj: Any) -> str:
    return hashlib.sha256(canonical_bytes(obj)).hexdigest()
