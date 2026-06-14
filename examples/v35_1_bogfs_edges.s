.intel_syntax noprefix
.code32
.global _start
_start:
    call here
here:
    pop edi

    # Zero-length writes are explicitly rejected.
    mov ebx, edi
    add ebx, (shared_path - here)
    mov ecx, 16
    mov edx, edi
    add edx, (payload_a - here)
    xor esi, esi
    mov eax, 17
    int 0x80

    # Exact maximum succeeds by replacing the existing full-size file.
    mov ebx, edi
    add ebx, (fill_path - here)
    mov ecx, 14
    mov edx, edi
    add edx, (max_payload - here)
    mov esi, 64
    mov eax, 17
    int 0x80

    # Maximum plus one rejects.
    mov ebx, edi
    add ebx, (fill_path - here)
    mov ecx, 14
    mov edx, edi
    add edx, (max_payload - here)
    mov esi, 65
    mov eax, 17
    int 0x80

    # Repeated writes deterministically advance shared.bin from v1 to v3.
    mov ebx, edi
    add ebx, (shared_path - here)
    mov ecx, 16
    mov edx, edi
    add edx, (payload_a - here)
    mov esi, 8
    mov eax, 17
    int 0x80

    mov ebx, edi
    add ebx, (shared_path - here)
    mov ecx, 16
    mov edx, edi
    add edx, (payload_b - here)
    mov esi, 8
    mov eax, 17
    int 0x80

    # Stat committed metadata before a failed replacement.
    mov ebx, edi
    add ebx, (shared_path - here)
    mov ecx, 16
    mov edx, edi
    sub edx, (here - _start)
    add edx, 0x7000
    mov esi, 40
    mov eax, 19
    int 0x80

    # Read committed bytes before a failed replacement.
    mov ebx, edi
    add ebx, (shared_path - here)
    mov ecx, 16
    mov edx, edi
    sub edx, (here - _start)
    add edx, 0x7080
    mov esi, 64
    mov eax, 18
    int 0x80

    # Total storage is full enough that replacing shared.bin with 64 bytes fails.
    mov ebx, edi
    add ebx, (shared_path - here)
    mov ecx, 16
    mov edx, edi
    add edx, (max_payload - here)
    mov esi, 64
    mov eax, 17
    int 0x80

    # Stat and read must still expose payload_b at version 3.
    mov ebx, edi
    add ebx, (shared_path - here)
    mov ecx, 16
    mov edx, edi
    sub edx, (here - _start)
    add edx, 0x7040
    mov esi, 40
    mov eax, 19
    int 0x80

    mov ebx, edi
    add ebx, (shared_path - here)
    mov ecx, 16
    mov edx, edi
    sub edx, (here - _start)
    add edx, 0x70c0
    mov esi, 64
    mov eax, 18
    int 0x80

    mov ebx, edx
    mov ecx, eax
    mov eax, 8
    int 0x80

    # Alias, protected path, full table, and cross-process pointer attempts.
    mov ebx, edi
    add ebx, (alias_path - here)
    mov ecx, 24
    mov edx, edi
    add edx, (payload_a - here)
    mov esi, 8
    mov eax, 17
    int 0x80

    mov ebx, edi
    add ebx, (system_path - here)
    mov ecx, 14
    mov edx, edi
    add edx, (payload_a - here)
    mov esi, 8
    mov eax, 17
    int 0x80

    mov ebx, edi
    add ebx, (new_path - here)
    mov ecx, 13
    mov edx, edi
    add edx, (payload_a - here)
    mov esi, 8
    mov eax, 17
    int 0x80

    mov ebx, edi
    add ebx, (shared_path - here)
    mov ecx, 16
    mov edx, 0x00800000
    mov esi, 8
    mov eax, 17
    int 0x80

    mov eax, 6
    xor ebx, ebx
    int 0x80

shared_path:
    .ascii "/data/shared.bin"
fill_path:
    .ascii "/data/fill.bin"
alias_path:
    .ascii "/data/../data/shared.bin"
system_path:
    .ascii "/system/status"
new_path:
    .ascii "/data/new.bin"
payload_a:
    .ascii "AUDIT-A!"
payload_b:
    .ascii "AUDIT-B!"
max_payload:
    .fill 64, 1, 0x4d
