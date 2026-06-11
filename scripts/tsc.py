import sys
import re
import struct
import subprocess
from pathlib import Path

def strip_comments_and_whitespace(content: str) -> list[str]:
    lines = []
    for line in content.splitlines():
        line = re.sub(r'//.*', '', line)
        line = line.strip()
        if line:
            lines.append(line)
    return lines

def compile_to_bytecode(lines: list[str]) -> bytes:
    expected_hash_hex = None
    file_path = None
    accept_msg = None
    receipt_msg = None
    reject_msg = None
    exit_code = 0
    
    for line in lines:
        m = re.match(r'const\s+(\w+)\s*=\s*"([^"]+)";', line)
        if m:
            expected_hash_hex = m.group(2)
            continue
        m = re.match(r'const\s+(\w+)\s*=\s*read_file\("([^"]+)"\);', line)
        if m:
            file_path = m.group(2)
            continue
        m = re.match(r'accept\(\s*"([^"]+)"\s*\);', line)
        if m:
            accept_msg = m.group(1)
            continue
        m = re.match(r'emit_receipt\(\s*"([^"]+)"\s*\);', line)
        if m:
            receipt_msg = m.group(1)
            continue
        m = re.match(r'reject\(\s*"([^"]+)"\s*\);', line)
        if m:
            reject_msg = m.group(1)
            continue
        m = re.match(r'exit\(\s*(\d+)\s*\);', line)
        if m:
            exit_code = int(m.group(1))
            continue

    if not expected_hash_hex or not file_path:
        raise ValueError("Missing expected hash or input file path in TS code")

    expected_hash_bytes = bytes.fromhex(expected_hash_hex)
    if len(expected_hash_bytes) != 32:
        raise ValueError("Expected hash must be a 32-byte hex string")

    # Build bytecode blocks
    b1 = b'\x01' + file_path.encode('utf-8') + b'\x00'
    b2 = b'\x02' + expected_hash_bytes
    b3_placeholder = b'\x03\x00\x00\x00\x00'
    
    b4_accept = b'\x04' + (accept_msg.encode('utf-8') if accept_msg else b'') + b'\x00'
    b4_receipt = b'\x06' + (receipt_msg.encode('utf-8') if receipt_msg else b'') + b'\x00'
    b4_jump_placeholder = b'\x08\x00\x00\x00\x00'
    b4 = b4_accept + b4_receipt + b4_jump_placeholder
    
    b5 = b'\x05' + (reject_msg.encode('utf-8') if reject_msg else b'') + b'\x00'
    b6 = b'\x07' + struct.pack("<I", exit_code)

    offset_b1 = 0
    offset_b2 = offset_b1 + len(b1)
    offset_b3 = offset_b2 + len(b2)
    offset_b4 = offset_b3 + len(b3_placeholder)
    offset_b5 = offset_b4 + len(b4)
    offset_b6 = offset_b5 + len(b5)

    else_offset = offset_b5
    exit_offset = offset_b6

    b3 = b'\x03' + struct.pack("<I", else_offset)
    b4 = b4_accept + b4_receipt + b'\x08' + struct.pack("<I", exit_offset)

    bytecode = b1 + b2 + b3 + b4 + b5 + b6
    return bytecode

def assemble_stub() -> bytes:
    asm_code = """
    .intel_syntax noprefix
    .code32
    .global _start
_start:
    # Get PC
    call get_pc
get_pc:
    pop esi                 # ESI = get_pc
    add esi, (bytecode_start - get_pc)
    
    call get_pc2
get_pc2:
    pop ebp
    sub ebp, (get_pc2 - _start)
    
interpreter_loop:
    movzx eax, byte ptr [esi]
    inc esi
    
    cmp al, 0
    je do_exit
    
    cmp al, 1 # READ_FILE
    je do_read_file
    
    cmp al, 2 # VERIFY
    je do_verify
    
    cmp al, 3 # JUMP_IF_FALSE
    je do_jump_if_false
    
    cmp al, 4 # ACCEPT
    je do_accept
    
    cmp al, 5 # REJECT
    je do_reject
    
    cmp al, 6 # EMIT_RECEIPT
    je do_emit_receipt
    
    cmp al, 7 # EXIT
    je do_exit
    
    cmp al, 8 # JUMP
    je do_jump
    
    jmp do_exit_err

do_read_file:
    mov ebx, esi
find_zero:
    cmp byte ptr [esi], 0
    je found_zero
    inc esi
    jmp find_zero
found_zero:
    inc esi # step over null byte
    
    mov ecx, ebp
    add ecx, 32768
    mov edx, 4096
    mov eax, 4
    int 0x80
    
    mov [ebp + 32764], eax
    jmp interpreter_loop

do_verify:
    mov ebx, ebp
    add ebx, 32768
    mov ecx, [ebp + 32764]
    mov edx, esi
    
    mov eax, 1 # sys_verify
    int 0x80
    
    mov edi, eax
    add esi, 32
    jmp interpreter_loop

do_jump_if_false:
    mov ebx, [esi]
    add esi, 4
    
    cmp edi, 0
    jne interpreter_loop
    
    call get_pc3
get_pc3:
    pop esi
    sub esi, (get_pc3 - bytecode_start)
    add esi, ebx
    jmp interpreter_loop

do_accept:
    mov ebx, esi
find_zero_accept:
    cmp byte ptr [esi], 0
    je found_zero_accept
    inc esi
    jmp find_zero_accept
found_zero_accept:
    inc esi
    
    mov eax, 2 # sys_accept
    int 0x80
    jmp interpreter_loop

do_reject:
    mov ebx, esi
find_zero_reject:
    cmp byte ptr [esi], 0
    je found_zero_reject
    inc esi
    jmp find_zero_reject
found_zero_reject:
    inc esi
    
    mov eax, 3 # sys_reject
    int 0x80
    jmp interpreter_loop

do_emit_receipt:
    mov ebx, esi
    xor ecx, ecx
find_zero_receipt:
    cmp byte ptr [esi], 0
    je found_zero_receipt
    inc esi
    inc ecx
    jmp find_zero_receipt
found_zero_receipt:
    inc esi
    
    mov eax, 5 # sys_emit_receipt
    int 0x80
    jmp interpreter_loop

do_jump:
    mov ebx, [esi]
    add esi, 4
    
    call get_pc4
get_pc4:
    pop esi
    sub esi, (get_pc4 - bytecode_start)
    add esi, ebx
    jmp interpreter_loop

do_exit_err:
    mov ebx, -1 # exit code -1
    mov eax, 6  # sys_exit
    int 0x80

do_exit:
    cmp byte ptr [esi - 1], 7
    jne exit_zero
    mov ebx, [esi]
    jmp do_sys_exit
exit_zero:
    xor ebx, ebx
do_sys_exit:
    mov eax, 6 # sys_exit
    int 0x80

bytecode_start:
    """
    
    temp_s = Path("temp_stub.s")
    temp_o = Path("temp_stub.o")
    temp_bin = Path("temp_stub.bin")
    
    try:
        temp_s.write_text(asm_code)
        res = subprocess.run(["as", "--32", "-o", str(temp_o), str(temp_s)], capture_output=True, text=True)
        if res.returncode != 0:
            raise Exception(f"Assembly failed: {res.stderr}")
            
        res = subprocess.run(["objcopy", "-O", "binary", str(temp_o), str(temp_bin)], capture_output=True, text=True)
        if res.returncode != 0:
            raise Exception(f"Objcopy failed: {res.stderr}")
            
        return temp_bin.read_bytes()
    finally:
        if temp_s.exists(): temp_s.unlink()
        if temp_o.exists(): temp_o.unlink()
        if temp_bin.exists(): temp_bin.unlink()

def main():
    if len(sys.argv) < 3:
        print("Usage: python3 tsc.py <input.ts> <output.bogapp>")
        sys.exit(1)
        
    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])
    
    source_bytes = input_path.read_bytes()
    lines = strip_comments_and_whitespace(source_bytes.decode('utf-8'))
    
    bytecode = compile_to_bytecode(lines)
    stub = assemble_stub()
    
    final_bundle = stub + bytecode
    output_path.write_bytes(final_bundle)
    
    import hashlib
    ts_hash = hashlib.sha256(source_bytes).hexdigest()
    bytecode_hash = hashlib.sha256(bytecode).hexdigest()
    stub_hash = hashlib.sha256(stub).hexdigest()
    bundle_hash = hashlib.sha256(final_bundle).hexdigest()
    
    print(f"Successfully compiled {input_path} to {output_path} (stub size: {len(stub)}, bytecode size: {len(bytecode)})")
    print(f"hello.ts hash: {ts_hash}")
    print(f"emitted bytecode hash: {bytecode_hash}")
    print(f"interpreter stub hash: {stub_hash}")
    print(f"final app bundle hash: {bundle_hash}")

if __name__ == "__main__":
    main()
