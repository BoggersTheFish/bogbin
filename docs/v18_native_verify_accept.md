# BOGBIN v18: Native BOGVM Hash Verification and Data Acceptance

v18 implements the first native verifier opcodes inside the BogKernel/BOGVM executor, transitioning from a simple "decode and execute" spike to a functional "verify and accept" capability.

## Objective
Extend the native Rust BOGVM executor to support:
- `VERIFY_HASH (0x13)`: Compute the SHA-256 hash of an embedded data payload and verify it against an expected hash constant.
- `ACCEPT_DATA (0x14)`: Accept the payload if the hash matched the expectation.
- `REJECT_DATA (0x17)`: Reject the payload if the hash mismatched the expectation.

The kernel runs the verification sequence twice (once with the correct hash and once with an incorrect/all-zeros hash) and emits deterministic serial receipt markers to COM1.

## Implementation Details

### Hashing
A freestanding, allocation-free (`#![no_std]`) SHA-256 hash implementation is integrated into `bogk-core`.

### Supported Opcodes
- `VERIFY_HASH (0x13)`: Compares the computed hash of the payload to the expected hash. Sets a `hash_match` flag in the executor.
- `ACCEPT_DATA (0x14)`: Sets the `data_accepted` flag if `hash_match` is true.
- `REJECT_DATA (0x17)`: Sets the `data_rejected` flag if `hash_match` is false.
- `HALT (0x01)`: Ends VM execution.

### Verification Receipt
The verification results are outputted to COM1 with the following serial markers:
```text
BOGKERNEL_VERIFY_BEGIN
PAYLOAD_PRESENT=true
EXPECTED_HASH=<hash>
ACTUAL_HASH=<hash>
HASH_MATCH=true/false
DATA_ACCEPTED=true/false
DATA_REJECTED=true/false
EXECUTION_STATUS=completed/failed
BOGKERNEL_VERIFY_END
```

## Boundaries
- **Freestanding Environment:** Memory, interrupts, filesystem, and scheduler remain out of scope.
- **Embedded Payload:** The data payload is statically compiled into the kernel.
- **No full OS:** The kernel does not interface with physical hardware beyond the UART serial output.

## Verification
- Host-side audit and execution via `scripts/evaluate_bogkernel_verify_accept.py`.
- Rust executor unit tests via `cargo test -p bogk-core`.
