import json
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KERNEL_DIR = ROOT / "kernel"
ARTIFACTS_DIR = ROOT / "artifacts"
RECEIPT_PATH = ARTIFACTS_DIR / "native_app_bundle_receipt.json"

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
    serial_log = ARTIFACTS_DIR / "bogkernel_app_bundle_serial.log"
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
            # We want to see two BOGKERNEL_APP_BUNDLE_END markers
            if output.count("BOGKERNEL_APP_BUNDLE_END") >= 2:
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
        print("Error: Two BOGKERNEL_APP_BUNDLE_END markers not found in serial output")
        return 1

    # Parse verification runs
    runs = []
    lines = output.splitlines()
    in_run = False
    current_run = {}

    for line in lines:
        if line == "BOGKERNEL_APP_BUNDLE_BEGIN":
            in_run = True
            current_run = {}
        elif line == "BOGKERNEL_APP_BUNDLE_END":
            in_run = False
            runs.append(current_run)
        elif in_run and "=" in line:
            key, val = line.split("=", 1)
            current_run[key.lower()] = val

    if len(runs) < 2:
        print(f"Error: Expected at least 2 app bundle runs, found {len(runs)}")
        return 1

    run_pos = runs[0]
    run_neg = runs[1]

    # Validate Run 1 (Positive)
    expected_hash = "9d34149fbd1fe777eb238799054c8cbfbce372255f219f8740838def9bfd02db"
    assert run_pos.get("app_name") == "hello-bogos", "Run 1 app name mismatch"
    assert run_pos.get("app_version") == "19.0.0", "Run 1 app version mismatch"
    assert run_pos.get("app_present") == "true", "Run 1 app present mismatch"
    assert run_pos.get("app_hash_expected") == expected_hash, "Run 1 expected hash mismatch"
    assert run_pos.get("app_hash_actual") == expected_hash, "Run 1 actual hash mismatch"
    assert run_pos.get("app_hash_match") == "true", "Run 1 hash match mismatch"
    assert run_pos.get("app_accepted") == "true", "Run 1 app accepted mismatch"
    assert run_pos.get("app_rejected") == "false", "Run 1 app rejected mismatch"
    assert run_pos.get("app_execution_started") == "true", "Run 1 app execution started mismatch"
    assert run_pos.get("app_execution_status") == "completed", "Run 1 app execution status mismatch"
    assert run_pos.get("app_halted") == "true", "Run 1 app halted mismatch"

    # Validate Run 2 (Negative)
    wrong_hash = "0000000000000000000000000000000000000000000000000000000000000000"
    assert run_neg.get("app_name") == "bad-hello-bogos", "Run 2 app name mismatch"
    assert run_neg.get("app_version") == "19.0.0", "Run 2 app version mismatch"
    assert run_neg.get("app_present") == "true", "Run 2 app present mismatch"
    assert run_neg.get("app_hash_expected") == wrong_hash, "Run 2 expected hash mismatch"
    assert run_neg.get("app_hash_actual") == expected_hash, "Run 2 actual hash mismatch"
    assert run_neg.get("app_hash_match") == "false", "Run 2 hash match mismatch"
    assert run_neg.get("app_accepted") == "false", "Run 2 app accepted mismatch"
    assert run_neg.get("app_rejected") == "true", "Run 2 app rejected mismatch"
    assert run_neg.get("app_execution_started") == "false", "Run 2 app execution started mismatch"
    assert run_neg.get("app_execution_status") == "rejected", "Run 2 app execution status mismatch"
    assert run_neg.get("app_halted") == "false", "Run 2 app halted mismatch"

    receipt = {
        "format": "BOGKERNEL-native-app-bundle-receipt-19.0",
        "execution_status": "completed",
        "platform": "qemu",
        "verify_positive": run_pos,
        "verify_negative": run_neg,
        "serial_output": output,
    }

    RECEIPT_PATH.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(f"Receipt written to {RECEIPT_PATH}")
    print("v19 Native Verified Embedded App Bundle Proof PASSED")
    return 0

if __name__ == "__main__":
    exit(main())
