.intel_syntax noprefix
.code32
.global _start
_start:
    mov ebx, 0xffffffff
    mov eax, 16
    int 0x80
    mov eax, 6
    xor ebx, ebx
    int 0x80
