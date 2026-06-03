from __future__ import annotations

import json
import hashlib
from pathlib import Path

from .bases import BASIS_ORDER, synthesize_basis
from .optimizer import optimize_chunked_residual_plan


class ContainerError(Exception):
    pass


REQUIRED_TOP_LEVEL_FIELDS = (
    "format",
    "vm_format",
    "pack_mode",
    "chunk_size",
    "chunk_count",
    "whole_sha256",
    "total_residual_count",
    "chunks",
)

REQUIRED_CHUNK_FIELDS = (
    "index",
    "name",
    "offset",
    "length",
    "basis",
    "start_byte",
    "residual_count",
    "residuals",
    "chunk_sha256",
)


def build_bog_container(data: bytes, chunk_size: int = 64) -> dict:
    plan = optimize_chunked_residual_plan(data, chunk_size)
    chunks = []

    for chunk in plan["chunks"]:
        chunks.append({
            "index": chunk["index"],
            "name": f"payload_chunk_{chunk['index']:04d}",
            "offset": chunk["offset"],
            "length": chunk["length"],
            "basis": chunk["basis"],
            "start_byte": chunk["start_byte"],
            "residual_count": chunk["residual_count"],
            "residuals": chunk["residuals"],
            "chunk_sha256": chunk["sha256"],
        })

    return {
        "format": "BOG-1.1",
        "vm_format": "BOGBIN-1.1",
        "pack_mode": "chunked",
        "chunk_size": plan["chunk_size"],
        "chunk_count": plan["chunk_count"],
        "whole_sha256": plan["whole_sha256"],
        "total_residual_count": plan["total_residual_count"],
        "chunks": chunks,
    }


def write_bog_container(container: dict, path: str) -> None:
    validate_bog_container(container)
    Path(path).write_text(_canonical_json(container) + "\n")


def read_bog_container(path: str) -> dict:
    try:
        container = json.loads(Path(path).read_text())
    except json.JSONDecodeError as exc:
        raise ContainerError(f"Invalid .bog JSON: {exc}") from exc
    validate_bog_container(container)
    return container


def compile_bog_container_to_bogasm(container: dict) -> str:
    validate_bog_container(container)

    lines = [
        f"# BOG container {container['format']}",
        f"# vm_format {container['vm_format']}",
        f"# whole_sha256 {container['whole_sha256']}",
        f"# chunk_size {container['chunk_size']}",
        f"# chunk_count {container['chunk_count']}",
        f"# total_residual_count {container['total_residual_count']}",
    ]

    for chunk in container["chunks"]:
        name = chunk["name"]
        lines.extend([
            f"DATA_BLOCK {name}",
            f"DECLARE_BASIS {chunk['basis']}",
            f"LOAD_COEFFICIENTS {name} {chunk['start_byte']} {chunk['length']}",
            f"SYNTHESIZE {name}",
        ])

        for patch in chunk["residuals"]:
            lines.append(f"STORE_RESIDUAL {name} {patch['offset']} {patch['byte']}")

        lines.extend([
            f"APPLY_RESIDUAL {name}",
            f"VERIFY_HASH {name} {chunk['chunk_sha256']}",
            f"ACCEPT_DATA {name}",
        ])

    lines.extend([
        "EMIT_RECEIPT",
        "HALT",
    ])
    return "\n".join(lines) + "\n"


def reconstruct_bog_container_bytes(container: dict) -> bytes:
    validate_bog_container(container)

    chunks_by_index = {}
    for chunk in container["chunks"]:
        index = chunk["index"]
        if index in chunks_by_index:
            raise ContainerError(f"Duplicate chunk index: {index}")
        chunks_by_index[index] = chunk

    if set(chunks_by_index.keys()) != set(range(container["chunk_count"])):
        raise ContainerError("Missing chunk index in container")

    reconstructed_chunks = []
    for index in range(container["chunk_count"]):
        chunk = chunks_by_index[index]
        data = bytearray(synthesize_basis(chunk["basis"], chunk["start_byte"], chunk["length"]))

        for patch in chunk["residuals"]:
            offset = patch["offset"]
            if offset >= len(data):
                raise ContainerError("residual offset out of reconstructed chunk range")
            data[offset] = patch["byte"]

        chunk_bytes = bytes(data)
        actual_chunk_hash = hashlib.sha256(chunk_bytes).hexdigest()
        if actual_chunk_hash != chunk["chunk_sha256"]:
            raise ContainerError(f"chunk {index} SHA-256 mismatch")
        reconstructed_chunks.append(chunk_bytes)

    reconstructed = b"".join(reconstructed_chunks)
    actual_whole_hash = hashlib.sha256(reconstructed).hexdigest()
    if actual_whole_hash != container["whole_sha256"]:
        raise ContainerError("whole SHA-256 mismatch")
    return reconstructed


def validate_bog_container(container: dict) -> None:
    if not isinstance(container, dict):
        raise ContainerError(".bog container must be a JSON object")

    for field in REQUIRED_TOP_LEVEL_FIELDS:
        if field not in container:
            raise ContainerError(f"Missing required container field: {field}")

    if container["format"] != "BOG-1.1":
        raise ContainerError(f"Unsupported .bog format: {container['format']}")
    if container["vm_format"] != "BOGBIN-1.1":
        raise ContainerError(f"Unsupported VM format: {container['vm_format']}")
    if container["pack_mode"] != "chunked":
        raise ContainerError(f"Unsupported pack mode: {container['pack_mode']}")
    if not isinstance(container["chunk_size"], int) or container["chunk_size"] <= 0:
        raise ContainerError("chunk_size must be a positive integer")
    if not isinstance(container["chunk_count"], int) or container["chunk_count"] < 0:
        raise ContainerError("chunk_count must be a non-negative integer")
    if not isinstance(container["total_residual_count"], int) or container["total_residual_count"] < 0:
        raise ContainerError("total_residual_count must be a non-negative integer")
    if not _is_sha256(container["whole_sha256"]):
        raise ContainerError("whole_sha256 must be a SHA-256 hex string")
    if not isinstance(container["chunks"], list):
        raise ContainerError("chunks must be a list")
    if len(container["chunks"]) != container["chunk_count"]:
        raise ContainerError("chunk_count does not match chunks length")

    total_residual_count = 0
    expected_offset = 0
    for expected_index, chunk in enumerate(container["chunks"]):
        _validate_chunk(chunk, expected_index, expected_offset, container["chunk_size"])
        total_residual_count += chunk["residual_count"]
        expected_offset += chunk["length"]

    if total_residual_count != container["total_residual_count"]:
        raise ContainerError("total_residual_count does not match chunk residuals")


def _validate_chunk(chunk: dict, expected_index: int, expected_offset: int, chunk_size: int) -> None:
    if not isinstance(chunk, dict):
        raise ContainerError("chunk must be a JSON object")
    for field in REQUIRED_CHUNK_FIELDS:
        if field not in chunk:
            raise ContainerError(f"Missing required chunk field: {field}")

    if chunk["index"] != expected_index:
        raise ContainerError("chunk index ordering is not deterministic")
    expected_name = f"payload_chunk_{expected_index:04d}"
    if chunk["name"] != expected_name:
        raise ContainerError(f"chunk name must be {expected_name}")
    if chunk["offset"] != expected_offset:
        raise ContainerError("chunk offset ordering is not deterministic")
    if not isinstance(chunk["length"], int) or chunk["length"] < 0 or chunk["length"] > chunk_size:
        raise ContainerError("chunk length is invalid")
    if chunk["length"] == 0:
        raise ContainerError("empty chunks are not allowed")
    if chunk["basis"] not in BASIS_ORDER:
        raise ContainerError(f"Unsupported deterministic basis: {chunk['basis']}")
    if not isinstance(chunk["start_byte"], int) or not 0 <= chunk["start_byte"] <= 255:
        raise ContainerError("start_byte must be 0..255")
    if not isinstance(chunk["residual_count"], int) or chunk["residual_count"] < 0:
        raise ContainerError("residual_count must be a non-negative integer")
    if not isinstance(chunk["residuals"], list):
        raise ContainerError("residuals must be a list")
    if len(chunk["residuals"]) != chunk["residual_count"]:
        raise ContainerError("residual_count does not match residual list length")
    if not _is_sha256(chunk["chunk_sha256"]):
        raise ContainerError("chunk_sha256 must be a SHA-256 hex string")

    previous_offset = -1
    for patch in chunk["residuals"]:
        if not isinstance(patch, dict):
            raise ContainerError("residual patch must be a JSON object")
        if set(patch.keys()) != {"offset", "byte"}:
            raise ContainerError("residual patch must contain offset and byte")
        if not isinstance(patch["offset"], int) or not 0 <= patch["offset"] < chunk["length"]:
            raise ContainerError("residual offset out of range")
        if patch["offset"] <= previous_offset:
            raise ContainerError("residual offsets must be strictly increasing")
        if not isinstance(patch["byte"], int) or not 0 <= patch["byte"] <= 255:
            raise ContainerError("residual byte must be 0..255")
        previous_offset = patch["offset"]


def _canonical_json(container: dict) -> str:
    return json.dumps(container, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _is_sha256(value) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(ch in "0123456789abcdef" for ch in value)
    )
