.intel_syntax noprefix
.code32
.global _start
_start:
    mov eax, 8
    mov ebx, 0x00800000
    mov ecx, 8
    int 0x80
    mov eax, 6
    xor ebx, ebx
    int 0x80
