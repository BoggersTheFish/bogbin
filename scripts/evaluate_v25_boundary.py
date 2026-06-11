import json
import subprocess
import time
from pathlib import Path
import sys
import shutil

ROOT = Path(__file__).resolve().parents[1]
KERNEL_DIR = ROOT / "kernel"
ARTIFACTS_DIR = ROOT / "artifacts"
RECEIPT_PATH = ARTIFACTS_DIR / "bogos_v25_boundary_receipt.json"

def run_command(cmd, cwd=None):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)

def assemble_app(asm_code, dest_path):
    temp_s = dest_path.with_suffix(".s")
    temp_o = dest_path.with_suffix(".o")
    temp_s.write_text(asm_code)
    
    # Assemble using system GNU Assembler
    res = run_command(["as", "--32", "-o", str(temp_o), str(temp_s)])
    if res.returncode != 0:
        raise Exception(f"Assembly failed: {res.stderr}")
        
    # Extract raw binary
    res = run_command(["objcopy", "-O", "binary", str(temp_o), str(dest_path)])
    if res.returncode != 0:
        raise Exception(f"Objcopy failed: {res.stderr}")
        
    # Cleanup
    if temp_s.exists(): temp_s.unlink()
    if temp_o.exists(): temp_o.unlink()

def main():
    print("Checking dependencies...")
    for tool in ["cargo", "qemu-system-i386", "as", "objcopy"]:
        if subprocess.run(["which", tool], capture_output=True).returncode != 0:
            print(f"Error: {tool} not found in PATH")
            return 1

    staging_dir = ARTIFACTS_DIR / "staging_v25"
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    apps_dir = staging_dir / "apps"
    apps_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Good application: Emits a receipt, exits normally.
    good_asm = """
    .intel_syntax noprefix
    .code32
    .global _start
    _start:
        jmp msg_def
    msg_ret:
        pop ebx
        mov ecx, 12         # len("good_receipt")
        mov eax, 5          # sys_emit_receipt
        int 0x80
        
        mov eax, 6          # sys_exit
        xor ebx, ebx
        int 0x80
    msg_def:
        call msg_ret
        .ascii "good_receipt"
    """
    
    # 2. Bad application: Attempts direct I/O, triggers GPF.
    bad_asm = """
    .intel_syntax noprefix
    .code32
    .global _start
    _start:
        mov dx, 0x3f8
        mov al, 0x41
        out dx, al          # Illegal operation in Ring 3 -> GPF!
        
        mov eax, 6          # sys_exit
        xor ebx, ebx
        int 0x80
    """
    
    print("Assembling test applications...")
    assemble_app(good_asm, apps_dir / "good_app.bogapp")
    assemble_app(bad_asm, apps_dir / "bad_app.bogapp")

    # Pack filesystem
    initrd_path = ARTIFACTS_DIR / "initrd_v25.bogfs"
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
    serial_log = ARTIFACTS_DIR / "bogos_v25_serial.log"
    
    if serial_log.exists():
        serial_log.unlink()

    print("Running QEMU with Ring 3 sandboxing test...")
    qemu_cmd = [
        "qemu-system-i386",
        "-kernel", str(kernel_path),
        "-initrd", str(initrd_path),
        "-serial", f"file:{serial_log}",
        "-display", "none",
    ]
    
    process = subprocess.Popen(qemu_cmd)
    
    # Let it run auto demo commands or we can inject keyboard/serial if we want,
    # but wait! Since we replaced run_app_command, does the auto demo run hello and bad-hello?
    # Yes, the auto demo commands are:
    # "help", "status", "ls", "cat /system/status", "cat /system/memory", "cat /receipts/last",
    # "run hello", "run bad-hello", "clear", "panic"
    # But wait! In v25, we have good_app and bad_app!
    # How does the auto-demo run good_app and bad_app?
    # It does not run them automatically because they are not in the AUTO_DEMO_COMMANDS list!
    # Wait, can we feed "run good_app" and "run bad_app" directly via QEMU serial input or stdin?
    # Yes! In our subprocess, we can write commands directly to QEMU's stdin if we redirect it,
    # OR we can just add "run good_app" and "run bad_app" to the auto demo list in main.rs!
    # Adding them to AUTO_DEMO_COMMANDS in main.rs is much simpler and more robust, since QEMU
    # doesn't need interactive redirection!
    # Let's check: yes, we can add them to the AUTO_DEMO_COMMANDS in main.rs!
    
    start_time = time.time()
    timeout = 15
    output = ""
    success = False
    
    while time.time() - start_time < timeout:
        if serial_log.exists():
            output = serial_log.read_text()
            if "good_receipt" in output and "BOGOS_SECURITY_BLOCK" in output and "BOGOS_PANIC_END" in output:
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
        print("Error: good_receipt or BOGOS_SECURITY_BLOCK not found in serial output")
        return 1

    assert "good_receipt" in output, "Expected good_receipt in serial log"
    assert "BOGOS_SECURITY_BLOCK" in output, "Expected BOGOS_SECURITY_BLOCK in serial log"
    assert "blocked illegal operation receipt" in output, "Expected blocked illegal operation receipt in serial log"
    assert "REASON=GPF" in output, "Expected REASON=GPF in serial log"
    
    # Write receipt
    receipt = {
        "format": "BOGOS-v25-boundary-receipt-1.0",
        "execution_status": "completed",
        "platform": "qemu",
        "good_app_status": "passed",
        "bad_app_status": "blocked",
        "serial_output": output,
    }

    RECEIPT_PATH.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(f"Receipt written to {RECEIPT_PATH}")
    print("v25 User App Boundary and Sandboxing PASSED")
    return 0

if __name__ == "__main__":
    sys.exit(main())
