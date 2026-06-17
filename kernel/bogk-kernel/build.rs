fn main() {
    let linker = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("linker.ld");
    println!("cargo:rerun-if-changed={}", linker.display());
    println!("cargo:rustc-link-arg=-nostdlib");
    println!("cargo:rustc-link-arg=-nostartfiles");
    println!("cargo:rustc-link-arg=-T{}", linker.display());
    println!("cargo:rustc-link-arg=-e");
    println!("cargo:rustc-link-arg=kernel_entry");
    println!("cargo:rustc-link-arg=-static");
}