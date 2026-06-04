from __future__ import annotations

import json
import hashlib
from pathlib import Path

from .bases import BASIS_ORDER, synthesize_basis
from .optimizer import optimize_chunked_residual_plan, optimize_transformed_chunked_residual_plan
from .transforms import TRANSFORM_ORDER, invert_transform


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

CANDIDATE_CHUNK_SIZES = (16, 32, 64, 128)
BOGPK_MAGIC = b"BOGPK1"
BOGPK_VERSION = 1
BOGPK_FLAG_TRANSFORMED_HASHES = 1 << 0
BOGPK_FLAG_ORIGINAL_HASHES = 1 << 1
BOGPK_FLAG_ZERO_RESIDUAL_RUNS = 1 << 2
BOGPK_DESCRIPTOR_SENTINEL = 0xFF

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


def build_bog_container(data: bytes, chunk_size: int = 64, auto_chunk: bool = False) -> dict:
    return build_bog_container_v1(data, chunk_size=chunk_size, auto_chunk=auto_chunk, transform_tournament=False)


def build_bog_container_v1(
    data: bytes,
    chunk_size: int = 64,
    auto_chunk: bool = False,
    transform_tournament: bool = False,
) -> dict:
    if auto_chunk:
        plan, tournament_results = optimize_adaptive_chunked_residual_plan(
            data,
            transform_tournament=transform_tournament,
        )
    else:
        plan = _optimize_chunked_plan(data, chunk_size, transform_tournament)
        tournament_results = []
    return build_bog_container_from_plan(
        plan,
        auto_chunk=auto_chunk,
        tournament_results=tournament_results,
        transform_tournament=transform_tournament,
    )


def optimize_adaptive_chunked_residual_plan(data: bytes, transform_tournament: bool = False) -> tuple[dict, list[dict]]:
    best_plan = None
    tournament_results = []

    for chunk_size in CANDIDATE_CHUNK_SIZES:
        plan = _optimize_chunked_plan(data, chunk_size, transform_tournament)
        residual_density = _residual_density(plan["total_residual_count"], len(data))
        result = {
            "chunk_size": chunk_size,
            "chunk_count": plan["chunk_count"],
            "total_residual_count": plan["total_residual_count"],
            "residual_density": residual_density,
        }
        if transform_tournament:
            result["transform_counts"] = plan["transform_counts"]
        tournament_results.append(result)

        candidate_key = (
            plan["total_residual_count"],
            residual_density,
            plan["chunk_count"],
            chunk_size,
        )
        if best_plan is None:
            best_plan = plan
            best_key = candidate_key
            continue
        if candidate_key < best_key:
            best_plan = plan
            best_key = candidate_key

    assert best_plan is not None
    return best_plan, tournament_results


def build_bog_container_from_plan(
    plan: dict,
    auto_chunk: bool = False,
    tournament_results: list[dict] | None = None,
    transform_tournament: bool = False,
) -> dict:
    tournament_results = tournament_results or []
    chunks = []

    for chunk in plan["chunks"]:
        chunks.append({
            "index": chunk["index"],
            "name": f"payload_chunk_{chunk['index']:04d}",
            "offset": chunk["offset"],
            "length": chunk["length"],
            "basis": chunk["basis"],
            "start_byte": chunk["start_byte"],
            "delta": chunk.get("delta", 0),
            "transform": chunk.get("transform", "identity"),
            "residual_count": chunk["residual_count"],
            "residuals": chunk["residuals"],
            "chunk_sha256": chunk["sha256"],
            "transformed_sha256": chunk.get("transformed_sha256", chunk["sha256"]),
            "original_chunk_sha256": chunk.get("original_sha256", chunk["sha256"]),
        })

    container = {
        "format": "BOG-1.3",
        "vm_format": "BOGBIN-1.3",
        "pack_mode": "chunked",
        "chunk_size": plan["chunk_size"],
        "chunk_count": plan["chunk_count"],
        "whole_sha256": plan["whole_sha256"],
        "total_residual_count": plan["total_residual_count"],
        "chunks": chunks,
    }
    container["chunk_tournament_enabled"] = auto_chunk
    container["candidate_chunk_sizes"] = list(CANDIDATE_CHUNK_SIZES) if auto_chunk else [plan["chunk_size"]]
    container["selected_chunk_size"] = plan["chunk_size"]
    container["selected_total_residual_count"] = plan["total_residual_count"]
    container["selected_residual_density"] = _residual_density(plan["total_residual_count"], plan["length"])
    container["chunk_tournament_results"] = tournament_results
    container["transform_tournament_enabled"] = transform_tournament
    container["candidate_transforms"] = list(TRANSFORM_ORDER) if transform_tournament else ["identity"]
    container["selected_transform_counts"] = plan.get(
        "transform_counts",
        {"identity": plan["chunk_count"]},
    )
    return container


def write_bog_container(container: dict, path: str) -> None:
    validate_bog_container(container)
    Path(path).write_text(_canonical_json(container) + "\n")


def write_bogpk_container(container: dict, path: str) -> None:
    Path(path).write_bytes(encode_bogpk_container(container))


def read_bog_container(path: str) -> dict:
    try:
        container = json.loads(Path(path).read_text())
    except json.JSONDecodeError as exc:
        raise ContainerError(f"Invalid .bog JSON: {exc}") from exc
    validate_bog_container(container)
    return container


def read_container(path: str) -> dict:
    path_obj = Path(path)
    if path_obj.suffix == ".bogpk":
        return read_bogpk_container(path)
    return read_bog_container(path)


def read_bogpk_container(path: str) -> dict:
    return decode_bogpk_container(Path(path).read_bytes())


def encode_bogpk_container(container: dict) -> bytes:
    validate_bog_container(container)

    chunk_size = container["chunk_size"]
    if chunk_size not in CANDIDATE_CHUNK_SIZES:
        raise ContainerError("BOGPK chunk_size must be one of 16, 32, 64, 128")

    flags = 0
    descriptor_bytes = bytearray()
    residual_bytes = bytearray()
    chunks = container["chunks"]
    index = 0

    while index < len(chunks):
        chunk = chunks[index]
        run_length = _zero_residual_run_length(chunks, index)
        if run_length >= 2:
            flags |= BOGPK_FLAG_ZERO_RESIDUAL_RUNS
            descriptor_bytes.append(BOGPK_DESCRIPTOR_SENTINEL)
            descriptor_bytes.extend(_encode_varuint(run_length))
            descriptor_bytes.append(_encode_descriptor(chunk))
            descriptor_bytes.append(chunk["start_byte"])
            descriptor_bytes.append(chunk.get("delta", 0))
            index += run_length
            continue

        descriptor_bytes.append(_encode_descriptor(chunk))
        descriptor_bytes.append(chunk["start_byte"])
        descriptor_bytes.append(chunk.get("delta", 0))
        descriptor_bytes.extend(_encode_varuint(chunk["residual_count"]))
        _append_residuals(residual_bytes, chunk["residuals"])
        index += 1

    original_length = sum(chunk["length"] for chunk in chunks)
    encoded = bytearray()
    encoded.extend(BOGPK_MAGIC)
    encoded.append(BOGPK_VERSION)
    encoded.append(flags)
    encoded.append(CANDIDATE_CHUNK_SIZES.index(chunk_size))
    encoded.extend(_encode_varuint(original_length))
    encoded.extend(_encode_varuint(container["chunk_count"]))
    encoded.extend(_encode_varuint(container["total_residual_count"]))
    encoded.extend(bytes.fromhex(container["whole_sha256"]))
    encoded.extend(descriptor_bytes)
    encoded.extend(residual_bytes)
    return bytes(encoded)


def decode_bogpk_container(data: bytes) -> dict:
    reader = _ByteReader(data)
    if reader.read_bytes(len(BOGPK_MAGIC)) != BOGPK_MAGIC:
        raise ContainerError("Invalid BOGPK magic header")

    version = reader.read_byte()
    if version != BOGPK_VERSION:
        raise ContainerError(f"Unsupported BOGPK version: {version}")

    flags = reader.read_byte()
    if flags & ~(BOGPK_FLAG_TRANSFORMED_HASHES | BOGPK_FLAG_ORIGINAL_HASHES | BOGPK_FLAG_ZERO_RESIDUAL_RUNS):
        raise ContainerError("Unsupported BOGPK flags")
    if flags & (BOGPK_FLAG_TRANSFORMED_HASHES | BOGPK_FLAG_ORIGINAL_HASHES):
        raise ContainerError("BOGPK optional chunk hash streams are not implemented yet")

    chunk_size_code = reader.read_byte()
    try:
        chunk_size = CANDIDATE_CHUNK_SIZES[chunk_size_code]
    except IndexError as exc:
        raise ContainerError("Invalid BOGPK chunk_size_code") from exc

    original_length = _decode_varuint(reader)
    chunk_count = _decode_varuint(reader)
    total_residual_count = _decode_varuint(reader)
    whole_sha256 = reader.read_bytes(32).hex()

    if original_length == 0 and chunk_count != 0:
        raise ContainerError("BOGPK zero original_length requires zero chunk_count")
    if original_length > 0 and chunk_count == 0:
        raise ContainerError("BOGPK nonzero original_length requires chunks")

    descriptors = []
    while len(descriptors) < chunk_count:
        marker = reader.read_byte()
        if marker == BOGPK_DESCRIPTOR_SENTINEL:
            if not flags & BOGPK_FLAG_ZERO_RESIDUAL_RUNS:
                raise ContainerError("BOGPK zero-run sentinel without zero-run flag")
            run_length = _decode_varuint(reader)
            if run_length < 2:
                raise ContainerError("BOGPK zero-residual run length must be at least 2")
            descriptor = reader.read_byte()
            start_byte = reader.read_byte()
            delta = reader.read_byte()
            if len(descriptors) + run_length > chunk_count:
                raise ContainerError("BOGPK zero-residual run exceeds chunk_count")
            for _ in range(run_length):
                descriptors.append(_decode_descriptor(descriptor, start_byte, delta, 0))
            continue

        start_byte = reader.read_byte()
        delta = reader.read_byte()
        residual_count = _decode_varuint(reader)
        descriptors.append(_decode_descriptor(marker, start_byte, delta, residual_count))

    chunks = []
    residual_total = 0
    reconstructed_chunks = []
    for index, descriptor in enumerate(descriptors):
        length = _decoded_chunk_length(index, chunk_count, chunk_size, original_length)
        residuals = _read_residuals(reader, descriptor["residual_count"], length)
        residual_total += len(residuals)
        transformed = _synthesize_residual_chunk(
            descriptor["basis"],
            descriptor["start_byte"],
            descriptor["delta"],
            length,
            residuals,
        )
        original = invert_transform(descriptor["transform"], transformed)
        reconstructed_chunks.append(original)
        chunks.append({
            "index": index,
            "name": f"payload_chunk_{index:04d}",
            "offset": index * chunk_size,
            "length": length,
            "basis": descriptor["basis"],
            "start_byte": descriptor["start_byte"],
            "delta": descriptor["delta"],
            "transform": descriptor["transform"],
            "residual_count": len(residuals),
            "residuals": residuals,
            "chunk_sha256": hashlib.sha256(transformed).hexdigest(),
            "transformed_sha256": hashlib.sha256(transformed).hexdigest(),
            "original_chunk_sha256": hashlib.sha256(original).hexdigest(),
        })

    if residual_total != total_residual_count:
        raise ContainerError("BOGPK residual total mismatch")
    if reader.remaining() != 0:
        raise ContainerError("BOGPK trailing bytes")

    reconstructed = b"".join(reconstructed_chunks)
    if len(reconstructed) != original_length:
        raise ContainerError("BOGPK original length mismatch")
    if hashlib.sha256(reconstructed).hexdigest() != whole_sha256:
        raise ContainerError("BOGPK whole SHA-256 mismatch")

    transform_counts = {transform: 0 for transform in TRANSFORM_ORDER}
    for chunk in chunks:
        transform_counts[chunk["transform"]] += 1

    container = {
        "format": "BOG-1.3",
        "vm_format": "BOGBIN-1.3",
        "pack_mode": "chunked",
        "chunk_size": chunk_size,
        "chunk_count": chunk_count,
        "whole_sha256": whole_sha256,
        "total_residual_count": total_residual_count,
        "chunks": chunks,
        "chunk_tournament_enabled": False,
        "candidate_chunk_sizes": [chunk_size],
        "selected_chunk_size": chunk_size,
        "selected_total_residual_count": total_residual_count,
        "selected_residual_density": _residual_density(total_residual_count, original_length),
        "chunk_tournament_results": [],
        "transform_tournament_enabled": True,
        "candidate_transforms": list(TRANSFORM_ORDER),
        "selected_transform_counts": transform_counts,
    }
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
            f"LOAD_COEFFICIENTS {name} {chunk['start_byte']} {chunk['length']} {chunk.get('delta', 0)}",
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
        data = bytearray(synthesize_basis(
            chunk["basis"],
            chunk["start_byte"],
            chunk["length"],
            delta=chunk.get("delta", 0),
        ))

        for patch in chunk["residuals"]:
            offset = patch["offset"]
            if offset >= len(data):
                raise ContainerError("residual offset out of reconstructed chunk range")
            data[offset] = patch["byte"]

        chunk_bytes = bytes(data)
        actual_chunk_hash = hashlib.sha256(chunk_bytes).hexdigest()
        if actual_chunk_hash != chunk["chunk_sha256"]:
            raise ContainerError(f"chunk {index} SHA-256 mismatch")
        transformed_hash = chunk.get("transformed_sha256", chunk["chunk_sha256"])
        if actual_chunk_hash != transformed_hash:
            raise ContainerError(f"chunk {index} transformed SHA-256 mismatch")
        original_chunk = invert_transform(chunk.get("transform", "identity"), chunk_bytes)
        original_chunk_hash = hashlib.sha256(original_chunk).hexdigest()
        expected_original_hash = chunk.get("original_chunk_sha256", chunk["chunk_sha256"])
        if original_chunk_hash != expected_original_hash:
            raise ContainerError(f"chunk {index} original SHA-256 mismatch")
        reconstructed_chunks.append(original_chunk)

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

    if container["format"] != "BOG-1.3":
        raise ContainerError(f"Unsupported .bog format: {container['format']}")
    if container["vm_format"] != "BOGBIN-1.3":
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
    _validate_tournament_metadata(container)
    _validate_transform_metadata(container)


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
    if chunk.get("transform", "identity") not in TRANSFORM_ORDER:
        raise ContainerError(f"Unsupported reversible transform: {chunk.get('transform')}")
    if not isinstance(chunk["start_byte"], int) or not 0 <= chunk["start_byte"] <= 255:
        raise ContainerError("start_byte must be 0..255")
    if not isinstance(chunk.get("delta", 0), int) or not 0 <= chunk.get("delta", 0) <= 255:
        raise ContainerError("delta must be 0..255")
    if not isinstance(chunk["residual_count"], int) or chunk["residual_count"] < 0:
        raise ContainerError("residual_count must be a non-negative integer")
    if not isinstance(chunk["residuals"], list):
        raise ContainerError("residuals must be a list")
    if len(chunk["residuals"]) != chunk["residual_count"]:
        raise ContainerError("residual_count does not match residual list length")
    if not _is_sha256(chunk["chunk_sha256"]):
        raise ContainerError("chunk_sha256 must be a SHA-256 hex string")
    if "transformed_sha256" in chunk and not _is_sha256(chunk["transformed_sha256"]):
        raise ContainerError("transformed_sha256 must be a SHA-256 hex string")
    if "original_chunk_sha256" in chunk and not _is_sha256(chunk["original_chunk_sha256"]):
        raise ContainerError("original_chunk_sha256 must be a SHA-256 hex string")

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


def _validate_tournament_metadata(container: dict) -> None:
    enabled = container.get("chunk_tournament_enabled", False)
    if not isinstance(enabled, bool):
        raise ContainerError("chunk_tournament_enabled must be boolean")

    candidate_sizes = container.get("candidate_chunk_sizes", [container["chunk_size"]])
    if not isinstance(candidate_sizes, list) or not all(isinstance(size, int) and size > 0 for size in candidate_sizes):
        raise ContainerError("candidate_chunk_sizes must be positive integers")

    selected_chunk_size = container.get("selected_chunk_size", container["chunk_size"])
    selected_total_residual_count = container.get("selected_total_residual_count", container["total_residual_count"])
    selected_residual_density = container.get("selected_residual_density", _residual_density(container["total_residual_count"], _container_length(container)))
    tournament_results = container.get("chunk_tournament_results", [])

    if selected_chunk_size != container["chunk_size"]:
        raise ContainerError("selected_chunk_size must match chunk_size")
    if selected_total_residual_count != container["total_residual_count"]:
        raise ContainerError("selected_total_residual_count must match total_residual_count")
    if not isinstance(selected_residual_density, float):
        raise ContainerError("selected_residual_density must be a float")
    if not isinstance(tournament_results, list):
        raise ContainerError("chunk_tournament_results must be a list")
    if enabled and candidate_sizes != list(CANDIDATE_CHUNK_SIZES):
        raise ContainerError("auto chunk candidate sizes must match v1.3 tournament")


def _validate_transform_metadata(container: dict) -> None:
    enabled = container.get("transform_tournament_enabled", False)
    if not isinstance(enabled, bool):
        raise ContainerError("transform_tournament_enabled must be boolean")

    candidate_transforms = container.get("candidate_transforms", ["identity"])
    if not isinstance(candidate_transforms, list) or not all(transform in TRANSFORM_ORDER for transform in candidate_transforms):
        raise ContainerError("candidate_transforms must be supported reversible transforms")
    if enabled and candidate_transforms != list(TRANSFORM_ORDER):
        raise ContainerError("transform tournament candidates must match deterministic order")

    selected_counts = container.get("selected_transform_counts", {"identity": container["chunk_count"]})
    if not isinstance(selected_counts, dict):
        raise ContainerError("selected_transform_counts must be an object")
    if sum(selected_counts.values()) != container["chunk_count"]:
        raise ContainerError("selected_transform_counts must sum to chunk_count")


def _optimize_chunked_plan(data: bytes, chunk_size: int, transform_tournament: bool) -> dict:
    if transform_tournament:
        return optimize_transformed_chunked_residual_plan(data, chunk_size)
    return optimize_chunked_residual_plan(data, chunk_size)


def _container_length(container: dict) -> int:
    return sum(chunk["length"] for chunk in container["chunks"])


def _residual_density(total_residual_count: int, length: int) -> float:
    if length == 0:
        return 0.0
    return round(total_residual_count / length, 6)


def _is_sha256(value) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(ch in "0123456789abcdef" for ch in value)
    )


def _encode_descriptor(chunk: dict) -> int:
    transform_id = TRANSFORM_ORDER.index(chunk.get("transform", "identity"))
    basis_id = BASIS_ORDER.index(chunk["basis"])
    if basis_id > 15:
        raise ContainerError("BOGPK basis_id out of range")
    return (transform_id << 6) | (basis_id << 2)


def _decode_descriptor(value: int, start_byte: int, delta: int, residual_count: int) -> dict:
    if value & 0b11:
        raise ContainerError("BOGPK descriptor reserved bits must be zero")
    transform_id = (value >> 6) & 0b11
    basis_id = (value >> 2) & 0b1111
    try:
        transform = TRANSFORM_ORDER[transform_id]
        basis = BASIS_ORDER[basis_id]
    except IndexError as exc:
        raise ContainerError("BOGPK descriptor enum out of range") from exc
    return {
        "transform": transform,
        "basis": basis,
        "start_byte": start_byte,
        "delta": delta,
        "residual_count": residual_count,
    }


def _zero_residual_run_length(chunks: list[dict], index: int) -> int:
    first = chunks[index]
    if first["residual_count"] != 0:
        return 0
    length = 1
    for candidate in chunks[index + 1:]:
        if candidate["residual_count"] != 0:
            break
        if (
            candidate.get("transform", "identity") != first.get("transform", "identity")
            or candidate["basis"] != first["basis"]
            or candidate["start_byte"] != first["start_byte"]
            or candidate.get("delta", 0) != first.get("delta", 0)
        ):
            break
        length += 1
    return length


def _append_residuals(output: bytearray, residuals: list[dict]) -> None:
    previous_offset = -1
    for patch in residuals:
        offset = patch["offset"]
        output.extend(_encode_varuint(offset if previous_offset < 0 else offset - previous_offset - 1))
        output.append(patch["byte"])
        previous_offset = offset


def _read_residuals(reader: "_ByteReader", residual_count: int, length: int) -> list[dict]:
    residuals = []
    previous_offset = -1
    for _ in range(residual_count):
        offset_delta = _decode_varuint(reader)
        offset = offset_delta if previous_offset < 0 else previous_offset + 1 + offset_delta
        if not 0 <= offset < length:
            raise ContainerError("BOGPK residual offset out of range")
        residuals.append({"offset": offset, "byte": reader.read_byte()})
        previous_offset = offset
    return residuals


def _synthesize_residual_chunk(basis: str, start_byte: int, delta: int, length: int, residuals: list[dict]) -> bytes:
    data = bytearray(synthesize_basis(basis, start_byte, length, delta=delta))
    for patch in residuals:
        data[patch["offset"]] = patch["byte"]
    return bytes(data)


def _decoded_chunk_length(index: int, chunk_count: int, chunk_size: int, original_length: int) -> int:
    if chunk_count == 0:
        raise ContainerError("BOGPK chunk length requested for empty container")
    if index < chunk_count - 1:
        return chunk_size
    final_length = original_length - ((chunk_count - 1) * chunk_size)
    if not 1 <= final_length <= chunk_size:
        raise ContainerError("BOGPK final chunk length is invalid")
    return final_length


def _encode_varuint(value: int) -> bytes:
    if value < 0:
        raise ContainerError("BOGPK varuint cannot be negative")
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _decode_varuint(reader: "_ByteReader") -> int:
    value = 0
    shift = 0
    raw = []
    while True:
        byte = reader.read_byte()
        raw.append(byte)
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            encoded = _encode_varuint(value)
            if encoded != bytes(raw):
                raise ContainerError("BOGPK non-minimal varuint")
            return value
        shift += 7
        if shift > 63:
            raise ContainerError("BOGPK varuint too large")


class _ByteReader:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.offset = 0

    def read_byte(self) -> int:
        if self.offset >= len(self.data):
            raise ContainerError("Unexpected end of BOGPK data")
        value = self.data[self.offset]
        self.offset += 1
        return value

    def read_bytes(self, length: int) -> bytes:
        if self.offset + length > len(self.data):
            raise ContainerError("Unexpected end of BOGPK data")
        value = self.data[self.offset:self.offset + length]
        self.offset += length
        return value

    def remaining(self) -> int:
        return len(self.data) - self.offset
