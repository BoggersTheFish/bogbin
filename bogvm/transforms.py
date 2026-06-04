from __future__ import annotations


TRANSFORM_ORDER = (
    "identity",
    "xor_previous",
    "delta_previous",
    "nibble_split",
    "mtf",
    "bwt",
    "bwt_mtf",
)
BWT_TRANSFORMS = {"bwt", "bwt_mtf"}


def apply_transform(name: str, data: bytes) -> bytes:
    transformed, _ = apply_transform_with_param(name, data)
    return transformed


def apply_transform_with_param(name: str, data: bytes) -> tuple[bytes, int]:
    if name not in TRANSFORM_ORDER:
        raise ValueError(f"Unsupported transform: {name}")

    if name == "identity":
        return data, 0

    if name == "xor_previous":
        if not data:
            return b"", 0
        out = bytearray([data[0]])
        for index in range(1, len(data)):
            out.append(data[index] ^ data[index - 1])
        return bytes(out), 0

    if name == "delta_previous":
        if not data:
            return b"", 0
        out = bytearray([data[0]])
        for index in range(1, len(data)):
            out.append((data[index] - data[index - 1]) % 256)
        return bytes(out), 0

    if name == "nibble_split":
        return bytes(_swap_nibbles(value) for value in data), 0

    if name == "mtf":
        return _mtf_encode(data), 0

    if name == "bwt":
        return _bwt_encode(data)

    if name == "bwt_mtf":
        bwt_data, primary_index = _bwt_encode(data)
        return _mtf_encode(bwt_data), primary_index

    raise ValueError(f"Unsupported transform: {name}")


def invert_transform(name: str, data: bytes, param: int = 0) -> bytes:
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

    if name == "mtf":
        return _mtf_decode(data)

    if name == "bwt":
        return _bwt_decode(data, param)

    if name == "bwt_mtf":
        return _bwt_decode(_mtf_decode(data), param)

    raise ValueError(f"Unsupported transform: {name}")


def _swap_nibbles(value: int) -> int:
    return ((value & 0x0F) << 4) | (value >> 4)


def _mtf_encode(data: bytes) -> bytes:
    alphabet = list(range(256))
    encoded = bytearray()
    for value in data:
        index = alphabet.index(value)
        encoded.append(index)
        if index:
            alphabet.pop(index)
            alphabet.insert(0, value)
    return bytes(encoded)


def _mtf_decode(data: bytes) -> bytes:
    alphabet = list(range(256))
    decoded = bytearray()
    for index in data:
        value = alphabet[index]
        decoded.append(value)
        if index:
            alphabet.pop(index)
            alphabet.insert(0, value)
    return bytes(decoded)


def _bwt_encode(data: bytes) -> tuple[bytes, int]:
    if not data:
        return b"", 0
    rotations = sorted((data[index:] + data[:index], index) for index in range(len(data)))
    primary_index = next(rank for rank, (_, index) in enumerate(rotations) if index == 0)
    return bytes(rotation[-1] for rotation, _ in rotations), primary_index


def _bwt_decode(data: bytes, primary_index: int) -> bytes:
    length = len(data)
    if length == 0:
        if primary_index != 0:
            raise ValueError("empty BWT transform requires primary index 0")
        return b""
    if not 0 <= primary_index < length:
        raise ValueError("BWT primary index out of range")

    table = [b""] * length
    for _ in range(length):
        table = sorted(bytes([data[index]]) + table[index] for index in range(length))
    return table[primary_index]
