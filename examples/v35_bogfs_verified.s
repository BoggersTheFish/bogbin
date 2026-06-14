.intel_syntax noprefix
.code32
.global _start
_start:
    call here
here:
    pop edi

    mov ebx, edi
    add ebx, (shared_path - here)
    mov ecx, 16
    mov edx, edi
    add edx, (payload - here)
    mov esi, 8
    mov eax, 17
    int 0x80

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

    mov ebx, edi
    add ebx, (shared_path - here)
    mov ecx, 16
    mov edx, edi
    sub edx, (here - _start)
    add edx, 0x7040
    mov esi, 40
    mov eax, 19
    int 0x80

    mov eax, 6
    xor ebx, ebx
    int 0x80

shared_path:
    .ascii "/data/shared.bin"
payload:
    .ascii "V35-DATA"
