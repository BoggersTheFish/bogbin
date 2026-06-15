import argparse
import hashlib
from pathlib import Path


MAGIC = b"BOGAPP39"
FORMAT_VERSION = 2
HEADER_SIZE = 160
ABI_VERSION = 2


def fixed_text(value, size):
    encoded = value.encode("ascii")
    if not encoded or len(encoded) >= size:
        raise ValueError(f"text field must contain 1..{size - 1} ASCII bytes")
    return encoded + bytes(size - len(encoded))


def pack_app(code, name, version="1.0.0", entrypoint=0, capabilities=0, abi_version=ABI_VERSION):
    header = bytearray(HEADER_SIZE)
    header[0:8] = MAGIC
    header[8:12] = FORMAT_VERSION.to_bytes(4, "little")
    header[12:16] = HEADER_SIZE.to_bytes(4, "little")
    header[16:20] = (HEADER_SIZE + len(code)).to_bytes(4, "little")
    header[20:24] = entrypoint.to_bytes(4, "little")
    header[24:28] = HEADER_SIZE.to_bytes(4, "little")
    header[28:32] = len(code).to_bytes(4, "little")
    header[32:36] = capabilities.to_bytes(4, "little")
    header[36:40] = abi_version.to_bytes(4, "little")
    header[40:44] = (4).to_bytes(4, "little")
    header[44:48] = (128).to_bytes(4, "little")
    header[48:80] = fixed_text(name, 32)
    header[80:96] = fixed_text(version, 16)
    header[96:128] = hashlib.sha256(code).digest()
    header[128:160] = hashlib.sha256(header[0:128]).digest()
    return bytes(header) + code


def main():
    parser = argparse.ArgumentParser(description="Pack a persistent v39 .bogapp v2 container")
    parser.add_argument("code", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--name", required=True)
    parser.add_argument("--version", default="1.0.0")
    parser.add_argument("--entrypoint", type=lambda value: int(value, 0), default=0)
    parser.add_argument("--capabilities", type=lambda value: int(value, 0), default=0)
    parser.add_argument("--abi-version", type=int, default=ABI_VERSION)
    args = parser.parse_args()
    args.output.write_bytes(pack_app(
        args.code.read_bytes(),
        args.name,
        args.version,
        args.entrypoint,
        args.capabilities,
        args.abi_version,
    ))


if __name__ == "__main__":
    main()
