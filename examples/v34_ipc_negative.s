.intel_syntax noprefix
.code32
.global _start
_start:
    call here
here:
    pop edi

    xor ebx, ebx
    mov ecx, 8
    mov edx, 1
    xor esi, esi
    mov eax, 13
    int 0x80

    mov ebx, 99
    mov eax, 16
    int 0x80

    mov ebx, 2
    mov ecx, 0x00100000
    mov edx, 4
    xor esi, esi
    mov eax, 14
    int 0x80

    mov ebx, 2
    mov ecx, 0x00800000
    mov edx, 4
    mov eax, 14
    int 0x80

    mov ebx, 2
    mov ecx, edi
    mov edx, 9
    mov eax, 14
    int 0x80

    mov ebx, 2
    mov ecx, edi
    add ecx, (payload - here)
    mov edx, 8
    mov eax, 14
    int 0x80

    mov ebx, 2
    mov ecx, edi
    add ecx, (payload - here)
    mov edx, 8
    mov eax, 14
    int 0x80

    mov ebx, 2
    mov ecx, edi
    mov edx, 8
    mov eax, 15
    int 0x80

    mov ecx, edi
    sub ecx, (here - _start)
    add ecx, 0x7000
    mov ebx, 2
    mov edx, 2
    mov eax, 15
    int 0x80

    mov ebx, 2
    mov eax, 16
    int 0x80

    mov ecx, edi
    sub ecx, (here - _start)
    add ecx, 0x7000
    mov ebx, 2
    mov edx, 8
    mov eax, 15
    int 0x80

    mov ebx, 1
    mov ecx, edi
    sub ecx, (here - _start)
    add ecx, 0x7000
    mov edx, 8
    mov eax, 15
    int 0x80

    mov eax, 6
    xor ebx, ebx
    int 0x80

payload:
    .ascii "NEG-MSG\n"
