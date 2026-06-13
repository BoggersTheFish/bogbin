.intel_syntax noprefix
.code32
.global _start
_start:
    call here
here:
    pop ecx
    mov ebx, 2
    mov edx, 8
    xor esi, esi
    mov eax, 15
    int 0x80
    mov eax, 6
    xor ebx, ebx
    int 0x80
