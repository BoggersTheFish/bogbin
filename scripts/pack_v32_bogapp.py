import argparse
import hashlib
from pathlib import Path


MAGIC = b"BOGAPP32"
FORMAT_VERSION = 1
HEADER_SIZE = 136


def fixed_text(value, size):
    encoded = value.encode("ascii")
    if not encoded or len(encoded) >= size:
        raise ValueError(f"text field must contain 1..{size - 1} ASCII bytes")
    return encoded + b"\0" * (size - len(encoded))


def pack_app(code, name, version, entrypoint=0, capabilities=0, code_hash=None):
    expected_code_hash = code_hash or hashlib.sha256(code).digest()
    manifest = b"".join(
        [
            MAGIC,
            FORMAT_VERSION.to_bytes(4, "big"),
            HEADER_SIZE.to_bytes(4, "big"),
            entrypoint.to_bytes(4, "big"),
            HEADER_SIZE.to_bytes(4, "big"),
            len(code).to_bytes(4, "big"),
            capabilities.to_bytes(4, "big"),
            fixed_text(name, 24),
            fixed_text(version, 16),
            expected_code_hash,
        ]
    )
    assert len(manifest) == 104
    return manifest + hashlib.sha256(manifest).digest() + code


def main():
    parser = argparse.ArgumentParser(description="Pack a v32 kernel-loadable .bogapp")
    parser.add_argument("code")
    parser.add_argument("output")
    parser.add_argument("--name", required=True)
    parser.add_argument("--version", default="1.0.0")
    parser.add_argument("--entrypoint", type=lambda value: int(value, 0), default=0)
    parser.add_argument("--capabilities", type=lambda value: int(value, 0), default=0)
    parser.add_argument("--bad-code-hash", action="store_true")
    args = parser.parse_args()

    code = Path(args.code).read_bytes()
    code_hash = b"\0" * 32 if args.bad_code_hash else None
    packed = pack_app(
        code,
        args.name,
        args.version,
        entrypoint=args.entrypoint,
        capabilities=args.capabilities,
        code_hash=code_hash,
    )
    Path(args.output).write_bytes(packed)


if __name__ == "__main__":
    main()
