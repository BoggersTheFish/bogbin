# BOGBIN / BOGVM Release Notes

## v0.1.1: Blocked Execution Receipts

v0.1.1 makes blocked VM-law failures auditable. Contradictory programs now emit blocked receipts instead of only tracebacking.

Proof:

- `examples/contradiction.bogasm` creates support and conflict pressure on the same claim.
- `INTERFERE` reports support pressure, conflict pressure, net pressure, and tension.
- `VERIFY` rejects the claim.
- `ACCEPT` is blocked because the claim is not verified.
- The CLI writes `artifacts/contradiction_receipt.json`.

Verification:

~~~bash
python3 -m unittest discover -s tests -p "test_*.py" -q
python3 -m bogvm assemble examples/contradiction.bogasm artifacts/contradiction.bogbin
python3 -m bogvm run artifacts/contradiction.bogbin --receipt artifacts/contradiction_receipt.json || echo "blocked receipt emitted"
~~~

Boundary:

- Blocked execution is not success.
- Blocked execution is still auditable.
- No `ACCEPT` without `VERIFY`.
- Candidate graph contamination remains zero.

## v0.1.0: Minimal Wave-State Binary VM

v0.1.0 creates the first minimal BOGVM.

Proof:

- `.bogasm` source assembles into `.bogbin`.
- BOGVM executes fixed-point sparse graph-state propagation.
- `examples/proof_chain.bogasm` verifies `A -> B -> C`, then accepts `claim_A_C`.
- The VM emits `artifacts/proof_chain_receipt.json`.

Boundary:

- This is a toy VM proof, not a full operating system.
- No Fourier/generative storage yet.
- No laptop port yet.
- No direct hardware execution yet.
