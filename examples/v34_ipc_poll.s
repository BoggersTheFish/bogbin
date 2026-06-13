.intel_syntax noprefix
.code32
.global _start
_start:
    xor ebx, ebx
    mov ecx, 8
    mov edx, 1
    xor esi, esi
    mov eax, 13
    int 0x80
    mov ebx, eax
    mov eax, 16
    int 0x80
    mov eax, 6
    xor ebx, ebx
    int 0x80
