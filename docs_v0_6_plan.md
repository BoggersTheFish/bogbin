# BOGBIN v0.6 Plan: Residual Patching

Goal: add exact reconstruction from generator output plus deterministic residual patches.

v0.6 adds residual patching:

    generator output + residual patches = exact reconstructed bytes

This is the bridge from toy generative storage toward real .bog storage, because data no longer has to be represented only by the generator. The generator can produce a cheap base state, and residual patches can correct it into an exact byte sequence before hash verification.

Boundary:

- Deterministic byte residuals only.
- No compression victory claim.
- No automatic residual optimization yet.
- No Fourier basis yet.
- No .bog container compiler yet.
- No laptop port yet.
