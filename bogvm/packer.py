from __future__ import annotations

from .optimizer import optimize_residual_plan


MAX_U16 = 65535


class PackerError(Exception):
    pass


def pack_bytes_to_bogasm(data: bytes, data_name: str = "payload") -> str:
    if not data_name or any(ch.isspace() for ch in data_name):
        raise PackerError("data_name must be a non-empty single token")
    if len(data) > MAX_U16:
        raise PackerError("BOGBIN v0.7 pack input length must be <= 65535 bytes")

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
