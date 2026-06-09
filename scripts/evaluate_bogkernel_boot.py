import json
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KERNEL_DIR = ROOT / "kernel" / "bogk-kernel"
ARTIFACTS_DIR = ROOT / "artifacts"
RECEIPT_PATH = ARTIFACTS_DIR / "bogkernel_boot_receipt.json"

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
        cwd=ROOT / "kernel"
    )
    if build_result.returncode != 0:
        print("Build failed:")
        print(build_result.stderr)
        return 1

    kernel_path = ROOT / "kernel" / "target" / "i686-unknown-linux-musl" / "debug" / "bogk-kernel"
    serial_log = ARTIFACTS_DIR / "bogkernel_serial.log"
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    print("Auditing kernel artifact...")
    elf_audit = {}
    
    # 1. ELF Header Check
    header_result = run_command(["readelf", "-h", str(kernel_path)])
    if header_result.returncode == 0:
        for line in header_result.stdout.splitlines():
            if "Class:" in line:
                elf_audit["kernel_elf_class"] = line.split(":", 1)[1].strip()
            elif "Machine:" in line:
                elf_audit["kernel_machine"] = line.split(":", 1)[1].strip()
            elif "Entry point address:" in line:
                elf_audit["kernel_entry_point"] = line.split(":", 1)[1].strip()

    # 2. Dynamic Interpreter Check
    interp_result = run_command(["readelf", "-l", str(kernel_path)])
    elf_audit["has_dynamic_interpreter"] = "INTERP" in interp_result.stdout

    # 3. Dynamic Section Check (should be empty for freestanding)
    dynamic_result = run_command(["readelf", "-d", str(kernel_path)])
    elf_audit["has_dynamic_section"] = "Dynamic section at offset" in dynamic_result.stdout

    # 4. Undefined Symbols Check (should be empty besides maybe intrinsic builtins)
    nm_result = run_command(["nm", "-u", str(kernel_path)])
    elf_audit["undefined_symbols"] = nm_result.stdout.strip().splitlines()

    print("Running QEMU...")
    qemu_cmd = [
        "qemu-system-i386",
        "-kernel", str(kernel_path),
        "-serial", f"file:{serial_log}",
        "-display", "none",
    ]
    
    # Run QEMU in the background
    process = subprocess.Popen(qemu_cmd)
    
    # Wait for output
    start_time = time.time()
    timeout = 10
    output = ""
    success = False
    
    while time.time() - start_time < timeout:
        if serial_log.exists():
            output = serial_log.read_text()
            if "BOGKERNEL_BOOT_END" in output:
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

    receipt = {
        "format": "BOGKERNEL-boot-receipt-16.0",
        "execution_status": "completed" if success else "failed",
        "platform": "qemu",
        "elf_audit": elf_audit,
        "serial_markers_verified": success,
        "serial_output": output,
    }

    RECEIPT_PATH.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(f"Receipt written to {RECEIPT_PATH}")

    if not success:
        print("Error: Boot markers not found in serial output")
        return 1

    print("v16 Boot Proof PASSED")
    return 0

if __name__ == "__main__":
    exit(main())
