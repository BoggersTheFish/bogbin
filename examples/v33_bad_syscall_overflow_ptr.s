.intel_syntax noprefix
.code32
.global _start
_start:
    mov ebx, 0xfffffff0
    mov ecx, 32
    mov eax, 8
    int 0x80
    mov eax, 6
    xor ebx, ebx
    int 0x80
