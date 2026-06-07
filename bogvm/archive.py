from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

from .container import (
    BOG_FORMAT,
    BOGPK_VERSION,
    build_bog_container_v1,
    reconstruct_bog_container_bytes,
    read_bogpk_container,
    write_bogpk_container,
)
from .schema import SchemaError, validate_schema


class ArchiveError(Exception):
    pass


ARCHIVE_FORMAT = "BOGARCHIVE-2.0"


def build_directory_archive(
    source_dir: str | Path,
    archive_dir: str | Path,
    chunk_size: int = 64,
    auto_chunk: bool = True,
    transform_tournament: bool = True,
) -> dict:
    source = Path(source_dir)
    archive = Path(archive_dir)
    if not source.is_dir():
        raise ArchiveError("source_dir must be a directory")
    if archive.exists():
        shutil.rmtree(archive)
    objects_dir = archive / "objects"
    objects_dir.mkdir(parents=True)

    files = []
    for path in sorted(p for p in source.rglob("*") if p.is_file()):
        rel = path.relative_to(source).as_posix()
        data = path.read_bytes()
        sha256 = hashlib.sha256(data).hexdigest()
        object_name = f"{sha256}.bogpk"
        object_path = objects_dir / object_name
        if not object_path.exists():
            container = build_bog_container_v1(
                data,
                chunk_size=chunk_size,
                auto_chunk=auto_chunk,
                transform_tournament=transform_tournament,
            )
            write_bogpk_container(container, str(object_path))
        files.append({
            "path": rel,
            "size": len(data),
            "sha256": sha256,
            "object": f"objects/{object_name}",
        })

    manifest = {
        "format": ARCHIVE_FORMAT,
        "container_format": BOG_FORMAT,
        "bogpk_version": BOGPK_VERSION,
        "source": str(source),
        "file_count": len(files),
        "files": files,
        "tree_sha256": _tree_hash(files),
    }
    validate_schema(manifest, "archive-manifest.schema.json")
    _write_manifest(archive / "manifest.json", manifest)
    return manifest


def restore_directory_archive(archive_dir: str | Path, output_dir: str | Path) -> dict:
    archive = Path(archive_dir)
    output = Path(output_dir)
    manifest = read_archive_manifest(archive)
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    restored = []
    for entry in manifest["files"]:
        target = output / entry["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        data = read_archive_file(archive, entry["path"], manifest=manifest)
        target.write_bytes(data)
        restored.append({
            "path": entry["path"],
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        })

    receipt = {
        "format": "BOGARCHIVE-restore-receipt-2.0",
        "archive": str(archive),
        "output": str(output),
        "file_count": len(restored),
        "tree_sha256": _tree_hash(restored),
        "expected_tree_sha256": manifest["tree_sha256"],
        "all_hashes_match": _tree_hash(restored) == manifest["tree_sha256"],
        "execution_status": "completed" if _tree_hash(restored) == manifest["tree_sha256"] else "blocked",
    }
    if receipt["execution_status"] != "completed":
        raise ArchiveError("restored directory hash mismatch")
    return receipt


def verify_directory_archive(archive_dir: str | Path) -> dict:
    archive = Path(archive_dir)
    failures = []
    try:
        manifest = read_archive_manifest(archive)
    except ArchiveError as exc:
        return {
            "format": "BOGARCHIVE-verify-receipt-2.0",
            "archive": str(archive),
            "file_count": 0,
            "verified_file_count": 0,
            "failures": [{"path": "manifest.json", "reason": str(exc)}],
            "execution_status": "blocked",
        }

    verified = []
    for entry in manifest["files"]:
        try:
            data = read_archive_file(archive, entry["path"], manifest=manifest)
        except Exception as exc:
            failures.append({"path": entry["path"], "reason": str(exc)})
            continue
        verified.append({
            "path": entry["path"],
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        })

    tree_sha256 = _tree_hash(verified)
    if not failures and tree_sha256 != manifest["tree_sha256"]:
        failures.append({
            "path": ".",
            "reason": "verified archive tree hash mismatch",
        })

    return {
        "format": "BOGARCHIVE-verify-receipt-2.0",
        "archive": str(archive),
        "file_count": manifest["file_count"],
        "verified_file_count": len(verified),
        "tree_sha256": tree_sha256,
        "expected_tree_sha256": manifest["tree_sha256"],
        "failures": failures,
        "execution_status": "completed" if not failures else "blocked",
    }


def read_archive_manifest(archive_dir: str | Path) -> dict:
    path = Path(archive_dir) / "manifest.json"
    try:
        manifest = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ArchiveError(f"invalid archive manifest: {exc}") from exc
    try:
        validate_schema(manifest, "archive-manifest.schema.json")
    except SchemaError as exc:
        raise ArchiveError(str(exc)) from exc
    if manifest.get("format") != ARCHIVE_FORMAT:
        raise ArchiveError(f"unsupported archive format: {manifest.get('format')}")
    files = manifest.get("files")
    if not isinstance(files, list):
        raise ArchiveError("archive files must be a list")
    if manifest.get("file_count") != len(files):
        raise ArchiveError("archive file_count mismatch")
    if _tree_hash(files) != manifest.get("tree_sha256"):
        raise ArchiveError("archive tree hash mismatch")
    return manifest


def read_archive_file(archive_dir: str | Path, relative_path: str, manifest: dict | None = None) -> bytes:
    archive = Path(archive_dir)
    manifest = manifest or read_archive_manifest(archive)
    if Path(relative_path).is_absolute() or ".." in Path(relative_path).parts:
        raise ArchiveError("archive path must be relative and contained")
    matches = [entry for entry in manifest["files"] if entry["path"] == relative_path]
    if not matches:
        raise ArchiveError(f"file not found in archive: {relative_path}")
    entry = matches[0]
    object_path = archive / entry["object"]
    container = read_bogpk_container(str(object_path))
    data = reconstruct_bog_container_bytes(container)
    if len(data) != entry["size"] or hashlib.sha256(data).hexdigest() != entry["sha256"]:
        raise ArchiveError(f"archive object verification failed: {relative_path}")
    return data


def _tree_hash(files: list[dict]) -> str:
    h = hashlib.sha256()
    for entry in sorted(files, key=lambda item: item["path"]):
        h.update(entry["path"].encode("utf-8"))
        h.update(b"\0")
        h.update(str(entry["size"]).encode("ascii"))
        h.update(b"\0")
        h.update(entry["sha256"].encode("ascii"))
        h.update(b"\n")
    return h.hexdigest()


def tree_hash_for_directory(root: str | Path) -> str:
    files = []
    for path in sorted(p for p in Path(root).rglob("*") if p.is_file()):
        data = path.read_bytes()
        files.append({
            "path": path.relative_to(root).as_posix(),
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        })
    return _tree_hash(files)


def _write_manifest(path: Path, manifest: dict) -> None:
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
