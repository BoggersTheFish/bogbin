import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
KERNEL_DIR = ROOT / "kernel"
ARTIFACTS_DIR = ROOT / "artifacts"
RECEIPT_PATH = ARTIFACTS_DIR / "bogos_v30_preemptive_scheduler_receipt.json"


def run_command(cmd, cwd=None):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def assemble_app(source_path, destination):
    object_path = destination.with_suffix(".o")
    result = run_command(["as", "--32", "-o", str(object_path), str(source_path)])
    if result.returncode != 0:
        raise RuntimeError(result.stderr)
    result = run_command(["objcopy", "-O", "binary", str(object_path), str(destination)])
    if result.returncode != 0:
        raise RuntimeError(result.stderr)
    object_path.unlink()


def parse_receipts(output, begin, end):
    receipts = []
    for block in output.split(begin + "\n")[1:]:
        body = block.split(end, 1)[0]
        receipt = {}
        for line in body.splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                receipt[key] = value
        receipts.append(receipt)
    return receipts


def write_mutated_bogapp(source, destination, mutations, refresh_manifest=True, trailing=b""):
    content = bytearray(source.read_bytes())
    for offset, value in mutations:
        content[offset : offset + len(value)] = value
    if refresh_manifest:
        content[104:136] = hashlib.sha256(content[:104]).digest()
    destination.write_bytes(bytes(content) + trailing)


def main():
    for tool in ["cargo", "qemu-system-i386", "as", "objcopy"]:
        if shutil.which(tool) is None:
            print(f"Error: {tool} not found in PATH")
            return 1

    staging_dir = ARTIFACTS_DIR / "staging_v30"
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    apps_dir = staging_dir / "apps"
    apps_dir.mkdir(parents=True)
    (staging_dir / "input.dat").write_text("BOGBIN-v18-payload")
    
    # Compile cooperative apps
    for source, destination in [
        (ROOT / "examples/v29_ctx_a.ts", apps_dir / "ctx_a.bogapp"),
        (ROOT / "examples/v29_ctx_b.ts", apps_dir / "ctx_b.bogapp"),
    ]:
        result = run_command(["python3", str(ROOT / "scripts/tsc.py"), str(source), str(destination)])
        if result.returncode != 0:
            print(result.stderr)
            return 1
            
    # Compile preemptive apps
    assemble_app(ROOT / "examples/v30_preempt_a.s", apps_dir / "preempt_a.bogapp")
    assemble_app(ROOT / "examples/v30_preempt_b.s", apps_dir / "preempt_b.bogapp")
    assemble_app(ROOT / "examples/v31_bad_kernel_read.s", apps_dir / "v31_bad_kernel_read.bogapp")
    assemble_app(ROOT / "examples/v31_bad_kernel_write.s", apps_dir / "v31_bad_kernel_write.bogapp")
    assemble_app(
        ROOT / "examples/v31_bad_cross_process_write.s",
        apps_dir / "v31_bad_cross_process_write.bogapp",
    )
    assemble_app(ROOT / "examples/v31_bad_code_write.s", apps_dir / "v31_bad_code_write.bogapp")

    dynamic_code = apps_dir / "dynamic_hello.raw"
    assemble_app(ROOT / "examples/v32_dynamic_hello.s", dynamic_code)
    for output, extra in [
        (apps_dir / "dynamic_hello.bogapp", []),
        (apps_dir / "bad_dynamic_hello.bogapp", ["--bad-code-hash"]),
        (apps_dir / "invalid_entrypoint.bogapp", ["--entrypoint", "0xffffffff"]),
    ]:
        result = run_command(
            [
                "python3",
                str(ROOT / "scripts/pack_v32_bogapp.py"),
                str(dynamic_code),
                str(output),
                "--name",
                output.stem,
                *extra,
            ]
        )
        if result.returncode != 0:
            print(result.stderr)
            return 1
    dynamic_code.unlink()
    (apps_dir / "malformed_dynamic.bogapp").write_bytes(b"not-a-v32-bogapp")
    valid_dynamic = apps_dir / "dynamic_hello.bogapp"
    dynamic_length = len(valid_dynamic.read_bytes()) - 136
    write_mutated_bogapp(
        valid_dynamic,
        apps_dir / "bad_magic.bogapp",
        [(0, b"BADAPP32")],
        refresh_manifest=False,
    )
    write_mutated_bogapp(
        valid_dynamic,
        apps_dir / "bad_version.bogapp",
        [(8, (2).to_bytes(4, "big"))],
        refresh_manifest=False,
    )
    write_mutated_bogapp(
        valid_dynamic,
        apps_dir / "zero_code_length.bogapp",
        [(24, (0).to_bytes(4, "big"))],
    )
    write_mutated_bogapp(
        valid_dynamic,
        apps_dir / "bad_code_offset.bogapp",
        [(20, (144).to_bytes(4, "big"))],
    )
    write_mutated_bogapp(
        valid_dynamic,
        apps_dir / "bad_code_length.bogapp",
        [(24, (dynamic_length + 1).to_bytes(4, "big"))],
    )
    write_mutated_bogapp(
        valid_dynamic,
        apps_dir / "entrypoint_at_end.bogapp",
        [(16, dynamic_length.to_bytes(4, "big"))],
    )
    write_mutated_bogapp(
        valid_dynamic,
        apps_dir / "unsupported_capability.bogapp",
        [(28, (1).to_bytes(4, "big"))],
    )
    write_mutated_bogapp(
        valid_dynamic,
        apps_dir / "trailing_bytes.bogapp",
        [],
        trailing=b"\0",
    )
    bad_manifest = bytearray(valid_dynamic.read_bytes())
    bad_manifest[104] ^= 0xFF
    (apps_dir / "bad_manifest_hash.bogapp").write_bytes(bad_manifest)
    write_mutated_bogapp(
        valid_dynamic,
        apps_dir / "noncanonical_name.bogapp",
        [(46, b"X")],
    )
    for source_name in [
        "v33_syscall_write",
        "v33_syscall_verify",
        "v33_syscall_claim",
        "v33_bad_syscall_kernel_ptr",
        "v33_bad_syscall_cross_process_ptr",
        "v33_bad_syscall_overflow_ptr",
        "v33_audit_lengths",
        "v33_audit_ranges",
        "v33_audit_misc",
        "v34_ipc_sender",
        "v34_ipc_receiver",
        "v34_ipc_negative",
    ]:
        raw_path = apps_dir / f"{source_name}.raw"
        output_path = apps_dir / f"{source_name}.bogapp"
        assemble_app(ROOT / f"examples/{source_name}.s", raw_path)
        result = run_command(
            [
                "python3",
                str(ROOT / "scripts/pack_v32_bogapp.py"),
                str(raw_path),
                str(output_path),
                "--name",
                source_name[:23],
            ]
        )
        if result.returncode != 0:
            print(result.stderr)
            return 1
        raw_path.unlink()
    
    # Compile bad_sched.bogapp
    bad_sched_src = apps_dir / "bad_sched.s"
    bad_sched_src.write_text(
        """
        .intel_syntax noprefix
        .code32
        .global _start
        _start:
            mov dx, 0x3f8
            mov al, 0x41
            out dx, al
        """
    )
    assemble_app(bad_sched_src, apps_dir / "bad_sched.bogapp")
    bad_sched_src.unlink()

    initrd_path = ARTIFACTS_DIR / "initrd_v30.bogfs"
    result = run_command([
        "python3",
        str(ROOT / "scripts/make_bogfs.py"),
        str(staging_dir),
        str(initrd_path),
    ])
    if result.returncode != 0:
        print(result.stderr)
        return 1
        
    result = run_command(
        ["cargo", "build", "-p", "bogk-kernel", "--target", "i686-unknown-linux-musl"],
        cwd=KERNEL_DIR,
    )
    if result.returncode != 0:
        print(result.stderr)
        return 1

    kernel_path = KERNEL_DIR / "target/i686-unknown-linux-musl/debug/bogk-kernel"
    serial_log = ARTIFACTS_DIR / "bogos_v30_preemptive_scheduler_serial.log"
    if serial_log.exists():
        serial_log.unlink()
        
    process = subprocess.Popen([
        "qemu-system-i386",
        "-kernel",
        str(kernel_path),
        "-initrd",
        str(initrd_path),
        "-serial",
        f"file:{serial_log}",
        "-display",
        "none",
        "-icount",
        "shift=3,align=off",
    ])
    
    output = ""
    deadline = time.time() + 20
    while time.time() < deadline:
        if serial_log.exists():
            output = serial_log.read_text()
            if "BOGOS_PANIC_END" in output:
                break
        time.sleep(0.25)
    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        
    if "BOGOS_PANIC_END" not in output:
        print("Error: QEMU auto-demo did not complete")
        return 1

    process_receipts = parse_receipts(output, "BOGOS_PROCESS_BEGIN", "BOGOS_PROCESS_END")
    preempts = parse_receipts(output, "BOGOS_PREEMPT_BEGIN", "BOGOS_PREEMPT_END")
    saves = parse_receipts(output, "BOGOS_CONTEXT_SAVE_BEGIN", "BOGOS_CONTEXT_SAVE_END")
    restores = parse_receipts(output, "BOGOS_CONTEXT_RESTORE_BEGIN", "BOGOS_CONTEXT_RESTORE_END")
    
    latest = {receipt.get("APP_PATH"): receipt for receipt in process_receipts}
    
    # 1. Verify preempt_a and preempt_b ran and exited successfully
    assert "/apps/preempt_a.bogapp" in latest
    assert "/apps/preempt_b.bogapp" in latest
    a_pid = latest["/apps/preempt_a.bogapp"]["PID"]
    b_pid = latest["/apps/preempt_b.bogapp"]["PID"]
    
    assert latest["/apps/preempt_a.bogapp"]["STATE_EXITED"] == "true"
    assert latest["/apps/preempt_b.bogapp"]["STATE_EXITED"] == "true"
    assert latest["/apps/preempt_a.bogapp"]["STATE_PREEMPTED"] == "true"
    assert latest["/apps/preempt_b.bogapp"]["STATE_PREEMPTED"] == "true"

    # 2. Verify deterministic interleaved output (A1, B1, A2, B2)
    positions = [output.index(f"\n{marker}\n") for marker in ["A1", "B1", "A2", "B2"]]
    assert positions == sorted(positions)

    # 3. Verify BOGOS_PREEMPT receipts for preempt_a and preempt_b
    preempt_pids = {receipt["PID"] for receipt in preempts}
    assert a_pid in preempt_pids
    assert b_pid in preempt_pids
    
    for receipt in preempts:
        assert receipt["STATE_BEFORE"] == "RUNNING"
        assert receipt["STATE_AFTER"] == "READY"
        assert receipt["REASON"] == "timer_irq"
        assert int(receipt["PREEMPTION_COUNT"]) > 0
        assert len(receipt["EIP"]) == 8
        assert len(receipt["ESP"]) == 8

    # 4. Verify saved/restored EIP and ESP for preempted processes
    preempt_by_pid = {receipt["PID"]: receipt for receipt in preempts}
    restore_by_pid = {receipt["PID"]: receipt for receipt in restores}
    
    for pid in [a_pid, b_pid]:
        p_rec = preempt_by_pid[pid]
        r_rec = restore_by_pid[pid]
        assert p_rec["EIP"] == r_rec["EIP"]
        assert p_rec["ESP"] == r_rec["ESP"]

    # 5. Verify exited/blocked/rejected processes are not preempted or restored
    # Strict non-preemptable: anything other than preempt_a, preempt_b, ctx_a, ctx_b
    ctx_a_pid = latest["/apps/ctx_a.bogapp"]["PID"]
    ctx_b_pid = latest["/apps/ctx_b.bogapp"]["PID"]
    dynamic_pid = latest["/apps/dynamic_hello.bogapp"]["PID"]
    v33_pids = [
        receipt["PID"]
        for receipt in process_receipts
        if receipt.get("APP_PATH", "").startswith("/apps/v33_")
    ]
    v34_pids = [
        receipt["PID"]
        for receipt in process_receipts
        if receipt.get("APP_PATH", "").startswith("/apps/v34_")
    ]
    strict_non_preemptable_pids = {
        receipt["PID"]
        for receipt in process_receipts
        if receipt["PID"] not in [a_pid, b_pid, ctx_a_pid, ctx_b_pid, dynamic_pid, *v33_pids, *v34_pids]
    }
    assert strict_non_preemptable_pids.isdisjoint({receipt["PID"] for receipt in preempts})
    assert strict_non_preemptable_pids.isdisjoint({receipt["PID"] for receipt in restores})

    # 6. Verify scheduler receipts contain REASON field
    sched_receipts = parse_receipts(output, "BOGOS_SCHED_BEGIN", "BOGOS_SCHED_END")
    for r in sched_receipts:
        assert "REASON" in r
        assert r["REASON"] in ["yield", "spawn", "preemption", "exit", "block", "none"]

    receipt = {
        "format": "BOGOS-v30-preemptive-scheduler-receipt-1.0",
        "execution_status": "completed",
        "platform": "qemu",
        "output_order": ["A1", "B1", "A2", "B2"],
        "preempt_a_pid": a_pid,
        "preempt_b_pid": b_pid,
        "preemption_receipts": preempts,
        "context_restore_receipts": restores,
        "bogfs_image_hash": hashlib.sha256(initrd_path.read_bytes()).hexdigest(),
        "qemu_serial_receipt_hash": hashlib.sha256(serial_log.read_bytes()).hexdigest(),
        "serial_output": output,
    }
    RECEIPT_PATH.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(f"Receipt written to {RECEIPT_PATH}")
    print("v30 Preemptive Scheduler PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
