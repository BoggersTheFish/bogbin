.intel_syntax noprefix
.code32
.global _start
_start:
    call get_pc
get_pc:
    pop ebx
    mov ecx, 257
    mov eax, 8
    int 0x80
    mov eax, 6
    xor ebx, ebx
    int 0x80
