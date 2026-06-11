import json
import subprocess
import time
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
KERNEL_DIR = ROOT / "kernel"
ARTIFACTS_DIR = ROOT / "artifacts"
RECEIPT_PATH = ARTIFACTS_DIR / "bogos_v22_memory_receipt.json"

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
    serial_log = ARTIFACTS_DIR / "bogos_v22_serial.log"
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
            # We want to see BOGOS MEMORY STATS
            if "BOGOS MEMORY STATS" in output and "BOGOS_PANIC_END" in output:
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
        print("Error: Memory stats or panic markers not found in serial output")
        return 1

    # Parse memory stats
    memory_stats = {}
    in_mem_stats = False
    for line in output.splitlines():
        if line == "BOGOS MEMORY STATS":
            in_mem_stats = True
        elif in_mem_stats and ("=" in line):
            key, val = line.split("=", 1)
            memory_stats[key.lower()] = val
        elif in_mem_stats and (line.strip() == "" or "BOGOS" in line):
            in_mem_stats = False

    print("Parsed Memory Stats:", memory_stats)

    total_allocated_str = memory_stats.get("total_allocated")
    alloc_calls_str = memory_stats.get("alloc_calls")
    
    assert total_allocated_str is not None, "total_allocated missing from memory stats"
    assert alloc_calls_str is not None, "alloc_calls missing from memory stats"
    
    total_allocated = int(total_allocated_str)
    alloc_calls = int(alloc_calls_str)
    
    print(f"Verified total allocated: {total_allocated} bytes")
    print(f"Verified allocation calls: {alloc_calls}")
    
    assert total_allocated > 0, "Expected positive allocated bytes count"
    assert alloc_calls > 0, "Expected positive allocation calls count"

    receipt = {
        "format": "BOGOS-v22-memory-receipt-1.0",
        "execution_status": "completed",
        "platform": "qemu",
        "total_allocated_bytes": total_allocated,
        "allocation_calls_count": alloc_calls,
        "serial_output": output,
    }

    RECEIPT_PATH.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(f"Receipt written to {RECEIPT_PATH}")
    print("v22 BogKernel Memory and Heap PASSED")
    return 0

if __name__ == "__main__":
    exit(main())
