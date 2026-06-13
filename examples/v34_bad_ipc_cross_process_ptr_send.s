.intel_syntax noprefix
.code32
.global _start
_start:
    mov ebx, 2
    mov ecx, 0x00800000
    mov edx, 4
    xor esi, esi
    mov eax, 14
    int 0x80
    mov eax, 6
    xor ebx, ebx
    int 0x80
