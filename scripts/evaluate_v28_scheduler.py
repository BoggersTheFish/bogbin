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
RECEIPT_PATH = ARTIFACTS_DIR / "bogos_v28_scheduler_receipt.json"


def run_command(cmd, cwd=None):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def assemble_app(source, destination):
    source_path = destination.with_suffix(".s")
    object_path = destination.with_suffix(".o")
    source_path.write_text(source)
    result = run_command(["as", "--32", "-o", str(object_path), str(source_path)])
    if result.returncode != 0:
        raise RuntimeError(result.stderr)
    result = run_command(["objcopy", "-O", "binary", str(object_path), str(destination)])
    if result.returncode != 0:
        raise RuntimeError(result.stderr)
    source_path.unlink()
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


def main():
    for tool in ["cargo", "qemu-system-i386", "as", "objcopy"]:
        if shutil.which(tool) is None:
            print(f"Error: {tool} not found in PATH")
            return 1

    staging_dir = ARTIFACTS_DIR / "staging_v28"
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    apps_dir = staging_dir / "apps"
    apps_dir.mkdir(parents=True)

    assemble_app(
        """
        .intel_syntax noprefix
        .code32
        .global _start
        _start:
            mov eax, 7
            int 0x80
            mov eax, 6
            xor ebx, ebx
            int 0x80
        """,
        apps_dir / "sched_a.bogapp",
    )
    assemble_app(
        """
        .intel_syntax noprefix
        .code32
        .global _start
        _start:
            mov eax, 6
            xor ebx, ebx
            int 0x80
        """,
        apps_dir / "sched_b.bogapp",
    )
    assemble_app(
        """
        .intel_syntax noprefix
        .code32
        .global _start
        _start:
            mov dx, 0x3f8
            mov al, 0x41
            out dx, al
        """,
        apps_dir / "bad_sched.bogapp",
    )

    initrd_path = ARTIFACTS_DIR / "initrd_v28.bogfs"
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
    serial_log = ARTIFACTS_DIR / "bogos_v28_scheduler_serial.log"
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

    scheduler_receipts = parse_receipts(output, "BOGOS_SCHED_BEGIN", "BOGOS_SCHED_END")
    process_receipts = parse_receipts(output, "BOGOS_PROCESS_BEGIN", "BOGOS_PROCESS_END")
    spawned = {}
    for receipt in process_receipts:
        if receipt.get("APP_PATH") in {
            "/apps/sched_a.bogapp",
            "/apps/sched_b.bogapp",
            "/apps/bad_sched.bogapp",
        }:
            spawned[receipt["APP_PATH"]] = receipt

    selected = [receipt["SELECTED_PID"] for receipt in scheduler_receipts]
    sched_a_pid = spawned["/apps/sched_a.bogapp"]["PID"]
    sched_b_pid = spawned["/apps/sched_b.bogapp"]["PID"]
    bad_pid = spawned["/apps/bad_sched.bogapp"]["PID"]
    assert selected[:4] == [sched_a_pid, sched_b_pid, bad_pid, sched_a_pid]
    assert all(receipt["POLICY"] == "fifo_round_robin_ready" for receipt in scheduler_receipts)
    assert all(receipt["SELECTED_STATE"] == "SCHEDULED" for receipt in scheduler_receipts[:4])
    assert selected.count(bad_pid) == 1
    rejected_pids = {
        receipt["PID"]
        for receipt in process_receipts
        if receipt.get("STATE_REJECTED") == "true"
    }
    assert rejected_pids.isdisjoint(selected)
    assert spawned["/apps/sched_a.bogapp"]["STATE_YIELDED"] == "true"
    assert spawned["/apps/sched_b.bogapp"]["STATE_EXITED"] == "true"
    assert spawned["/apps/bad_sched.bogapp"]["STATE_BLOCKED"] == "true"
    assert "BOGOS PROCESS TABLE" in output
    assert "BOGOS SCHEDULER" in output
    assert "selected_policy=fifo_round_robin_ready" in output
    assert "/system/processes" in output
    assert "/system/scheduler" in output

    receipt = {
        "format": "BOGOS-v28-cooperative-scheduler-receipt-1.0",
        "execution_status": "completed",
        "platform": "qemu",
        "policy": "fifo_round_robin_ready",
        "selected_pids": selected,
        "sched_a_pid": sched_a_pid,
        "sched_b_pid": sched_b_pid,
        "bad_pid": bad_pid,
        "blocked_process_rescheduled": False,
        "rejected_process_scheduled": False,
        "bogfs_image_hash": hashlib.sha256(initrd_path.read_bytes()).hexdigest(),
        "qemu_serial_receipt_hash": hashlib.sha256(serial_log.read_bytes()).hexdigest(),
        "scheduler_receipts": scheduler_receipts,
        "serial_output": output,
    }
    RECEIPT_PATH.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(f"Receipt written to {RECEIPT_PATH}")
    print("v28 Cooperative Verified Scheduler PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
