.intel_syntax noprefix
.code32
.global _start
_start:
    # PID 1 owns this private test-page virtual address; this process does not.
    mov dword ptr [0x00800000], 0x31313131
    mov eax, 6
    mov ebx, 1
    int 0x80
