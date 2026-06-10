# BOGBIN v17: Native Minimal BOGVM Execution

v17 implements the first native BOGVM execution path inside the BogKernel. It transitions from a simple "boots and writes to serial" proof to a "boots and executes bytecode" proof.

## Objective
The kernel boots in QEMU, runs a tiny embedded BOGVM bytecode program, and emits serial receipt markers proving that the native executor decoded and executed the expected instructions.

## Implementation Details

### Instruction Format
v17 follows the `docs/bogvm_bytecode_contract.md` specification:
- 8-byte big-endian instructions (`>BBHHH`).
- Fields: `opcode`, `flags`, `target`, `source`, `param`.

### Supported Opcodes
To maintain a narrow scope, only two opcodes are supported in this milestone:
- `NOOP (0x00)`: Increments the instruction count and program counter.
- `HALT (0x01)`: Terminates execution and signals completion.

Any other opcode seen by the minimal executor will stop execution and be marked as `unsupported_opcode_seen`.

### Execution Receipt
The native executor returns a deterministic result including:
- `instruction_count`: Total number of instructions executed.
- `pc_final`: The final program counter value.
- `halted`: Boolean indicating if the program reached a `HALT` opcode.
- `unsupported_opcode_seen`: Boolean indicating if an unknown opcode was encountered.
- `execution_status`: `completed` or `failed`.

### Serial Proof Markers
Execution results are emitted to COM1 with the following markers:
```text
BOGKERNEL_VM_EXEC_BEGIN
BOGKERNEL_VM_FORMAT=BOGKERNEL-native-vm-receipt-17.0
INSTRUCTION_WIDTH=8
PROGRAM_INSTRUCTION_COUNT=<count>
OPCODES_EXECUTED=NOOP,HALT
HALTED=true
UNSUPPORTED_OPCODE_SEEN=false
EXECUTION_STATUS=completed
BOGKERNEL_VM_EXEC_END
```

## Boundaries
- **Minimal Opcode Support:** Only `NOOP` and `HALT`. No data synthesis, hash verification, or graph propagation yet.
- **Static Program:** The bytecode is embedded directly in the kernel image.
- **No Full OS:** No interrupts, scheduler, filesystem, or drivers beyond the minimal UART stub.
- **QEMU Only:** Reference execution in an emulated environment.

## Verification
The `scripts/evaluate_bogkernel_vm_exec.py` script builds the kernel, audits the ELF, runs QEMU, and verifies both the boot and VM execution serial markers.
