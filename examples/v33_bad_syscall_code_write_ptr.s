.intel_syntax noprefix
.code32
.global _start
_start:
    call own_code
own_code:
    pop ebx
    mov ecx, 16
    mov eax, 10
    int 0x80
    mov eax, 6
    xor ebx, ebx
    int 0x80
