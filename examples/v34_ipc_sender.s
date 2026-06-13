.intel_syntax noprefix
.code32
.global _start
_start:
    call here
here:
    pop edi

    mov eax, 13
    mov ebx, 31
    mov ecx, 16
    mov edx, 2
    xor esi, esi
    int 0x80

    mov ebx, eax
    mov ecx, edi
    add ecx, (message - here)
    mov edx, 8
    xor esi, esi
    mov eax, 14
    int 0x80

    mov ebx, 1
    mov eax, 16
    int 0x80

    mov eax, 7
    int 0x80

    mov ecx, 8000000
sender_burn:
    dec ecx
    jnz sender_burn

    mov eax, 6
    xor ebx, ebx
    int 0x80

message:
    .ascii "V34-MSG\n"
