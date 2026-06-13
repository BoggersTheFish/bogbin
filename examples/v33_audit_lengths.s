.intel_syntax noprefix
.code32
.global _start
_start:
    call here
here:
    pop edi

    mov ebx, edi
    xor ecx, ecx
    mov eax, 8
    int 0x80

    mov ebx, edi
    add ebx, (payload - here)
    mov ecx, 256
    mov eax, 8
    int 0x80

    mov ebx, edi
    mov ecx, 257
    mov eax, 8
    int 0x80

    mov eax, 6
    xor ebx, ebx
    int 0x80
payload:
    .fill 256, 1, 0x4d
