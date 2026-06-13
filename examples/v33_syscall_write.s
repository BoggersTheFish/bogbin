.intel_syntax noprefix
.code32
.global _start
_start:
    call get_pc
get_pc:
    pop edi

    mov eax, 9
    int 0x80

    mov ebx, edi
    sub ebx, (get_pc - _start)
    add ebx, 0x7000
    mov ecx, 16
    mov eax, 10
    int 0x80

    mov ebx, edi
    add ebx, (msg1 - get_pc)
    mov ecx, 8
    mov eax, 8
    int 0x80

    mov eax, 7
    int 0x80

    mov ebx, edi
    add ebx, (msg2 - get_pc)
    mov ecx, 8
    mov eax, 8
    int 0x80

    mov eax, 6
    xor ebx, ebx
    int 0x80

msg1:
    .ascii "V33-ONE\n"
msg2:
    .ascii "V33-TWO\n"
