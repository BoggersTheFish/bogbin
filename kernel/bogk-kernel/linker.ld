ENTRY(kernel_entry)

SECTIONS {
    . = 1M;
    _kernel_start = .;

    .multiboot_header : {
        /* ensure that the multiboot header is at the beginning */
        KEEP(*(.multiboot_header))
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
