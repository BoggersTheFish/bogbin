import json
import subprocess
import time
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
KERNEL_DIR = ROOT / "kernel"
ARTIFACTS_DIR = ROOT / "artifacts"
RECEIPT_PATH = ARTIFACTS_DIR / "bogos_v21_interrupts_receipt.json"

def run_command(cmd, cwd=None, timeout=None):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)

def main():
    print("Checking dependencies...")
    for tool in ["cargo", "qemu-system-i386"]:
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
    serial_log = ARTIFACTS_DIR / "bogos_v21_serial.log"
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
            # We want to see BOGOS_PANIC_BEGIN and BOGOS_PANIC_END
            if "BOGOS_PANIC_BEGIN" in output and "BOGOS_PANIC_END" in output:
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
        print("Error: Panic markers not found in serial output (did interrupts or panic fail?)")
        return 1

    # Parse panic info
    panic_info = {}
    in_panic = False
    for line in output.splitlines():
        if line == "BOGOS_PANIC_BEGIN":
            in_panic = True
        elif line == "BOGOS_PANIC_END":
            in_panic = False
        elif in_panic and "=" in line:
            key, val = line.split("=", 1)
            panic_info[key.lower()] = val

    print("Parsed Panic Info:", panic_info)

    reason = panic_info.get("reason", "")
    assert "manual panic" in reason or "main.rs" in reason, f"Unexpected panic reason: {reason}"
    
    tick_count_str = panic_info.get("tick_count")
    assert tick_count_str is not None, "Tick count missing from panic receipt"
    ticks = int(tick_count_str)
    print(f"Verified timer interrupt ticks count: {ticks}")
    assert ticks > 0, f"Expected positive tick count, got {ticks}"

    receipt = {
        "format": "BOGOS-v21-interrupts-receipt-1.0",
        "execution_status": "completed",
        "platform": "qemu",
        "ticks_recorded": ticks,
        "panic_reason": panic_info.get("reason"),
        "serial_output": output,
    }

    RECEIPT_PATH.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(f"Receipt written to {RECEIPT_PATH}")
    print("v21 BogKernel Interrupt Foundations PASSED")
    return 0

if __name__ == "__main__":
    exit(main())
