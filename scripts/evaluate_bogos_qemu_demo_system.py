import json
import subprocess
import time
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
KERNEL_DIR = ROOT / "kernel"
ARTIFACTS_DIR = ROOT / "artifacts"
RECEIPT_PATH = ARTIFACTS_DIR / "bogos_qemu_demo_system_receipt.json"

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
    serial_log = ARTIFACTS_DIR / "bogos_qemu_demo_system_serial.log"
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
    timeout = 15
    output = ""
    success = False
    
    while time.time() - start_time < timeout:
        if serial_log.exists():
            output = serial_log.read_text()
            # We want to see BOGOS_V20_END and two BOGOS_APP_RUN_END markers
            if "BOGOS_V20_END" in output and output.count("BOGOS_APP_RUN_END") >= 2:
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
        print("Error: Required markers not found in serial output")
        return 1

    # Parse boot markers
    v20_info = {}
    in_v20 = False
    for line in output.splitlines():
        if line == "BOGOS_V20_BEGIN":
            in_v20 = True
        elif line == "BOGOS_V20_END":
            in_v20 = False
        elif in_v20 and "=" in line:
            key, val = line.split("=", 1)
            v20_info[key.lower()] = val

    # Verify boot info
    assert v20_info.get("version") == "20.0.0", "v20 version mismatch"
    assert v20_info.get("vga_text_online") == "true", "vga online mismatch"
    assert v20_info.get("shell_online") == "true", "shell online mismatch"
    assert v20_info.get("embedded_table_present") == "true", "table present mismatch"
    assert v20_info.get("pseudo_file_count") == "4", "file count mismatch"
    assert v20_info.get("verified_app_count") == "1", "verified count mismatch"
    assert v20_info.get("rejected_app_count") == "1", "rejected count mismatch"
    assert v20_info.get("auto_demo_supported") == "true", "auto-demo mismatch"

    # Parse app runs
    runs = []
    lines = output.splitlines()
    in_run = False
    current_run = {}

    for line in lines:
        if line == "BOGOS_APP_RUN_BEGIN":
            in_run = True
            current_run = {}
        elif line == "BOGOS_APP_RUN_END":
            in_run = False
            runs.append(current_run)
        elif in_run and "=" in line:
            key, val = line.split("=", 1)
            current_run[key.lower()] = val

    # We expect at least 2 runs: hello and bad-hello
    run_hello = None
    run_bad_hello = None
    for r in runs:
        if r.get("command") == "run hello":
            run_hello = r
        elif r.get("command") == "run bad-hello":
            run_bad_hello = r

    assert run_hello is not None, "run hello receipt missing"
    assert run_bad_hello is not None, "run bad-hello receipt missing"

    # Verify accepted hello app
    assert run_hello.get("app_path") == "/apps/hello.bogapp", "hello path mismatch"
    assert run_hello.get("app_name") == "hello-bogos", "hello name mismatch"
    assert run_hello.get("app_present") == "true", "hello present mismatch"
    assert run_hello.get("app_hash_match") == "true", "hello hash match mismatch"
    assert run_hello.get("app_accepted") == "true", "hello accepted mismatch"
    assert run_hello.get("app_rejected") == "false", "hello rejected mismatch"
    assert run_hello.get("app_execution_started") == "true", "hello started mismatch"
    assert run_hello.get("app_output_event") == "hello_from_verified_bogos_app", "hello output mismatch"
    assert run_hello.get("app_execution_status") == "completed", "hello status mismatch"
    assert run_hello.get("app_halted") == "true", "hello halted mismatch"

    # Verify rejected bad-hello app
    assert run_bad_hello.get("app_path") == "/apps/bad-hello.bogapp", "bad-hello path mismatch"
    assert run_bad_hello.get("app_name") == "bad-hello-bogos", "bad-hello name mismatch"
    assert run_bad_hello.get("app_present") == "true", "bad-hello present mismatch"
    assert run_bad_hello.get("app_hash_match") == "false", "bad-hello hash match mismatch"
    assert run_bad_hello.get("app_accepted") == "false", "bad-hello accepted mismatch"
    assert run_bad_hello.get("app_rejected") == "true", "bad-hello rejected mismatch"
    assert run_bad_hello.get("app_execution_started") == "false", "bad-hello started mismatch"
    assert run_bad_hello.get("app_output_event") == "none", "bad-hello output mismatch"
    assert run_bad_hello.get("app_execution_status") == "rejected", "bad-hello status mismatch"
    assert run_bad_hello.get("app_halted") == "false", "bad-hello halted mismatch"

    receipt = {
        "format": "BOGOS-v20-demo-receipt-1.0",
        "execution_status": "completed",
        "platform": "qemu",
        "v20_boot_info": v20_info,
        "run_hello": run_hello,
        "run_bad_hello": run_bad_hello,
        "serial_output": output,
    }

    RECEIPT_PATH.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(f"Receipt written to {RECEIPT_PATH}")
    print("v20 BogOS QEMU Demo System PASSED")
    return 0

if __name__ == "__main__":
    exit(main())
