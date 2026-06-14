.intel_syntax noprefix
.code32
.global _start
_start:
    call here
here:
    pop edi

    # Bad kernel data pointer.
    mov ebx, edi
    add ebx, (shared_path - here)
    mov ecx, 16
    mov edx, 0x00100000
    mov esi, 4
    mov eax, 17
    int 0x80

    # Oversized write.
    mov ebx, edi
    add ebx, (shared_path - here)
    mov ecx, 16
    mov edx, edi
    add edx, (fill_payload - here)
    mov esi, 65
    mov eax, 17
    int 0x80

    # Read-only destination path.
    mov ebx, edi
    add ebx, (readonly_path - here)
    mov ecx, 18
    mov edx, edi
    add edx, (small_payload - here)
    mov esi, 4
    mov eax, 17
    int 0x80

    # Invalid destination path.
    mov ebx, edi
    add ebx, (invalid_path - here)
    mov ecx, 17
    mov edx, edi
    add edx, (small_payload - here)
    mov esi, 4
    mov eax, 17
    int 0x80

    # Another process's private test page.
    mov ebx, edi
    add ebx, (shared_path - here)
    mov ecx, 16
    mov edx, 0x00800000
    mov esi, 4
    mov eax, 17
    int 0x80

    # Deterministic receipt-hash fault injection.
    mov ebx, edi
    add ebx, (hashfail_path - here)
    mov ecx, 18
    mov edx, edi
    add edx, (small_payload - here)
    mov esi, 4
    mov eax, 17
    int 0x80

    # Fill bounded storage, then prove a larger replacement is rejected.
    mov ebx, edi
    add ebx, (fill_path - here)
    mov ecx, 14
    mov edx, edi
    add edx, (fill_payload - here)
    mov esi, 64
    mov eax, 17
    int 0x80

    mov ebx, edi
    add ebx, (shared_path - here)
    mov ecx, 16
    mov edx, edi
    add edx, (fill_payload - here)
    mov esi, 64
    mov eax, 17
    int 0x80

    # Read the earlier committed value after all rejected writes.
    mov ebx, edi
    add ebx, (shared_path - here)
    mov ecx, 16
    mov edx, edi
    sub edx, (here - _start)
    add edx, 0x7000
    mov esi, 64
    mov eax, 18
    int 0x80

    mov ebx, edx
    mov ecx, eax
    mov eax, 8
    int 0x80

    mov eax, 6
    xor ebx, ebx
    int 0x80

shared_path:
    .ascii "/data/shared.bin"
fill_path:
    .ascii "/data/fill.bin"
readonly_path:
    .ascii "/data/readonly.bin"
hashfail_path:
    .ascii "/data/hashfail.bin"
invalid_path:
    .ascii "/data//shared.bin"
small_payload:
    .ascii "FAIL"
fill_payload:
    .fill 64, 1, 0x46
