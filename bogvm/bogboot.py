from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .genesis import Genesis
from .signing import canonical_bytes


BOOT_FORMAT = "BOGBOOT-receipt-13.0"
IRQ_FORMAT = "BOGIRQ-claim-receipt-14.0"
HARDWARE_STATE_FORMAT = "BOGHW-state-14.0"


DEFAULT_MANIFEST = {
    "format": "BOGHW-device-manifest-14.0",
    "platform": "qemu-virt-reference",
    "devices": {
        "serial": {"capability": "hardware.serial.input", "irq": 4},
        "timer": {"capability": "hardware.timer.tick", "irq": 0},
        "keyboard": {"capability": "hardware.keyboard.input", "irq": 1},
        "block_device": {"capability": "hardware.block.read", "irq": 14},
        "framebuffer": {"capability": "hardware.framebuffer.event", "irq": None},
    },
    "memory_map": [
        {"name": "boot", "start": 0x00100000, "size": 0x00010000, "kind": "reserved"},
        {"name": "bogk", "start": 0x00110000, "size": 0x00090000, "kind": "reserved"},
        {"name": "available", "start": 0x00200000, "size": 0x03E00000, "kind": "available"},
    ],
}


class BogBootError(Exception):
    pass


class BogBoot:
    """QEMU-only verified boot and device-boundary event reference contract."""

    def __init__(self, workspace: Any) -> None:
        self.workspace = workspace
        self.genesis = Genesis(workspace)
        self.dir = workspace.bogos / "bogboot"
        self.manifest_path = self.dir / "device_manifest.json"
        self.state_path = self.dir / "hardware_state.json"
        self.claims_dir = self.dir / "irq_claims"
        self.quarantine_dir = self.dir / "quarantine"
        for path in (self.dir, self.claims_dir, self.quarantine_dir):
            path.mkdir(parents=True, exist_ok=True)

    def boot(self, manifest: dict | None = None) -> dict:
        manifest = json.loads(json.dumps(manifest or DEFAULT_MANIFEST))
        failures = self._validate_manifest(manifest)
        manifest_sha256 = _stable_hash(manifest)
        state = {
            "format": HARDWARE_STATE_FORMAT,
            "platform": manifest.get("platform"),
            "manifest_sha256": manifest_sha256,
            "tick": 0,
            "claim_sequence": 0,
            "accepted_claims": [],
            "quarantined_claims": [],
            "devices": {name: {"event_count": 0, "last_payload_sha256": None} for name in sorted(manifest.get("devices", {}))},
        }
        state["state_root_sha256"] = self._state_root(state)
        if not failures:
            _write_json(self.manifest_path, manifest)
            _write_json(self.state_path, state)
        receipt = {
            "format": BOOT_FORMAT,
            "target": "qemu-virt-reference",
            "platform": manifest.get("platform"),
            "initialized_devices": sorted(manifest.get("devices", {})),
            "memory_map": manifest.get("memory_map", []),
            "device_manifest_sha256": manifest_sha256,
            "hardware_state_root_sha256": state["state_root_sha256"] if not failures else None,
            "bogk_entrypoint": "verified-event-loop",
            "physical_hardware_claimed": False,
            "failures": failures,
            "execution_status": "completed" if not failures else "blocked",
        }
        return self.genesis.record("bogboot", receipt)

    def irq_claim(
        self,
        source: str,
        raw_payload: bytes | str,
        decoded_event: Any,
        capabilities: list[str],
        timestamp_tick: int | None = None,
    ) -> dict:
        state, manifest = self._load()
        device = manifest["devices"].get(source)
        tick = state["tick"] + 1 if timestamp_tick is None else timestamp_tick
        payload = raw_payload.encode() if isinstance(raw_payload, str) else bytes(raw_payload)
        before = state["state_root_sha256"]
        failures = []
        required = device.get("capability") if device else None
        if device is None:
            failures.append({"path": source, "reason": "device is not declared by hardware manifest"})
        if required not in capabilities:
            failures.append({"path": source, "reason": f"missing hardware capability: {required}"})
        if not isinstance(tick, int) or tick <= state["tick"]:
            failures.append({"path": str(tick), "reason": "hardware tick must increase monotonically"})

        claim_core = {
            "source": source,
            "timestamp_tick": tick,
            "raw_payload_sha256": hashlib.sha256(payload).hexdigest(),
            "decoded_event": decoded_event,
            "capability_required": required,
            "capabilities_presented": sorted(set(capabilities)),
            "state_root_before": before,
        }
        claim_id = _stable_hash(claim_core)
        state["claim_sequence"] += 1
        if failures:
            state["quarantined_claims"].append(claim_id)
        else:
            state["tick"] = tick
            state["accepted_claims"].append(claim_id)
            state["devices"][source]["event_count"] += 1
            state["devices"][source]["last_payload_sha256"] = claim_core["raw_payload_sha256"]
        state["state_root_sha256"] = self._state_root(state)
        _write_json(self.state_path, state)
        receipt = {
            "format": IRQ_FORMAT,
            "claim_id": claim_id,
            **claim_core,
            "accepted": not failures,
            "state_root_after": state["state_root_sha256"],
            "failures": failures,
            "execution_status": "completed" if not failures else "blocked",
        }
        target = self.claims_dir if not failures else self.quarantine_dir
        _write_json(target / f"{state['claim_sequence']:06d}_{claim_id}.json", receipt)
        return self.genesis.record("bogirq", receipt)

    def verify(self) -> dict:
        failures = []
        try:
            state, manifest = self._load()
            failures.extend(self._validate_manifest(manifest))
            if state.get("manifest_sha256") != _stable_hash(manifest):
                failures.append({"path": str(self.manifest_path), "reason": "hardware manifest hash mismatch"})
            if state.get("state_root_sha256") != self._state_root(state):
                failures.append({"path": str(self.state_path), "reason": "hardware state root mismatch"})
            claims = sorted(self.claims_dir.glob("*.json")) + sorted(self.quarantine_dir.glob("*.json"))
            if len(claims) != state.get("claim_sequence"):
                failures.append({"path": str(self.dir), "reason": "hardware claim sequence mismatch"})
            for path in claims:
                claim = json.loads(path.read_text())
                if claim.get("claim_id") != _stable_hash({
                    key: claim[key] for key in (
                        "source", "timestamp_tick", "raw_payload_sha256", "decoded_event",
                        "capability_required", "capabilities_presented", "state_root_before",
                    )
                }):
                    failures.append({"path": str(path), "reason": "IRQ claim hash mismatch"})
        except (OSError, KeyError, json.JSONDecodeError, BogBootError) as exc:
            failures.append({"path": str(self.dir), "reason": str(exc)})
        return {
            "format": "BOGHW-verification-receipt-14.0",
            "hardware_ledger_verified": not failures,
            "failures": failures,
            "execution_status": "completed" if not failures else "blocked",
        }

    def _load(self) -> tuple[dict, dict]:
        if not self.state_path.is_file() or not self.manifest_path.is_file():
            raise BogBootError("BogBoot has not completed")
        return json.loads(self.state_path.read_text()), json.loads(self.manifest_path.read_text())

    @staticmethod
    def _validate_manifest(manifest: dict) -> list[dict]:
        failures = []
        if manifest.get("platform") != "qemu-virt-reference":
            failures.append({"path": "platform", "reason": "BogBoot v0.1 supports only qemu-virt-reference"})
        required = {"serial", "timer"}
        if not required.issubset(manifest.get("devices", {})):
            failures.append({"path": "devices", "reason": "serial and timer devices are required"})
        ranges = []
        for entry in manifest.get("memory_map", []):
            start, size = entry.get("start"), entry.get("size")
            if not isinstance(start, int) or not isinstance(size, int) or start < 0 or size <= 0:
                failures.append({"path": "memory_map", "reason": "memory ranges require non-negative start and positive size"})
            else:
                ranges.append((start, start + size, entry.get("name")))
        for previous, current in zip(sorted(ranges), sorted(ranges)[1:]):
            if current[0] < previous[1]:
                failures.append({"path": "memory_map", "reason": f"overlapping memory ranges: {previous[2]} and {current[2]}"})
        return failures

    @staticmethod
    def _state_root(state: dict) -> str:
        return _stable_hash({key: value for key, value in state.items() if key != "state_root_sha256"})


def _stable_hash(obj: Any) -> str:
    return hashlib.sha256(canonical_bytes(obj)).hexdigest()


def _write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")
