.intel_syntax noprefix
.code32
.global _start
_start:
    call code_address
code_address:
    pop eax
    mov byte ptr [eax], 0x90
    mov eax, 6
    mov ebx, 1
    int 0x80
