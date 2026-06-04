from __future__ import annotations

import hashlib

from .bases import BASIS_ORDER, synthesize_basis
from .transforms import TRANSFORM_ORDER, apply_transform, apply_transform_with_param, invert_transform


class OptimizerError(Exception):
    pass


TRANSFORM_COSTS = {
    "identity": 0,
    "xor_previous": 1,
    "delta_previous": 1,
    "nibble_split": 1,
    "mtf": 8,
    "bwt": 16,
    "bwt_mtf": 24,
}

BASIS_COSTS = {
    "zero_block": 0,
    "repeat_byte": 1,
    "delta_u8": 2,
    "dictionary_u8": 3,
    "rle_u8": 3,
    "ramp_u8": 2,
    "triangle_u8": 4,
    "sine8_u8": 5,
    "fourier8_u8": 6,
}


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


def optimize_transformed_chunked_residual_plan(data: bytes, chunk_size: int = 64) -> dict:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if chunk_size > 65535:
        raise ValueError("chunk_size must be <= 65535")

    chunks = []
    total_residual_count = 0
    transform_counts = {transform: 0 for transform in TRANSFORM_ORDER}

    for index, offset in enumerate(range(0, len(data), chunk_size)):
        chunk = data[offset:offset + chunk_size]
        plan = optimize_transformed_residual_plan(chunk)
        plan["index"] = index
        plan["offset"] = offset
        chunks.append(plan)
        total_residual_count += plan["residual_count"]
        transform_counts[plan["transform"]] += 1

    return {
        "chunk_size": chunk_size,
        "chunk_count": len(chunks),
        "chunks": chunks,
        "total_residual_count": total_residual_count,
        "whole_sha256": hashlib.sha256(data).hexdigest(),
        "length": len(data),
        "transform_tournament_enabled": True,
        "candidate_transforms": list(TRANSFORM_ORDER),
        "transform_counts": transform_counts,
    }


def optimize_transformed_residual_plan(data: bytes) -> dict:
    best: dict | None = None

    for transform_index, transform in enumerate(TRANSFORM_ORDER):
        transformed, transform_param = apply_transform_with_param(transform, data)
        plan = optimize_residual_plan(transformed)
        restored = invert_transform(transform, transformed, transform_param)
        if restored != data:
            raise OptimizerError(f"transform is not reversible: {transform}")

        candidate = dict(plan)
        candidate["transform"] = transform
        candidate["transform_param"] = transform_param
        candidate["transform_index"] = transform_index
        candidate["sha256"] = hashlib.sha256(transformed).hexdigest()
        candidate["transformed_sha256"] = candidate["sha256"]
        candidate["original_sha256"] = hashlib.sha256(data).hexdigest()
        candidate["score"] = score_reconstruction_plan(candidate)

        if best is None:
            best = candidate
            continue

        candidate_key = (
            candidate["score"]["total_cost"],
            candidate["score"]["container_size"],
            candidate["residual_count"],
            candidate["score"]["decode_cost"],
            candidate["score"]["transform_cost"],
            candidate["transform_index"],
            candidate["basis"],
            candidate["start_byte"],
            candidate.get("delta", 0),
            candidate["transform_param"],
        )
        best_key = (
            best["score"]["total_cost"],
            best["score"]["container_size"],
            best["residual_count"],
            best["score"]["decode_cost"],
            best["score"]["transform_cost"],
            best["transform_index"],
            best["basis"],
            best["start_byte"],
            best.get("delta", 0),
            best["transform_param"],
        )
        if candidate_key < best_key:
            best = candidate

    assert best is not None
    best.pop("transform_index")
    _assert_exact_reconstruction(best, apply_transform(best["transform"], data))
    restored = invert_transform(best["transform"], apply_transform(best["transform"], data), best["transform_param"])
    if hashlib.sha256(restored).hexdigest() != best["original_sha256"]:
        raise OptimizerError("transformed residual plan failed original SHA-256 reconstruction")
    return best


def score_reconstruction_plan(plan: dict) -> dict:
    residual_count = plan["residual_count"]
    length = plan["length"]
    transform = plan.get("transform", "identity")
    basis = plan["basis"]
    transform_cost = TRANSFORM_COSTS[transform]
    basis_cost = BASIS_COSTS[basis]
    descriptor_size = 3 + (1 if transform in {"bwt", "bwt_mtf"} else 0)
    residual_delta_size = _estimate_delta_residual_size(plan.get("residuals", []))
    residual_bitmask_size = ((length + 7) // 8) + residual_count if residual_count else 0
    residual_size = min(
        residual_delta_size,
        residual_bitmask_size if residual_count else residual_delta_size,
    )
    container_size = descriptor_size + _varuint_size(residual_count) + residual_size
    decode_cost = length + residual_count + transform_cost + basis_cost
    total_cost = (container_size * 16) + residual_count + transform_cost + decode_cost
    return {
        "residual_count": residual_count,
        "container_size": container_size,
        "transform_cost": transform_cost,
        "basis_cost": basis_cost,
        "decode_cost": decode_cost,
        "total_cost": total_cost,
    }


def _estimate_delta_residual_size(residuals: list[dict]) -> int:
    size = 0
    previous_offset = -1
    for patch in residuals:
        offset = patch["offset"]
        delta = offset if previous_offset < 0 else offset - previous_offset - 1
        size += _varuint_size(delta) + 1
        previous_offset = offset
    return size


def _varuint_size(value: int) -> int:
    if value < 0:
        raise OptimizerError("varuint size cannot be negative")
    size = 1
    value >>= 7
    while value:
        size += 1
        value >>= 7
    return size


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
