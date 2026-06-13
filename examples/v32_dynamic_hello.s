.intel_syntax noprefix
.code32
.global _start
_start:
    call get_pc
get_pc:
    pop edx

    mov eax, 8
    mov ebx, edx
    add ebx, (msg1 - get_pc)
    mov ecx, 2
    int 0x80

    mov ecx, 8000000
burn_loop:
    dec ecx
    jnz burn_loop

    mov eax, 8
    mov ebx, edx
    add ebx, (msg2 - get_pc)
    mov ecx, 2
    int 0x80

    mov eax, 6
    xor ebx, ebx
    int 0x80

msg1:
    .ascii "D1"
msg2:
    .ascii "D2"
