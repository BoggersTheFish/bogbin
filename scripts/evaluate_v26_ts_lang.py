import json
import subprocess
import time
from pathlib import Path
import sys
import shutil

ROOT = Path(__file__).resolve().parents[1]
KERNEL_DIR = ROOT / "kernel"
ARTIFACTS_DIR = ROOT / "artifacts"
RECEIPT_PATH = ARTIFACTS_DIR / "bogos_v26_ts_lang_receipt.json"

def run_command(cmd, cwd=None):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)

def main():
    print("Checking dependencies...")
    for tool in ["cargo", "qemu-system-i386", "as", "objcopy"]:
        if subprocess.run(["which", tool], capture_output=True).returncode != 0:
            print(f"Error: {tool} not found in PATH")
            return 1

    staging_dir = ARTIFACTS_DIR / "staging_v26"
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
        
    apps_dir = staging_dir / "apps"
    apps_dir.mkdir(parents=True, exist_ok=True)
    
    # Write input.dat
    input_file = staging_dir / "input.dat"
    input_file.write_text("BOGBIN-v18-payload")
    
    print("Compiling hello.ts to hello.bogapp...")
    tsc_res = run_command([
        "python3",
        str(ROOT / "scripts" / "tsc.py"),
        str(ROOT / "examples" / "hello.ts"),
        str(apps_dir / "hello.bogapp")
    ])
    if tsc_res.returncode != 0:
        print("Compilation failed:", tsc_res.stderr)
        return 1
    print(tsc_res.stdout.strip())

    import re
    import hashlib
    
    hello_ts_hash = re.search(r'hello.ts hash:\s*([0-9a-f]+)', tsc_res.stdout).group(1)
    bytecode_hash = re.search(r'emitted bytecode hash:\s*([0-9a-f]+)', tsc_res.stdout).group(1)
    stub_hash = re.search(r'interpreter stub hash:\s*([0-9a-f]+)', tsc_res.stdout).group(1)
    bundle_hash = re.search(r'final app bundle hash:\s*([0-9a-f]+)', tsc_res.stdout).group(1)

    # Pack filesystem
    initrd_path = ARTIFACTS_DIR / "initrd_v26.bogfs"
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
    serial_log = ARTIFACTS_DIR / "bogos_v26_serial.log"
    
    if serial_log.exists():
        serial_log.unlink()

    print("Running QEMU with Ring 3 TS-Lang compilation test...")
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
            # We look for hello on its own line and completed status after COMMAND=run hello
            if "\nhello\n" in output and "COMMAND=run hello" in output:
                after_run = output.split("COMMAND=run hello", 1)[-1]
                if "APP_EXECUTION_STATUS=completed" in after_run:
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
        print("Error: hello receipt or completed run hello status not found in serial output")
        return 1

    assert "\nhello\n" in output, "Expected 'hello' receipt on its own line in serial log"
    assert "COMMAND=run hello" in output, "Expected 'run hello' command in serial log"
    
    # Verify completed status specifically under run hello block
    after_run = output.split("COMMAND=run hello", 1)[-1]
    assert "APP_EXECUTION_STATUS=completed" in after_run, "Expected completed app execution status for run hello"

    # Compute hashes of generated assets
    initrd_hash = hashlib.sha256(initrd_path.read_bytes()).hexdigest()
    serial_hash = hashlib.sha256(serial_log.read_bytes()).hexdigest()

    # Write receipt
    receipt = {
        "format": "BOGOS-v26-ts-lang-receipt-1.0",
        "execution_status": "completed",
        "platform": "qemu",
        "hello_ts_status": "passed",
        "hello_ts_hash": hello_ts_hash,
        "emitted_bytecode_hash": bytecode_hash,
        "interpreter_stub_hash": stub_hash,
        "final_app_bundle_hash": bundle_hash,
        "bogfs_image_hash": initrd_hash,
        "qemu_serial_receipt_hash": serial_hash,
        "serial_output": output,
    }

    RECEIPT_PATH.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(f"Receipt written to {RECEIPT_PATH}")
    print("v26 TS-Lang MVP PASSED")
    return 0

if __name__ == "__main__":
    sys.exit(main())
