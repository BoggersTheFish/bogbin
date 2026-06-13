.intel_syntax noprefix
.code32
.global _start
_start:
    call here
here:
    pop edi
    mov ecx, edi
    sub ecx, (here - _start)
    add ecx, 0x7000

    mov ebx, 1
    mov edx, 16
    xor esi, esi
    mov eax, 15
    int 0x80

    mov ebx, ecx
    mov ecx, eax
    mov eax, 8
    int 0x80

    mov ebx, 1
    mov eax, 16
    int 0x80

    mov ecx, 8000000
receiver_burn:
    dec ecx
    jnz receiver_burn

    mov eax, 6
    xor ebx, ebx
    int 0x80
