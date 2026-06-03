from __future__ import annotations

import hashlib

from .bases import BASIS_ORDER, synthesize_basis


def optimize_residual_plan(data: bytes) -> dict:
    length = len(data)
    target_hash = hashlib.sha256(data).hexdigest()
    best: dict | None = None

    for basis_index, basis in enumerate(BASIS_ORDER):
        for start_byte in range(256):
            generated = synthesize_basis(basis, start_byte, length)
            residuals = [
                {"offset": offset, "byte": actual}
                for offset, (actual, expected) in enumerate(zip(data, generated))
                if actual != expected
            ]
            candidate = {
                "basis": basis,
                "basis_index": basis_index,
                "start_byte": start_byte,
                "length": length,
                "sha256": target_hash,
                "residuals": residuals,
                "residual_count": len(residuals),
            }

            if best is None:
                best = candidate
                continue

            candidate_key = (
                candidate["residual_count"],
                candidate["basis_index"],
                candidate["start_byte"],
            )
            best_key = (
                best["residual_count"],
                best["basis_index"],
                best["start_byte"],
            )
            if candidate_key < best_key:
                best = candidate

    assert best is not None

    reconstructed = bytearray(synthesize_basis(best["basis"], best["start_byte"], length))
    for patch in best["residuals"]:
        reconstructed[patch["offset"]] = patch["byte"]

    plan = dict(best)
    plan.pop("basis_index")
    plan["reconstructed_hash"] = hashlib.sha256(bytes(reconstructed)).hexdigest()
    return plan
