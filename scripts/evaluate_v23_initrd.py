import json
import subprocess
import time
from pathlib import Path
import sys
import shutil

ROOT = Path(__file__).resolve().parents[1]
KERNEL_DIR = ROOT / "kernel"
ARTIFACTS_DIR = ROOT / "artifacts"
RECEIPT_PATH = ARTIFACTS_DIR / "bogos_v23_initrd_receipt.json"

def run_command(cmd, cwd=None, timeout=None):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)

def main():
    print("Checking dependencies...")
    for tool in ["cargo", "qemu-system-i386"]:
        if subprocess.run(["which", tool], capture_output=True).returncode != 0:
            print(f"Error: {tool} not found in PATH")
            return 1

    # Prepare staging directory and file
    staging_dir = ARTIFACTS_DIR / "staging"
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True, exist_ok=True)
    
    test_file = staging_dir / "hello.txt"
    test_file.write_text("Hello from BogFS!")
    
    # Pack filesystem
    initrd_path = ARTIFACTS_DIR / "initrd.bogfs"
    print("Packing BogFS...")
    pack_res = run_command(["python3", str(ROOT / "scripts" / "make_bogfs.py"), str(staging_dir), str(initrd_path)])
    if pack_res.returncode != 0:
        print("Packing failed:", pack_res.stderr)
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
    serial_log = ARTIFACTS_DIR / "bogos_v23_serial.log"
    
    if serial_log.exists():
        serial_log.unlink()

    print("Running QEMU with initrd...")
    qemu_cmd = [
        "qemu-system-i386",
        "-kernel", str(kernel_path),
        "-initrd", str(initrd_path),
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
            # We want to see BOGFS_FILE_ACCEPT and PATH=/hello.txt and BOGOS_PANIC_END (from shell shutdown/panic at end of auto demo)
            if "BOGFS_FILE_ACCEPT" in output and "PATH=/hello.txt" in output and "BOGOS_PANIC_END" in output:
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
        print("Error: BOGFS_FILE_ACCEPT or PATH=/hello.txt not found in serial output")
        return 1

    # Check for acceptance of files
    assert "BOGFS_FILE_ACCEPT" in output, "Expected BOGFS_FILE_ACCEPT in log"
    assert "PATH=/hello.txt" in output, "Expected PATH=/hello.txt in log"
    
    # Write receipt
    receipt = {
        "format": "BOGFS-v23-initrd-receipt-1.0",
        "execution_status": "completed",
        "platform": "qemu",
        "files_verified": ["/hello.txt"],
        "serial_output": output,
    }

    RECEIPT_PATH.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(f"Receipt written to {RECEIPT_PATH}")
    print("v23 Initrd / Verified Embedded FS PASSED")
    return 0

if __name__ == "__main__":
    sys.exit(main())
