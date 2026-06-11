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
RECEIPT_PATH = ARTIFACTS_DIR / "bogos_v27_process_model_receipt.json"


def run_command(cmd, cwd=None):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def assemble_app(asm_code, dest_path):
    source = dest_path.with_suffix(".s")
    obj = dest_path.with_suffix(".o")
    source.write_text(asm_code)
    result = run_command(["as", "--32", "-o", str(obj), str(source)])
    if result.returncode != 0:
        raise RuntimeError(f"assembly failed: {result.stderr}")
    result = run_command(["objcopy", "-O", "binary", str(obj), str(dest_path)])
    if result.returncode != 0:
        raise RuntimeError(f"objcopy failed: {result.stderr}")
    source.unlink()
    obj.unlink()


def parse_process_receipts(output):
    receipts = []
    for block in output.split("BOGOS_PROCESS_BEGIN\n")[1:]:
        body = block.split("BOGOS_PROCESS_END", 1)[0]
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

    staging_dir = ARTIFACTS_DIR / "staging_v27"
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    apps_dir = staging_dir / "apps"
    apps_dir.mkdir(parents=True)
    (staging_dir / "input.dat").write_text("BOGBIN-v27-process-input")

    print("Creating v27 process-model apps...")
    result = run_command([
        "python3",
        str(ROOT / "scripts" / "tsc.py"),
        str(ROOT / "examples" / "hello.ts"),
        str(apps_dir / "hello.bogapp"),
    ])
    if result.returncode != 0:
        print(result.stderr)
        return 1

    hello_bytes = (apps_dir / "hello.bogapp").read_bytes()
    (apps_dir / "invalid_opcode.bogapp").write_bytes(hello_bytes[:310] + b"\x99")

    assemble_app(
        """
        .intel_syntax noprefix
        .code32
        .global _start
        _start:
            mov dx, 0x3f8
            mov al, 0x41
            out dx, al
            mov eax, 6
            xor ebx, ebx
            int 0x80
        """,
        apps_dir / "bad_app.bogapp",
    )
    assemble_app(
        """
        .intel_syntax noprefix
        .code32
        .global _start
        _start:
            mov eax, 99
            int 0x80
            cmp eax, -1
            jne fail
            mov eax, 6
            xor ebx, ebx
            int 0x80
        fail:
            mov eax, 6
            mov ebx, 42
            int 0x80
        """,
        apps_dir / "invalid_syscall.bogapp",
    )

    spoof_source = ARTIFACTS_DIR / "v27_spoof.ts"
    spoof_source.write_text(
        'const expected = "3457c19c980b8b9e58ac5957d712cbdb9f2d887e19642ac5eace426cf39783e3";\n'
        'const input = read_file("/input.dat");\n'
        'emit_receipt("BOGOS_PROCESS_END");\n'
        "exit(0);\n"
    )
    result = run_command([
        "python3",
        str(ROOT / "scripts" / "tsc.py"),
        str(spoof_source),
        str(apps_dir / "spoof.bogapp"),
    ])
    spoof_source.unlink()
    if result.returncode != 0:
        print(result.stderr)
        return 1

    initrd_path = ARTIFACTS_DIR / "initrd_v27.bogfs"
    result = run_command([
        "python3",
        str(ROOT / "scripts" / "make_bogfs.py"),
        str(staging_dir),
        str(initrd_path),
    ])
    if result.returncode != 0:
        print(result.stderr)
        return 1

    print("Building BogKernel...")
    result = run_command(
        ["cargo", "build", "-p", "bogk-kernel", "--target", "i686-unknown-linux-musl"],
        cwd=KERNEL_DIR,
    )
    if result.returncode != 0:
        print(result.stderr)
        return 1

    kernel_path = KERNEL_DIR / "target/i686-unknown-linux-musl/debug/bogk-kernel"
    serial_log = ARTIFACTS_DIR / "bogos_v27_process_model_serial.log"
    if serial_log.exists():
        serial_log.unlink()

    print("Booting QEMU...")
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
    deadline = time.time() + 15
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

    receipts = parse_process_receipts(output)
    by_path = {receipt.get("APP_PATH"): receipt for receipt in receipts}
    hello = by_path["/apps/hello.bogapp"]
    assert hello["PID"] == "1"
    assert hello["STATE_CREATED"] == "true"
    assert hello["STATE_VERIFIED"] == "true"
    assert hello["STATE_RUNNING"] == "true"
    assert hello["STATE_EXITED"] == "true"
    assert hello["EXECUTION_STATUS"] == "completed"
    assert hello["EXIT_CODE"] == "0"

    blocked = by_path["/apps/bad_app.bogapp"]
    assert blocked["STATE_BLOCKED"] == "true"
    assert blocked["EXECUTION_STATUS"] == "blocked"
    assert blocked["BLOCK_REASON"] == "gpf"

    missing = by_path["/apps/bad-hello.bogapp"]
    assert missing["APP_HASH"] == "none"
    assert missing["STATE_REJECTED"] == "true"
    assert missing["EXECUTION_STATUS"] == "rejected"
    assert missing["BLOCK_REASON"] == "not_found_or_unverified"

    assert "BOGOS PROCESS TABLE" in output
    assert "PID=1 APP_PATH=/apps/hello.bogapp" in output
    assert "STATE=EXITED" in output
    assert output.count("BOGOS_PROCESS_END") == len(receipts)

    receipt = {
        "format": "BOGOS-v27-process-model-receipt-1.0",
        "execution_status": "completed",
        "platform": "qemu",
        "process_count": len(receipts),
        "hello_pid": 1,
        "hello_status": "completed",
        "blocked_app_status": "blocked",
        "missing_app_status": "rejected",
        "process_pseudo_file_status": "passed",
        "bogfs_image_hash": hashlib.sha256(initrd_path.read_bytes()).hexdigest(),
        "qemu_serial_receipt_hash": hashlib.sha256(serial_log.read_bytes()).hexdigest(),
        "process_receipts": receipts,
        "serial_output": output,
    }
    RECEIPT_PATH.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(f"Receipt written to {RECEIPT_PATH}")
    print("v27 Verified Process Model PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
