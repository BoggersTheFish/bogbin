from __future__ import annotations

from typing import Any

from .bogboot import BogBoot
from .mesh import BogMesh
from .swarm import BogPilotSwarm


def vertical_demo(workspace: Any) -> dict:
    boot = BogBoot(workspace)
    boot_receipt = boot.boot()
    keyboard = boot.irq_claim("keyboard", "a", {"key": "a", "pressed": True}, ["hardware.keyboard.input"])
    blocked_irq = boot.irq_claim("block_device", "sector:7", {"sector": 7}, [])
    swarm = BogPilotSwarm(workspace)
    tournament = swarm.tournament("choose verified system action", [
        {"action": "write", "path": "vertical/action-a.txt", "data": "A", "score": 7, "cost": 2},
        {"action": "write", "path": "vertical/action-b.txt", "data": "B", "score": 10, "cost": 3},
        {"action": "write", "path": "../unsafe.txt", "data": "unsafe", "score": 100, "cost": 1},
    ])
    replay = swarm.replay(tournament)
    mesh = BogMesh(workspace)
    mesh.propose("bogos/vertical", {"state": "B"}, context={"branch": "main"}, support=2, capability_scope=["registry.publish"])
    conflict = mesh.propose("bogos/vertical", {"state": "C"}, context={"branch": "main"}, support=2, capability_scope=["registry.publish"])
    checks = {
        "qemu_boot_receipt_verified": boot_receipt["execution_status"] == "completed",
        "keyboard_irq_admitted": keyboard["accepted"],
        "unauthorized_irq_quarantined": blocked_irq["execution_status"] == "blocked",
        "hardware_ledger_verified": boot.verify()["execution_status"] == "completed",
        "swarm_best_path_admitted": tournament["execution_status"] == "completed",
        "swarm_replay_verified": replay["swarm_replay_verified"],
        "mesh_conflict_receipted": conflict["conflict_detected"],
        "mesh_context_split": conflict["context_split"],
        "mesh_verified": mesh.verify()["execution_status"] == "completed",
    }
    return boot.genesis.record("verifier-first-vertical", {
        "format": "BOGOS-verifier-first-vertical-receipt-15.0",
        **checks,
        "boot_receipt": boot_receipt["receipt_hash"],
        "irq_receipt": keyboard["receipt_hash"],
        "swarm_receipt": tournament["receipt_hash"],
        "mesh_receipt": conflict["receipt_hash"],
        "execution_status": "completed" if all(checks.values()) else "blocked",
    })
