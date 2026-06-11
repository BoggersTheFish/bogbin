.intel_syntax noprefix
.code32
.global _start
_start:
    # Get EIP
    call get_pc
get_pc:
    pop edx
    
    # Emit "B1"
    mov eax, 5
    mov ebx, edx
    add ebx, (msg1 - get_pc)
    mov ecx, 2
    int 0x80
    
    # Burn CPU to trigger preemption
    mov ecx, 8000000
burn_loop:
    dec ecx
    jnz burn_loop
    
    # Emit "B2"
    mov eax, 5
    mov ebx, edx
    add ebx, (msg2 - get_pc)
    mov ecx, 2
    int 0x80
    
    # Exit(0)
    mov eax, 6
    mov ebx, 0
    int 0x80

msg1:
    .ascii "B1"
msg2:
    .ascii "B2"
