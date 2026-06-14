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
    mov ebp, eax

    mov ebx, ebp
    mov ecx, edi
    add ecx, (message - here)
    mov edx, 8
    xor esi, esi
    mov eax, 14
    int 0x80

    mov ebx, ebp
    mov eax, 16
    int 0x80

    mov ebx, edi
    add ebx, (system_path - here)
    mov ecx, 14
    mov edx, edi
    add edx, (message - here)
    mov esi, 8
    mov eax, 17
    int 0x80

    mov ebx, ebp
    mov eax, 16
    int 0x80

    mov ebx, ebp
    mov ecx, edi
    sub ecx, (here - _start)
    add ecx, 0x7000
    mov edx, 8
    xor esi, esi
    mov eax, 15
    int 0x80

    mov ebx, ecx
    mov ecx, eax
    mov eax, 8
    int 0x80

    mov eax, 6
    xor ebx, ebx
    int 0x80

system_path:
    .ascii "/system/status"
message:
    .ascii "IPC-V351"
