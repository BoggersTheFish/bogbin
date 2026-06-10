import json
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KERNEL_DIR = ROOT / "kernel"
ARTIFACTS_DIR = ROOT / "artifacts"
RECEIPT_PATH = ARTIFACTS_DIR / "native_verify_accept_receipt.json"

def run_command(cmd, cwd=None, timeout=None):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)

def main():
    print("Checking dependencies...")
    for tool in ["cargo", "qemu-system-i386", "readelf", "nm"]:
        if subprocess.run(["which", tool], capture_output=True).returncode != 0:
            print(f"Error: {tool} not found in PATH")
            return 1

    print("Building BogKernel...")
    build_result = run_command(
        ["cargo", "build", "-p", "bogk-kernel", "--target", "i686-unknown-linux-musl"],
        cwd=KERNEL_DIR
    )
    if build_result.returncode != 0:
        print("Build failed:")
        print(build_result.stderr)
        return 1

    kernel_path = KERNEL_DIR / "target" / "i686-unknown-linux-musl" / "debug" / "bogk-kernel"
    serial_log = ARTIFACTS_DIR / "bogkernel_verify_serial.log"
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    if serial_log.exists():
        serial_log.unlink()

    print("Running QEMU...")
    qemu_cmd = [
        "qemu-system-i386",
        "-kernel", str(kernel_path),
        "-serial", f"file:{serial_log}",
        "-display", "none",
    ]
    
    process = subprocess.Popen(qemu_cmd)
    
    start_time = time.time()
    timeout = 10
    output = ""
    success = False
    
    while time.time() - start_time < timeout:
        if serial_log.exists():
            output = serial_log.read_text()
            # We want to see two BOGKERNEL_VERIFY_END markers
            if output.count("BOGKERNEL_VERIFY_END") >= 2:
                success = True
                break
        time.sleep(0.5)
    
    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()

    print("Serial output:")
    print(output)

    if not success:
        print("Error: Two BOGKERNEL_VERIFY_END markers not found in serial output")
        return 1

    # Parse verification runs
    runs = []
    lines = output.splitlines()
    in_run = False
    current_run = {}

    for line in lines:
        if line == "BOGKERNEL_VERIFY_BEGIN":
            in_run = True
            current_run = {}
        elif line == "BOGKERNEL_VERIFY_END":
            in_run = False
            runs.append(current_run)
        elif in_run and "=" in line:
            key, val = line.split("=", 1)
            current_run[key.lower()] = val

    if len(runs) < 2:
        print(f"Error: Expected at least 2 verification runs, found {len(runs)}")
        return 1

    run_pos = runs[0]
    run_neg = runs[1]

    # Validate Run 1 (Positive)
    expected_hash = "3457c19c980b8b9e58ac5957d712cbdb9f2d887e19642ac5eace426cf39783e3"
    assert run_pos.get("payload_present") == "true", "Run 1 payload present mismatch"
    assert run_pos.get("expected_hash") == expected_hash, "Run 1 expected hash mismatch"
    assert run_pos.get("actual_hash") == expected_hash, "Run 1 actual hash mismatch"
    assert run_pos.get("hash_match") == "true", "Run 1 hash match mismatch"
    assert run_pos.get("data_accepted") == "true", "Run 1 data accepted mismatch"
    assert run_pos.get("data_rejected") == "false", "Run 1 data rejected mismatch"
    assert run_pos.get("execution_status") == "completed", "Run 1 execution status mismatch"

    # Validate Run 2 (Negative)
    wrong_hash = "0000000000000000000000000000000000000000000000000000000000000000"
    assert run_neg.get("payload_present") == "true", "Run 2 payload present mismatch"
    assert run_neg.get("expected_hash") == wrong_hash, "Run 2 expected hash mismatch"
    assert run_neg.get("actual_hash") == expected_hash, "Run 2 actual hash mismatch"
    assert run_neg.get("hash_match") == "false", "Run 2 hash match mismatch"
    assert run_neg.get("data_accepted") == "false", "Run 2 data accepted mismatch"
    assert run_neg.get("data_rejected") == "true", "Run 2 data rejected mismatch"
    assert run_neg.get("execution_status") == "completed", "Run 2 execution status mismatch"

    receipt = {
        "format": "BOGKERNEL-native-verify-accept-receipt-18.0",
        "execution_status": "completed",
        "platform": "qemu",
        "verify_positive": run_pos,
        "verify_negative": run_neg,
        "serial_output": output,
    }

    RECEIPT_PATH.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(f"Receipt written to {RECEIPT_PATH}")
    print("v18 Native Verify/Accept Proof PASSED")
    return 0

if __name__ == "__main__":
    exit(main())
