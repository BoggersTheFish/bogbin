import json
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KERNEL_DIR = ROOT / "kernel"
ARTIFACTS_DIR = ROOT / "artifacts"
RECEIPT_PATH = ARTIFACTS_DIR / "bogkernel_vm_exec_receipt.json"

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
    serial_log = ARTIFACTS_DIR / "bogkernel_vm_exec_serial.log"
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    print("Auditing kernel artifact...")
    elf_audit = {}
    
    header_result = run_command(["readelf", "-h", str(kernel_path)])
    if header_result.returncode == 0:
        for line in header_result.stdout.splitlines():
            if "Class:" in line:
                elf_audit["kernel_elf_class"] = line.split(":", 1)[1].strip()
            elif "Machine:" in line:
                elf_audit["kernel_machine"] = line.split(":", 1)[1].strip()
            elif "Entry point address:" in line:
                elf_audit["kernel_entry_point"] = line.split(":", 1)[1].strip()

    interp_result = run_command(["readelf", "-l", str(kernel_path)])
    elf_audit["has_dynamic_interpreter"] = "INTERP" in interp_result.stdout

    dynamic_result = run_command(["readelf", "-d", str(kernel_path)])
    elf_audit["has_dynamic_section"] = "Dynamic section at offset" in dynamic_result.stdout

    nm_result = run_command(["nm", "-u", str(kernel_path)])
    elf_audit["undefined_symbols"] = nm_result.stdout.strip().splitlines()

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
    boot_success = False
    vm_exec_success = False
    
    while time.time() - start_time < timeout:
        if serial_log.exists():
            output = serial_log.read_text()
            if "BOGKERNEL_BOOT_END" in output:
                boot_success = True
            if "BOGKERNEL_VM_EXEC_END" in output:
                vm_exec_success = True
            if boot_success and vm_exec_success:
                break
        time.sleep(0.5)
    
    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()

    print("Serial output:")
    print(output)

    # Parse VM execution markers
    vm_results = {}
    for line in output.splitlines():
        if "=" in line and line.startswith("BOGKERNEL_VM_"):
            key, val = line.split("=", 1)
            vm_results[key.replace("BOGKERNEL_VM_", "").lower()] = val
        elif "=" in line:
             key, val = line.split("=", 1)
             vm_results[key.lower()] = val

    receipt = {
        "format": "BOGKERNEL-native-vm-receipt-17.0",
        "execution_status": vm_results.get("execution_status", "failed"),
        "platform": "qemu",
        "elf_audit": elf_audit,
        "boot_markers_verified": boot_success,
        "vm_exec_markers_verified": vm_exec_success,
        "instruction_width": int(vm_results.get("instruction_width", 0)),
        "program_instruction_count": int(vm_results.get("program_instruction_count", 0)),
        "opcodes_executed": vm_results.get("opcodes_executed", ""),
        "halted": vm_results.get("halted") == "true",
        "unsupported_opcode_seen": vm_results.get("unsupported_opcode_seen") == "true",
        "serial_output": output,
    }

    RECEIPT_PATH.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(f"Receipt written to {RECEIPT_PATH}")

    if not (boot_success and vm_exec_success):
        print("Error: Required markers not found in serial output")
        return 1

    if receipt["execution_status"] != "completed":
        print(f"Error: VM execution status is {receipt['execution_status']}")
        return 1

    print("v17 VM Execution Proof PASSED")
    return 0

if __name__ == "__main__":
    exit(main())
