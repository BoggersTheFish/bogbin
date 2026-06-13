.intel_syntax noprefix
.code32
.global _start
_start:
    mov dword ptr [0x00100000], 0x31313131
    mov eax, 6
    mov ebx, 1
    int 0x80
