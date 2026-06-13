.intel_syntax noprefix
.code32
.global _start
_start:
    call here
here:
    pop edi

    mov ebx, edi
    mov ecx, 1
    mov edx, 0x00100000
    mov eax, 11
    int 0x80

    mov ebx, edi
    mov ecx, 257
    mov eax, 12
    int 0x80

    xor eax, eax
    int 0x80

    mov eax, 255
    int 0x80

    mov ebx, edi
    mov ecx, 1
    mov eax, 5
    int 0x80

    mov eax, 6
    xor ebx, ebx
    int 0x80
