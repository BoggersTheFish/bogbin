# BOGBIN v0.4 Plan: Triangle Integer Wave Basis

Goal: add the first periodic deterministic wave/generator basis.

v0.4 adds triangle_u8.

triangle_u8 uses a fixed integer triangle shape:

    offsets = 0, 32, 64, 96, 128, 96, 64, 32
    byte[i] = (start + offsets[i mod 8]) mod 256

This proves BOGVM can synthesize periodic wave-like byte fields from compact integer parameters while preserving hash-gated acceptance and blocked receipts.

Boundary:

- Toy-scale integer oscillator only.
- No floating point.
- No sine/cosine lookup table yet.
- No Fourier basis yet.
- No compression victory claim.
- No .bog container compiler yet.
- No laptop port yet.
