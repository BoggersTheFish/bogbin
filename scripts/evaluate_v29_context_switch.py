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
RECEIPT_PATH = ARTIFACTS_DIR / "bogos_v29_context_switch_receipt.json"


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

    staging_dir = ARTIFACTS_DIR / "staging_v29"
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    apps_dir = staging_dir / "apps"
    apps_dir.mkdir(parents=True)
    (staging_dir / "input.dat").write_text("BOGBIN-v18-payload")
    for source, destination in [
        (ROOT / "examples/v29_ctx_a.ts", apps_dir / "ctx_a.bogapp"),
        (ROOT / "examples/v29_ctx_b.ts", apps_dir / "ctx_b.bogapp"),
    ]:
        result = run_command(["python3", str(ROOT / "scripts/tsc.py"), str(source), str(destination)])
        if result.returncode != 0:
            print(result.stderr)
            return 1
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

    initrd_path = ARTIFACTS_DIR / "initrd_v29.bogfs"
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
    serial_log = ARTIFACTS_DIR / "bogos_v29_context_switch_serial.log"
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

    process_receipts = parse_receipts(output, "BOGOS_PROCESS_BEGIN", "BOGOS_PROCESS_END")
    saves = parse_receipts(output, "BOGOS_CONTEXT_SAVE_BEGIN", "BOGOS_CONTEXT_SAVE_END")
    restores = parse_receipts(output, "BOGOS_CONTEXT_RESTORE_BEGIN", "BOGOS_CONTEXT_RESTORE_END")
    latest = {receipt.get("APP_PATH"): receipt for receipt in process_receipts}
    a_pid = latest["/apps/ctx_a.bogapp"]["PID"]
    b_pid = latest["/apps/ctx_b.bogapp"]["PID"]

    positions = [output.index(f"\n{marker}\n") for marker in ["A1", "B1", "A2", "B2"]]
    assert positions == sorted(positions)
    assert {receipt["PID"] for receipt in saves} >= {a_pid, b_pid}
    assert {receipt["PID"] for receipt in restores} >= {a_pid, b_pid}
    saved_by_pid = {receipt["PID"]: receipt for receipt in saves}
    restored_by_pid = {receipt["PID"]: receipt for receipt in restores}
    for pid in [a_pid, b_pid]:
        assert saved_by_pid[pid]["EIP"] == restored_by_pid[pid]["EIP"]
        assert saved_by_pid[pid]["ESP"] == restored_by_pid[pid]["ESP"]
    assert saved_by_pid[a_pid]["EIP"] != saved_by_pid[b_pid]["EIP"]
    assert saved_by_pid[a_pid]["ESP"] != saved_by_pid[b_pid]["ESP"]
    assert latest["/apps/ctx_a.bogapp"]["STATE_EXITED"] == "true"
    assert latest["/apps/ctx_b.bogapp"]["STATE_EXITED"] == "true"
    terminal_pids = {
        receipt["PID"]
        for receipt in process_receipts
        if receipt.get("STATE_BLOCKED") == "true" or receipt.get("STATE_REJECTED") == "true"
    }
    assert terminal_pids.isdisjoint({receipt["PID"] for receipt in restores})
    for receipt in saves + restores:
        assert len(receipt["EIP"]) == 8
        assert len(receipt["ESP"]) == 8

    receipt = {
        "format": "BOGOS-v29-context-switch-receipt-1.0",
        "execution_status": "completed",
        "platform": "qemu",
        "output_order": ["A1", "B1", "A2", "B2"],
        "ctx_a_pid": a_pid,
        "ctx_b_pid": b_pid,
        "context_save_receipts": saves,
        "context_restore_receipts": restores,
        "terminal_process_restored": False,
        "bogfs_image_hash": hashlib.sha256(initrd_path.read_bytes()).hexdigest(),
        "qemu_serial_receipt_hash": hashlib.sha256(serial_log.read_bytes()).hexdigest(),
        "serial_output": output,
    }
    RECEIPT_PATH.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(f"Receipt written to {RECEIPT_PATH}")
    print("v29 Saved User Contexts PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
