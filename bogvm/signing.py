from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey


SIGNATURE_FORMAT = "BOGSIG-ed25519-1.0"


def generate_keypair(private_key_path: str | Path, public_key_path: str | Path) -> dict:
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    private_bytes = private_key.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    public_bytes = public_key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    private_path = Path(private_key_path)
    public_path = Path(public_key_path)
    private_path.write_text(base64.b64encode(private_bytes).decode("ascii") + "\n")
    private_path.chmod(0o600)
    public_path.write_text(base64.b64encode(public_bytes).decode("ascii") + "\n")
    return {"algorithm": "ed25519", "key_id": key_id(public_bytes)}


def public_key_info(public_key_path: str | Path) -> dict:
    public_bytes = base64.b64decode(Path(public_key_path).read_text().strip(), validate=True)
    Ed25519PublicKey.from_public_bytes(public_bytes)
    return {"algorithm": "ed25519", "key_id": key_id(public_bytes)}


def sign_object(obj: dict, private_key_path: str | Path) -> dict:
    private_bytes = base64.b64decode(Path(private_key_path).read_text().strip(), validate=True)
    private_key = Ed25519PrivateKey.from_private_bytes(private_bytes)
    public_bytes = private_key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    signature = private_key.sign(canonical_bytes(obj))
    return {
        "format": SIGNATURE_FORMAT,
        "algorithm": "ed25519",
        "key_id": key_id(public_bytes),
        "signature": base64.b64encode(signature).decode("ascii"),
    }


def verify_object_signature(obj: dict, signature: dict, trusted_public_keys: list[str | Path]) -> dict:
    if signature.get("format") != SIGNATURE_FORMAT or signature.get("algorithm") != "ed25519":
        return {"verified": False, "key_id": signature.get("key_id"), "reason": "unsupported signature format"}
    for path in trusted_public_keys:
        try:
            public_bytes = base64.b64decode(Path(path).read_text().strip(), validate=True)
            if key_id(public_bytes) != signature.get("key_id"):
                continue
            Ed25519PublicKey.from_public_bytes(public_bytes).verify(
                base64.b64decode(signature["signature"], validate=True),
                canonical_bytes(obj),
            )
            return {"verified": True, "key_id": signature["key_id"], "reason": None}
        except (OSError, ValueError, KeyError, InvalidSignature):
            continue
    return {"verified": False, "key_id": signature.get("key_id"), "reason": "signature is not valid for a trusted key"}


def canonical_bytes(obj: dict) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def key_id(public_bytes: bytes) -> str:
    return hashlib.sha256(public_bytes).hexdigest()[:16]
