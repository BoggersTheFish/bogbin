ENTRY(kernel_entry)

SECTIONS {
    . = 1M;
    _kernel_start = .;

    .multiboot_header : {
        /* MB1 for QEMU -kernel, MB2 (8-byte aligned) for UEFI GRUB GOP */
        KEEP(*(.multiboot_header))
        . = ALIGN(8);
    }

    .note.gnu.build-id : {
        *(.note.gnu.build-id)
    }

    .text : {
        *(.text .text.*)
    }

    .rodata : {
        *(.rodata .rodata.*)
    }

    .data : {
        *(.data .data.*)
    }

    .bss : {
        *(.bss .bss.*)
    }

    . = ALIGN(4096);
    _kernel_end = .;
}
