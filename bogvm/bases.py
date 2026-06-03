from __future__ import annotations


BASIS_ORDER = ("repeat_byte", "ramp_u8", "triangle_u8", "sine8_u8")

TRIANGLE_U8_OFFSETS = (0, 32, 64, 96, 128, 96, 64, 32)
SINE8_U8_OFFSETS = (0, 90, 127, 90, 0, -90, -127, -90)


def synthesize_basis(basis: str, start_byte: int, length: int) -> bytes:
    if basis not in BASIS_ORDER:
        raise ValueError(f"Unsupported deterministic basis: {basis}")
    if not 0 <= start_byte <= 255:
        raise ValueError("start_byte must be 0..255")
    if length < 0:
        raise ValueError("length must be non-negative")

    if basis == "repeat_byte":
        return bytes([start_byte]) * length

    if basis == "ramp_u8":
        return bytes((start_byte + i) % 256 for i in range(length))

    if basis == "triangle_u8":
        return bytes(
            (start_byte + TRIANGLE_U8_OFFSETS[i % len(TRIANGLE_U8_OFFSETS)]) % 256
            for i in range(length)
        )

    if basis == "sine8_u8":
        return bytes(
            (start_byte + SINE8_U8_OFFSETS[i % len(SINE8_U8_OFFSETS)]) % 256
            for i in range(length)
        )

    raise ValueError(f"Unsupported deterministic basis: {basis}")
