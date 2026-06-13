# BogOS v34: Verified IPC / Message Passing

## Why v34 Matters

BogOS v34 lets isolated dynamically loaded Ring 3 processes exchange bounded
messages without sharing user memory. The kernel validates the caller and each
user range, copies sends into fixed kernel-owned queues, copies receives into
validated receiver-owned writable pages, and receipts every outcome.

This is a QEMU-only experimental proof, not a production IPC subsystem.

## Register ABI

IPC extends Syscall ABI v2 through `int 0x80`. `EAX` carries the syscall number
and result; `EBX`, `ECX`, `EDX`, and `ESI` carry arguments.

| Number | Name | Arguments | Success result |
| ---: | --- | --- | --- |
| 13 | `ipc_register_channel` | peer PID, max message size, max queue depth, flags | channel ID |
| 14 | `ipc_send` | channel ID, readable payload pointer, payload length, flags | message ID |
| 15 | `ipc_recv` | channel ID, writable output pointer, output length, flags | payload length |
| 16 | `ipc_poll` | channel ID | queue depth |

Flags must be zero. Existing ABI v2 errors remain stable: `-2` invalid pointer,
`-3` invalid length, `-4` permission denied, and `-5` unavailable/invalid
channel/empty/full.

## Channel And Queue Model

Channels are point-to-point and owner-created. The owner may send; the peer may
receive; either endpoint may poll. Peer PID `0` creates a deterministic
self-channel used by negative proofs. A peer must be a live process admitted
by the v32 dynamic loader.

The v34 proof kernel has at most four channels, two queued messages per channel,
and 64 bytes per message. Requested limits may be smaller. Queues and payloads
are kernel-owned fixed storage. There is no shared memory.

Each accepted message has a monotonic message ID, channel ID, sender PID,
receiver PID, payload length, and SHA-256 payload hash. A receive removes the
front message only after authorization, output-size validation, writable-range
validation, and the kernel-to-user copy all succeed.

## Pointer Validation And Rejections

`ipc_send` uses the v33 active-CR3 and owner-mapping validator before copying
bytes from the sender. `ipc_recv` requires receiver-owned present/user/writable
pages. Kernel pointers, another process's pages, read-only code, unmapped
ranges, and overflowing ranges are rejected.

The QEMU negative app proves kernel-pointer send, cross-process-pointer send,
oversized send, queue full, read-only-code receive, too-small receive,
unauthorized receive, and invalid channel rejection. Rejected sends and
receives report `MUTATED_TRUSTED_STATE=false`. Rejected receives preserve the
message ID, hash, and queue depth until a later valid receive.

## Receipts

The kernel emits:

- `BOGOS_IPC_CHANNEL` for accepted and rejected channel creation
- `BOGOS_IPC_SEND` for queue admission or rejection
- `BOGOS_IPC_RECV` for delivery or rejection
- `BOGOS_IPC_POLL` for receipt-visible queue depth
- `BOGOS_IPC_INVARIANTS` for kernel mediation, queue bounds, pointer validation,
  no shared memory, and preserved v31/v33 guarantees

All IPC calls also emit the normal `BOGOS_SYSCALL` ABI v2 receipt.

## Boundaries

BogOS v34 remains QEMU-only, i686, experimental, and non-production. It has no
blocking waits, asynchronous wakeups, shared memory, sockets/networking,
filesystem services, package-manager integration, POSIX compatibility,
threads/multicore, SMP queue synchronization, persistence, or physical hardware
support.
