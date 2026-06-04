from __future__ import annotations


TRANSFORM_ORDER = ("identity", "xor_previous", "delta_previous", "nibble_split")


def apply_transform(name: str, data: bytes) -> bytes:
    if name not in TRANSFORM_ORDER:
        raise ValueError(f"Unsupported transform: {name}")

    if name == "identity":
        return data

    if name == "xor_previous":
        if not data:
            return b""
        out = bytearray([data[0]])
        for index in range(1, len(data)):
            out.append(data[index] ^ data[index - 1])
        return bytes(out)

    if name == "delta_previous":
        if not data:
            return b""
        out = bytearray([data[0]])
        for index in range(1, len(data)):
            out.append((data[index] - data[index - 1]) % 256)
        return bytes(out)

    if name == "nibble_split":
        return bytes(_swap_nibbles(value) for value in data)

    raise ValueError(f"Unsupported transform: {name}")


def invert_transform(name: str, data: bytes) -> bytes:
    if name not in TRANSFORM_ORDER:
        raise ValueError(f"Unsupported transform: {name}")

    if name == "identity":
        return data

    if name == "xor_previous":
        if not data:
            return b""
        out = bytearray([data[0]])
        for index in range(1, len(data)):
            out.append(data[index] ^ out[index - 1])
        return bytes(out)

    if name == "delta_previous":
        if not data:
            return b""
        out = bytearray([data[0]])
        for index in range(1, len(data)):
            out.append((out[index - 1] + data[index]) % 256)
        return bytes(out)

    if name == "nibble_split":
        return bytes(_swap_nibbles(value) for value in data)

    raise ValueError(f"Unsupported transform: {name}")


def _swap_nibbles(value: int) -> int:
    return ((value & 0x0F) << 4) | (value >> 4)
