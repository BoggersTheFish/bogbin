# BOGBIN v15: Verifier-First Vertical Expansion

The v15 verifier-first expansion connects hardware-modeled device boundaries, local-first claim resolution, and AI-proposal tournaments into a single signed vertical proof chain.

## Architecture Overview

BOGBIN v15 carries the "bytes accepted only after verification" rule through the entire stack, from emulated hardware IRQs up to swarm-selected state admission.

```text
  [ Swarm ] -- ( budget ) --> [ Pilot Candidates ]
      |                             |
      | ( best verified path )      | ( proposal )
      v                             v
[ Genesis Ledger ] <--- [ Deterministic Verifier ]
      ^                             ^
      | ( signed claims )           | ( model / hash )
      |                             |
  [ Mesh ] <----------------- [ BogIRQ / BogBoot ]
      |                             |
( Conflict Split )            ( QEMU Device Boundary )
```

## The Vertical Proof Chain

A completed v15 vertical demo executes and verifies the following stages:

1.  **BogBoot (QEMU-Reference Boot):** Emits a signed boot receipt over a deterministic device manifest, memory map, and initial hardware state root.
2.  **BogIRQ (Device-Boundary Gating):** Models timer, keyboard, serial, and block-device events. Valid events are admitted via capability and monotonic-tick checks; unauthorized events are quarantined.
3.  **BogMesh (Local-First Claim Exchange):** Exchanges signed claims between peers, verifies trusted identity, and deterministically converges or splits contexts on conflict.
4.  **BogPilot Swarm (Candidate Tournament):** Runs budgeted deterministic tournaments for untrusted planner proposals. Unsafe paths are blocked; the verified best path is selected and admitted.
5.  **Genesis (Signed State Admission):** The final arbiter. Every accepted hardware event, swarm decision, and mesh resolution is signed and chained into the append-only transparency ledger.

## Verification Receipts

The final v15 receipt (`BOGOS-verifier-first-vertical-receipt-15.0`) provides evidence for the entire vertical slice:

- `qemu_boot_receipt_verified`: Initial emulated hardware state is valid.
- `keyboard_irq_admitted`: Authorized device input entered the ledger.
- `unauthorized_irq_quarantined`: Tampered or unauthorized input was rejected.
- `hardware_ledger_verified`: The internal device-event log is consistent.
- `swarm_best_path_admitted`: The highest-scoring verified proposal was accepted.
- `swarm_replay_verified`: The selected swarm path was re-verified for deterministic correctness.
- `mesh_conflict_receipted`: Conflicting peer claims were identified.
- `mesh_context_split`: Divergent claims were isolated into a quarantined context.
- `mesh_verified`: The final mesh state conforms to deterministic resolution rules.
- `execution_status`: Must be `completed`.

## Boundaries and Technical Realities

To maintain first-contact clarity and sober technical framing, the following boundaries are enforced:

- **BogBoot / BogIRQ:** These are **user-space / QEMU-reference** contracts. They model emulated hardware behavior and memory maps but are not a physical BIOS, bare-metal kernel, or FPGA pin-level verifier.
- **BogMesh:** This is a **local-first signed claim exchange** protocol. It provides deterministic conflict resolution and identity verification but is not Byzantine Fault Tolerant (BFT) consensus or a production-scale public network.
- **BogPilot Swarm:** This treats AI/planner output as **untrusted candidate proposals**. It provides a deterministic tournament for selection and admission, but it is not a claim of autonomous "trusted" AI reasoning.
- **BogOS / BogK:** These are **user-space policy systems**. They verify and record workspace operations but are not host-kernel sandboxes and do not prevent direct host syscalls from malicious native processes.

## Reference Proof

The reference proof loop for v15 is:
`scripts/evaluate_verifier_first_vertical.py`

This script produces `artifacts/verifier_first_vertical_receipt.json`, which serves as the canonical evidence for the expansion's correctness.
