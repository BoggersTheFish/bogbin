# BOGBIN v0.3 Plan: Integer Wave Basis

Goal: add the first position-dependent deterministic wave/generator basis.

v0.2 proved repeat-byte generative storage:

- store parameters
- synthesize bytes
- verify hash
- accept/block with receipts

v0.3 adds ramp_u8:

    byte[i] = (start + i) mod 256

This proves BOGVM can synthesize data from a changing deterministic field, not only repeated constants.

Boundary:

- Still toy-scale.
- Integer deterministic basis only.
- No floating point.
- No Fourier yet.
- No compression victory claim.
- No laptop port yet.
