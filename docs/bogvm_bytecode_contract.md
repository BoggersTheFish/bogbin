# BOGVM Bytecode Contract

This document defines the deterministic instruction format and execution semantics for BOGVM, acting as the source of truth for both the Python reference implementation and the native Rust port.

## Instruction Format
All instructions are 8 bytes long, encoded as big-endian integers:

| Offset | Size | Name | Description |
| :--- | :--- | :--- | :--- |
| 0 | 1 | `opcode` | The operation to perform. |
| 1 | 1 | `flags` | Metadata for the operation (e.g., edge type). |
| 2 | 2 | `target` | Primary operand or result destination. |
| 4 | 2 | `source` | Secondary operand. |
| 6 | 2 | `param` | tertiary operand or parameter (e.g., depth, strength). |

Python equivalent: `struct.Struct(">BBHHH")`

## Opcode List

| Name | Hex | Description |
| :--- | :--- | :--- |
| `NOOP` | `0x00` | No operation. |
| `HALT` | `0x01` | Terminate execution. |
| `CREATE_NODE` | `0x02` | Declare a node. |
| `CREATE_EDGE` | `0x03` | Declare an edge between nodes. |
| `CREATE_CLAIM` | `0x04` | Declare a claim over an edge. |
| `ACTIVATE` | `0x05` | Set initial node activation strength. |
| `PROPAGATE` | `0x06` | Spread activation through edges. |
| `DECAY` | `0x07` | Reduce all activation strengths. |
| `INTERFERE` | `0x08` | Compute support/conflict pressure on a claim. |
| `COMPUTE_TENSION` | `0x09` | Compute tension on a claim. |
| `VERIFY` | `0x0A` | Transition claim to `verified` or `rejected`. |
| `ACCEPT` | `0x0B` | Accept a verified claim into the receipt. |
| `REJECT` | `0x0C` | Explicitly reject a claim. |
| `QUARANTINE` | `0x0D` | Move a claim to quarantine. |
| `LOG_RECEIPT` | `0x0E` | Append a record to the internal receipt ledger. |
| `EMIT_RECEIPT` | `0x0F` | Finalize and output the execution receipt. |
| `DECLARE_BASIS` | `0x10` | Declare a deterministic generator basis. |
| `LOAD_COEFFICIENTS`| `0x11` | Load parameters for a data block. |
| `SYNTHESIZE` | `0x12` | Reconstruct bytes from a basis and coefficients. |
| `VERIFY_HASH` | `0x13` | Compare reconstructed bytes against SHA-256. |
| `ACCEPT_DATA` | `0x14` | Accept data block only after hash verification. |
| `STORE_RESIDUAL` | `0x15` | Store a byte-level patch for a data block. |
| `APPLY_RESIDUAL` | `0x16` | Apply patches to a synthesized data block. |

## Execution Semantics

### Fixed-Point Math
All strength, weight, and decay values are integers in the range `0..1000`.
`SCALE = 1000`
Multiplication and division follow the rule: `result = (value * factor) // SCALE`

### Data Blocks
1. `SYNTHESIZE` must use the exact deterministic algorithms defined in `bogvm/bases.py`.
2. `VERIFY_HASH` is a hard gate. If the SHA-256 mismatch occurs, the execution is blocked.
3. `ACCEPT_DATA` requires a prior successful `VERIFY_HASH` for the same block ID.

## Initial Test Vectors
Reference `.bogbin` files in `examples/` and `artifacts/` must produce identical receipt hashes across implementations.

- **Proof Chain:** `examples/proof_chain.bogasm` -> `artifacts/proof_chain_receipt.json`
- **Generative Storage:** `examples/repeat_byte_storage.bogasm` -> `artifacts/repeat_byte_storage_receipt.json`
