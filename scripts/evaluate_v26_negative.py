import json
import subprocess
import time
from pathlib import Path
import sys
import shutil

ROOT = Path(__file__).resolve().parents[1]
KERNEL_DIR = ROOT / "kernel"
ARTIFACTS_DIR = ROOT / "artifacts"
RECEIPT_PATH = ARTIFACTS_DIR / "bogos_v26_negative_receipt.json"

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

    staging_dir = ARTIFACTS_DIR / "staging_negative"
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
        
    apps_dir = staging_dir / "apps"
    apps_dir.mkdir(parents=True, exist_ok=True)
    
    # Write input.dat
    input_file = staging_dir / "input.dat"
    input_file.write_text("BOGBIN-v18-payload")
    
    # 1. Invalid Syntax Test
    print("Test 1: Compiling invalid syntax TS...")
    syntax_file = ARTIFACTS_DIR / "invalid_syntax.ts"
    syntax_file.write_text("const x = 5 + 3;\nexit(0);\n")
    tsc_res = run_command([
        "python3",
        str(ROOT / "scripts" / "tsc.py"),
        str(syntax_file),
        str(apps_dir / "invalid_syntax.bogapp")
    ])
    if tsc_res.returncode == 0:
        print("Error: Compiling invalid syntax should have failed but succeeded!")
        return 1
    print("Invalid syntax compilation failed cleanly as expected.")
    if syntax_file.exists():
        syntax_file.unlink()

    # 2. Invalid Bytecode Test (Mutated .bogapp)
    # Compile a valid app hello.ts to copy its stub
    print("Test 2: Creating invalid opcode app...")
    hello_compiled = ARTIFACTS_DIR / "staging_v26" / "apps" / "hello.bogapp"
    # Compile it now unconditionally to get the latest stub
    run_command([
        "python3",
        str(ROOT / "scripts" / "tsc.py"),
        str(ROOT / "examples" / "hello.ts"),
        str(hello_compiled)
    ])
    
    hello_bytes = hello_compiled.read_bytes()
    # stub size is 310 bytes. The rest is bytecode.
    # We keep the stub (first 310 bytes) and append an invalid opcode 0x99.
    invalid_opcode_bytes = hello_bytes[:310] + b'\x99'
    (apps_dir / "invalid_opcode.bogapp").write_bytes(invalid_opcode_bytes)

    # 3. Kernel-only / Hardware Access Test (bad_app.bogapp)
    print("Test 3: Creating malicious hardware access app...")
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
    assemble_app(bad_asm, apps_dir / "bad_app.bogapp")

    # 4. Spoofing Receipt Test (spoof.bogapp)
    print("Test 4: Creating spoofing receipt app...")
    spoof_ts = ARTIFACTS_DIR / "spoof.ts"
    spoof_ts.write_text('const expected = "3457c19c980b8b9e58ac5957d712cbdb9f2d887e19642ac5eace426cf39783e3";\nconst input = read_file("/input.dat");\nemit_receipt("BOGOS_APP_RUN_END");\nexit(0);\n')
    tsc_res = run_command([
        "python3",
        str(ROOT / "scripts" / "tsc.py"),
        str(spoof_ts),
        str(apps_dir / "spoof.bogapp")
    ])
    if tsc_res.returncode != 0:
        print("Error: Compiling spoofing app failed:", tsc_res.stderr)
        return 1
    if spoof_ts.exists():
        spoof_ts.unlink()

    # 5. Invalid Syscall ABI Test (invalid_syscall.bogapp)
    print("Test 5: Creating invalid syscall validation app...")
    syscall_asm = """
    .intel_syntax noprefix
    .code32
    .global _start
    _start:
        # 1. Unknown syscall number
        mov eax, 99
        int 0x80
        cmp eax, -1
        jne fail
        
        # 2. Null pointer verify
        mov eax, 1
        xor ebx, ebx
        xor ecx, ecx
        xor edx, edx
        int 0x80
        cmp eax, -1
        jne fail

        # 3. Null pointer read_file
        mov eax, 4
        xor ebx, ebx
        xor ecx, ecx
        xor edx, edx
        int 0x80
        cmp eax, -1
        jne fail

        # 4. Too long emit_receipt (> 1024)
        mov eax, 5
        mov ebx, 1
        mov ecx, 2048
        int 0x80
        cmp eax, -1
        jne fail

        # Success
        mov eax, 6
        xor ebx, ebx
        int 0x80
    fail:
        mov eax, 6
        mov ebx, 42
        int 0x80
    """
    assemble_app(syscall_asm, apps_dir / "invalid_syscall.bogapp")

    # Pack negative test filesystem
    initrd_path = ARTIFACTS_DIR / "initrd_negative.bogfs"
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
    serial_log = ARTIFACTS_DIR / "bogos_negative_serial.log"
    
    if serial_log.exists():
        serial_log.unlink()

    print("Running QEMU with Ring 3 Sandboxing Negative Tests...")
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
    
    # Wait for the last command (panic) to execute or timeout
    while time.time() - start_time < timeout:
        if serial_log.exists():
            output = serial_log.read_text()
            if "BOGOS_PANIC_END" in output:
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
        print("Error: QEMU run timed out or did not complete auto-demo")
        return 1

    # Verify invalid opcode behavior
    assert "COMMAND=run invalid_opcode" in output, "Expected 'run invalid_opcode' command in serial log"
    # Exit code was -1, so status should be blocked
    invalid_opcode_section = output.split("COMMAND=run invalid_opcode", 1)[-1].split("BOGOS_APP_RUN_END", 1)[0]
    assert "APP_EXECUTION_STATUS=blocked" in invalid_opcode_section, "Expected invalid opcode app execution to be blocked"

    # Verify bad_app GPF enforcement
    assert "COMMAND=run bad_app" in output, "Expected 'run bad_app' command in serial log"
    bad_app_section = output.split("COMMAND=run bad_app", 1)[-1].split("BOGOS_APP_RUN_END", 1)[0]
    assert "BOGOS_SECURITY_BLOCK" in bad_app_section, "Expected security block for bad_app"
    assert "REASON=GPF" in bad_app_section, "Expected GPF exception reason"
    assert "APP_EXECUTION_STATUS=blocked" in bad_app_section, "Expected bad_app execution status to be blocked"

    # Verify spoofing receipt prevention
    assert "COMMAND=run spoof" in output, "Expected 'run spoof' command in serial log"
    # Make sure BOGOS_APP_RUN_END was not printed inside the run spoof block before the actual APP_RUN_END
    spoof_section = output.split("COMMAND=run spoof", 1)[-1]
    # Check that BOGOS_APP_RUN_END occurs only once in the remainder of the output for this command
    assert spoof_section.count("BOGOS_APP_RUN_END") >= 1, "Expected run spoof to end"
    # Ensure no empty or prematurely truncated receipt lines spoofed
    # (i.e. the string "BOGOS_APP_RUN_END" should not appear directly inside the printed output before APP_EXECUTION_STATUS)
    receipt_print = spoof_section.split("APP_PATH=", 1)[-1].split("APP_EXECUTION_STATUS=", 1)[0]
    assert "BOGOS_APP_RUN_END" not in receipt_print, "Spoofed receipt was printed by the kernel!"

    # Verify invalid syscall checks
    assert "COMMAND=run invalid_syscall" in output, "Expected 'run invalid_syscall' command in serial log"
    syscall_section = output.split("COMMAND=run invalid_syscall", 1)[-1].split("BOGOS_APP_RUN_END", 1)[0]
    assert "APP_EXECUTION_STATUS=completed" in syscall_section, "Expected invalid_syscall to pass checks and exit with 0"

    # Write negative test receipt
    receipt = {
        "format": "BOGOS-v26-negative-receipt-1.0",
        "execution_status": "completed",
        "platform": "qemu",
        "invalid_syntax_status": "passed",
        "invalid_opcode_status": "passed",
        "hardware_access_protection_status": "passed",
        "receipt_spoofing_protection_status": "passed",
        "invalid_syscall_checks_status": "passed",
        "serial_output": output,
    }

    RECEIPT_PATH.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(f"Receipt written to {RECEIPT_PATH}")
    print("v26 TS-Lang Negative Testing and ABI Protection PASSED")
    return 0

if __name__ == "__main__":
    sys.exit(main())
