from __future__ import annotations

import hashlib

from .optimizer import optimize_chunked_residual_plan, optimize_residual_plan


MAX_U16 = 65535


class PackerError(Exception):
    pass


def pack_bytes_to_bogasm(data: bytes, data_name: str = "payload") -> str:
    _validate_data_name(data_name)
    if len(data) > MAX_U16:
        raise PackerError("BOGBIN v0.9 single-block pack input length must be <= 65535 bytes")

    plan = optimize_residual_plan(data)
    lines = [
        f"DATA_BLOCK {data_name}",
        f"DECLARE_BASIS {plan['basis']}",
        f"LOAD_COEFFICIENTS {data_name} {plan['start_byte']} {plan['length']}",
        f"SYNTHESIZE {data_name}",
    ]

    for patch in plan["residuals"]:
        lines.append(f"STORE_RESIDUAL {data_name} {patch['offset']} {patch['byte']}")

    lines.extend([
        f"APPLY_RESIDUAL {data_name}",
        f"VERIFY_HASH {data_name} {plan['sha256']}",
        f"ACCEPT_DATA {data_name}",
        "EMIT_RECEIPT",
        "HALT",
    ])
    return "\n".join(lines) + "\n"


def pack_chunked_bytes_to_bogasm(data: bytes, data_name: str = "payload", chunk_size: int = 64) -> str:
    _validate_data_name(data_name)
    plan = optimize_chunked_residual_plan(data, chunk_size)

    lines = [
        f"# BOGBIN v0.9 chunked pack receipt whole_sha256 {plan['whole_sha256']}",
        f"# chunk_size {plan['chunk_size']}",
        f"# chunk_count {plan['chunk_count']}",
        f"# total_residual_count {plan['total_residual_count']}",
    ]

    for chunk in plan["chunks"]:
        chunk_name = f"{data_name}_chunk_{chunk['index']:04d}"
        lines.extend([
            f"DATA_BLOCK {chunk_name}",
            f"DECLARE_BASIS {chunk['basis']}",
            f"LOAD_COEFFICIENTS {chunk_name} {chunk['start_byte']} {chunk['length']}",
            f"SYNTHESIZE {chunk_name}",
        ])

        for patch in chunk["residuals"]:
            lines.append(f"STORE_RESIDUAL {chunk_name} {patch['offset']} {patch['byte']}")

        lines.extend([
            f"APPLY_RESIDUAL {chunk_name}",
            f"VERIFY_HASH {chunk_name} {chunk['sha256']}",
            f"ACCEPT_DATA {chunk_name}",
        ])

    lines.extend([
        "EMIT_RECEIPT",
        "HALT",
    ])
    return "\n".join(lines) + "\n"


def build_pack_receipt_metadata(data: bytes, chunk_size: int, single_block: bool) -> dict:
    if single_block:
        plan = optimize_residual_plan(data)
        return {
            "pack_mode": "single_block",
            "chunk_size": len(data),
            "chunk_count": 1,
            "total_residual_count": plan["residual_count"],
            "whole_sha256": hashlib.sha256(data).hexdigest(),
        }

    plan = optimize_chunked_residual_plan(data, chunk_size)
    return {
        "pack_mode": "chunked",
        "chunk_size": plan["chunk_size"],
        "chunk_count": plan["chunk_count"],
        "total_residual_count": plan["total_residual_count"],
        "whole_sha256": plan["whole_sha256"],
    }


def _validate_data_name(data_name: str) -> None:
    if not data_name or any(ch.isspace() for ch in data_name):
        raise PackerError("data_name must be a non-empty single token")
