# BOGBIN v0.5 Plan: Fixed Integer Sine Lookup Basis

Goal: add the first deterministic sine-like lookup-table generator basis.

v0.5 adds sine8_u8.

sine8_u8 uses a fixed 8-step integer lookup table:

    offsets = 0, 90, 127, 90, 0, -90, -127, -90
    byte[i] = (start + offsets[i mod 8]) mod 256

This proves BOGVM can synthesize sine-like periodic byte fields without floating point, trigonometric runtime calls, or platform-dependent rounding.

Boundary:

- Fixed integer lookup table only.
- No floating point.
- No runtime sine/cosine.
- No FFT yet.
- No Fourier basis yet.
- No compression victory claim.
- No .bog container compiler yet.
- No laptop port yet.
