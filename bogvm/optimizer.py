from __future__ import annotations

import hashlib

from .bases import BASIS_ORDER, synthesize_basis


class OptimizerError(Exception):
    pass


def optimize_residual_plan(data: bytes) -> dict:
    length = len(data)
    target_hash = hashlib.sha256(data).hexdigest()
    best: dict | None = None

    for basis_index, basis in enumerate(BASIS_ORDER):
        for coefficient_tuple in _coefficient_tuples_for_basis(basis, data):
            start_byte = coefficient_tuple[0]
            delta = coefficient_tuple[1]
            generated = synthesize_basis(basis, start_byte, length, delta=delta)
            residual_count = sum(1 for actual, expected in zip(data, generated) if actual != expected)
            candidate = {
                "basis": basis,
                "basis_index": basis_index,
                "start_byte": start_byte,
                "delta": delta,
                "coefficient_tuple": coefficient_tuple,
                "length": length,
                "sha256": target_hash,
                "residual_count": residual_count,
            }

            if best is None:
                best = candidate
                continue

            candidate_key = (
                candidate["residual_count"],
                candidate["basis_index"],
                candidate["coefficient_tuple"],
            )
            best_key = (
                best["residual_count"],
                best["basis_index"],
                best["coefficient_tuple"],
            )
            if candidate_key < best_key:
                best = candidate

    assert best is not None

    generated = synthesize_basis(best["basis"], best["start_byte"], length, delta=best["delta"])
    residuals = [
        {"offset": offset, "byte": actual}
        for offset, (actual, expected) in enumerate(zip(data, generated))
        if actual != expected
    ]
    reconstructed = _apply_residuals(generated, residuals)

    plan = dict(best)
    plan["residuals"] = residuals
    plan.pop("basis_index")
    plan.pop("coefficient_tuple")
    plan["reconstructed_hash"] = hashlib.sha256(bytes(reconstructed)).hexdigest()
    _assert_exact_reconstruction(plan, data)
    return plan


def _coefficient_tuples_for_basis(basis: str, data: bytes) -> list[tuple[int, int]]:
    if basis == "zero_block":
        return [(0, 0)]

    if basis == "delta_u8":
        tuples = []
        for delta in range(256):
            counts = [0] * 256
            for offset, value in enumerate(data):
                start_byte = (value - (offset * delta)) % 256
                counts[start_byte] += 1
            best_start = min(range(256), key=lambda value: (-counts[value], value))
            tuples.append((best_start, delta))
        return tuples

    if basis in {"dictionary_u8", "rle_u8"}:
        return [(_most_common_byte(data), 0)]

    return [(start_byte, 0) for start_byte in range(256)]


def _most_common_byte(data: bytes) -> int:
    if not data:
        return 0
    counts = [0] * 256
    for value in data:
        counts[value] += 1
    return min(range(256), key=lambda value: (-counts[value], value))


def optimize_chunked_residual_plan(data: bytes, chunk_size: int = 64) -> dict:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if chunk_size > 65535:
        raise ValueError("chunk_size must be <= 65535")

    chunks = []
    total_residual_count = 0

    for index, offset in enumerate(range(0, len(data), chunk_size)):
        chunk = data[offset:offset + chunk_size]
        plan = optimize_residual_plan(chunk)
        _assert_exact_reconstruction(plan, chunk)
        plan["index"] = index
        plan["offset"] = offset
        plan["sha256"] = hashlib.sha256(chunk).hexdigest()
        chunks.append(plan)
        total_residual_count += plan["residual_count"]

    return {
        "chunk_size": chunk_size,
        "chunk_count": len(chunks),
        "chunks": chunks,
        "total_residual_count": total_residual_count,
        "whole_sha256": hashlib.sha256(data).hexdigest(),
        "length": len(data),
    }


def _assert_exact_reconstruction(plan: dict, data: bytes) -> None:
    generated = synthesize_basis(
        plan["basis"],
        plan["start_byte"],
        plan["length"],
        delta=plan.get("delta", 0),
    )
    reconstructed = _apply_residuals(generated, plan["residuals"])
    actual_hash = hashlib.sha256(reconstructed).hexdigest()
    expected_hash = hashlib.sha256(data).hexdigest()

    if plan["length"] != len(data):
        raise OptimizerError("residual plan length does not match input length")
    if plan["sha256"] != expected_hash:
        raise OptimizerError("residual plan target hash does not match input bytes")
    if plan["residual_count"] != len(plan["residuals"]):
        raise OptimizerError("residual_count does not match residual list length")
    if actual_hash != expected_hash:
        raise OptimizerError("residual plan failed exact SHA-256 reconstruction")
    if plan.get("reconstructed_hash", actual_hash) != actual_hash:
        raise OptimizerError("reconstructed_hash does not match residual application")


def _apply_residuals(generated: bytes, residuals: list[dict]) -> bytes:
    reconstructed = bytearray(generated)
    previous_offset = -1

    for patch in residuals:
        offset = patch["offset"]
        byte = patch["byte"]
        if offset <= previous_offset:
            raise OptimizerError("residual offsets must be strictly increasing")
        if not 0 <= offset < len(reconstructed):
            raise OptimizerError("residual offset out of generated byte range")
        if not 0 <= byte <= 255:
            raise OptimizerError("residual byte must be 0..255")
        reconstructed[offset] = byte
        previous_offset = offset

    return bytes(reconstructed)
