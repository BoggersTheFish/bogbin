.intel_syntax noprefix
.code32
.global _start
_start:
    call here
here:
    pop edi

    mov ebx, edi
    and ebx, 0xfffff000
    add ebx, 0x0fff
    mov ecx, 1
    mov eax, 8
    int 0x80

    mov ebx, edi
    and ebx, 0xfffff000
    add ebx, 0x0fff
    mov ecx, 2
    mov eax, 8
    int 0x80

    mov ebx, edi
    and ebx, 0xfffff000
    add ebx, 0x0fff
    mov ecx, 16
    mov eax, 10
    int 0x80

    mov ebx, edi
    and ebx, 0xfffff000
    add ebx, 0x7000
    mov ecx, 16
    mov eax, 10
    int 0x80

    mov eax, 6
    xor ebx, ebx
    int 0x80
