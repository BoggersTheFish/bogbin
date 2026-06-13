.intel_syntax noprefix
.code32
.global _start
_start:
    mov eax, 0xffff
    int 0x80
    mov eax, 6
    xor ebx, ebx
    int 0x80
