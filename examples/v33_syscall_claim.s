.intel_syntax noprefix
.code32
.global _start
_start:
    call get_pc
get_pc:
    pop edi
    mov ebx, edi
    add ebx, (claim - get_pc)
    mov ecx, 15
    mov eax, 12
    int 0x80
    mov eax, 6
    xor ebx, ebx
    int 0x80
claim:
    .ascii "v33-audit-claim"
