# Benchmark framework and first observations

These observations seed a reproducible framework. They are not a BogOS-versus-Linux benchmark result. All raw samples and environment records are in [evidence](evidence/).

## Experiment classes and fair comparisons

| Class | Valid question | Comparison rule |
|---|---|---|
| Shared host algorithm | What does a bounded resource transition or checkpoint cost? | Same process/CPU/toolchain, equal inputs and outputs, include validation/receipt overhead explicitly |
| Matched guests | What does an actual BogOS syscall, IPC or allocator do relative to Linux? | Both guests use identical emulator/acceleration/vCPU/RAM/storage/cache settings and equivalent security/durability contracts |
| Physical OS | Does BogOS improve a real task on the reference PC? | Later approved hardware milestone, recoverable backups, identical workload/device/power/mitigation configuration |
| End-user tasks | Is the system usable and responsive? | Equivalent applications/data/tasks, input-to-completion distributions, task failure rate and accessibility, not a timer proxy alone |

Do not compare QEMU instruction timings with native Linux syscall times, a pure object update with a kernel syscall, cached reads with device throughput, or nondurable writes with fsync. [Linux perf-bench documentation](https://github.com/torvalds/linux/blob/master/tools/perf/Documentation/perf-bench.txt) describes useful eventual scheduler, syscall, memory and IPC baselines; its default stress workloads were not run on the active desktop.

For each future performance experiment, predeclare success criteria, identical operation counts, data hashes, resource limits, correctness/rejection checks and semantics. Record warmup, affinity, governor/frequency, thermal/load state, compiler flags, mitigations, logging, cache state, device/firmware and exact revisions. Retain all samples, not only the fastest trial. Run multiple independent batches, alternate A/B order and report confidence intervals when there are enough observations. Include CPU time, peak/live memory, allocator fragmentation/leaks, syscall/interrupt counts, throughput and p50/p95/p99/p99.9 latency as appropriate. Treat regressions in correctness, resource usage, starvation or durability as failure even when the mean improves.

## BKC host microbenchmark

Command after building the container environment:

```bash
docker run --rm --user "$(id -u):$(id -g)" --cpus=2 --memory=2g \
  -v "$PWD:/work" -e CARGO_HOME=/work/.cargo-cache \
  bogos-genesis-dev:1.85.1 \
  bash -c 'cd kernel && cargo build --locked --release -p bogk-core --example bkc_bench'
nice -n 10 timeout 30 kernel/target/release/examples/bkc_bench > bkc-benchmark.json
```

The x86-64 Linux host binary performs identical ownership transfers on 64 resources. It alternates each principal 1→2→1, rotating resources. One mode adds a complete O(64) checkpoint after each transfer. Setup occurs before timing; final checkpoint equality is mandatory in every pair. `black_box` retains observable work. There are two warmup pairs and 21 recorded pairs of 1,024 transfers. Order alternates. State storage is **1,032 bytes** on this target, with no dynamic allocation in the measured state transitions.

Initial run (`evidence/bkc-benchmark.json`, Rust 1.85.1 release, host CPU):

| Mode | Median ns/transfer | Range of batch-average ns/transfer |
|---|---:|---:|
| Local ownership transition | 2.983 | 2.927–3.077 |
| Same transition plus full checkpoint after every operation | 16,115.341 | 15,908.244–16,940.512 |

These are batch averages, not per-operation tail samples. The fast batches are very short and the test has a tiny hot working set. The hash path uses the software SHA-256 implementation in bogk-core. This demonstrates the cost of *adding* frequent full-state hashing to this toy operation. It does not establish that removing a required journal/security check is safe, that an alternative produces equal audit evidence, that kernels have this syscall cost, or that BogOS outperforms Linux. Both modes are Linux processes using the same model. More realistic contention, mapping, IPC and durable-state benchmarks remain necessary.

## Linux seed baseline

```bash
nice -n 10 timeout 30 python3 scripts/benchmark_genesis_linux.py \
  --output artifacts/genesis-linux/results.json
```

The benchmark uses ordinary bounded memory, a temporary file under the output directory and a tiny compile/link task. It does not access raw disks, change affinity/governors/cache policy, load all cores or run GPU computation. It records machine metadata and process resource usage. Source buffers and outputs are checked, and workloads execute under `python -O` too. Review caught an earlier version with work in removable assertions; its misleading results are preserved as negative evidence in `evidence/review-controls/`.

First normal run on BoggersThePC, Python 3.12.3, ext4 on the SanDisk SSD:

| Operation per sample | Median ms | Maximum / empirical p99 ms |
|---|---:|---:|
| SHA-256, 4 × 4 MiB | 29.877 | 40.733 |
| libc memmove, 16 × 4 MiB | 2.324 | 6.029 |
| 2,000 getpid calls via ctypes/Python (also includes os.getpid checks) | 2.609 | 2.663 |
| Buffered 4 MiB write + fsync | 10.988 | 20.712 |
| Cached 4 MiB read + SHA-256 | 7.880 | 7.964 |
| Tiny C compile + link | 30.639 | 30.965 |
| 1 ms sleep overshoot (32 samples) | 0.165 | 0.188 |

Nine samples per operation except five compilations and 32 sleeps. With these sample counts, empirical p99 is effectively the maximum and is not a defensible production-tail estimate. Process wall time was approximately 0.97 seconds; parent user/system CPU approximately 0.448/0.020 seconds, peak RSS 35,276 KiB. Compiler child CPU/RSS is not included in those parent figures. Concurrent development/desktop activity was not controlled. A later corrected `-O` run is also retained; it is a correctness control, not another sample merged into the first run.

The storage results include page cache and Python/hash overhead; they do not measure sustained disk throughput, random IOPS or crash durability. Memory copy uses a 4 MiB working set and does not characterise DRAM bandwidth/fragmentation. Tiny compilation is not a kernel/application build benchmark. Sleep overshoot is a scheduling observation, not measured desktop input latency. GPU/AI throughput, multicore scaling and power/energy efficiency were **not run**: a matched isolated workload and backend must first be established.

## Required next benchmarks

- Once Ring 3 tests pass: empty syscall roundtrip, scheduler wakeup/preemption, 0/64/4096-byte IPC with equal copying and validation, page alloc/map/unmap/reuse.
- Fragmentation/reclaim: fixed seeds, mixed allocation lifetimes and bounded memory; report internal/external fragmentation, failure rate, peak/live bytes and cleanup.
- Storage: host-built crash traces plus fault injection after every commit write/barrier, sequential/random workloads with explicit durability, corrupt roots and recovery latency.
- Multicore: 1/2/4/8 vCPU runs, per-CPU versus shared queues, lock contention/cache misses, migration cost, fairness and p99/p99.9 with sufficiently many events.
- Devices/GPU: start with virtio ownership and driver-fault containment; later approved real GPUs with equal numeric precision/model/batch/outputs, data movement, device memory, latency and power accounting.
- Adaptation: fixed and held-out workload mixes against conventional static/adaptive schedulers at equal controller budget. Include the cost of telemetry and reconfiguration.

No aggregate “superior to Linux” score is defined. Publish workload-specific successes and failures with their contracts.
