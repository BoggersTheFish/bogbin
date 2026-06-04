from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

from .archive import (
    build_directory_archive,
    read_archive_manifest,
    restore_directory_archive,
    tree_hash_for_directory,
    verify_directory_archive,
)


class StoreError(Exception):
    pass


STORE_INDEX_FORMAT = "BOGSTORE-index-3.0"
PACKAGE_RECEIPT_FORMAT = "BOGPKG-receipt-3.0"


def init_store(store_dir: str | Path) -> dict:
    store = Path(store_dir)
    packages = store / "packages"
    installed = store / "installed"
    packages.mkdir(parents=True, exist_ok=True)
    installed.mkdir(parents=True, exist_ok=True)
    index_path = store / "index.json"
    if index_path.exists():
        return read_store_index(store)
    index = {"format": STORE_INDEX_FORMAT, "packages": {}}
    _write_json(index_path, index)
    return index


def package_directory(
    source_dir: str | Path,
    bundle_dir: str | Path,
    name: str,
    version: str,
    chunk_size: int = 64,
    auto_chunk: bool = True,
    transform_tournament: bool = True,
) -> dict:
    bundle = Path(bundle_dir)
    archive_dir = bundle / "archive"
    manifest = build_directory_archive(
        source_dir,
        archive_dir,
        chunk_size=chunk_size,
        auto_chunk=auto_chunk,
        transform_tournament=transform_tournament,
    )
    receipt = {
        "format": PACKAGE_RECEIPT_FORMAT,
        "name": name,
        "version": version,
        "archive_tree_sha256": manifest["tree_sha256"],
        "file_count": manifest["file_count"],
        "bundle_sha256": _directory_hash(bundle),
    }
    _write_json(bundle / "receipt.json", receipt)
    receipt["bundle_sha256"] = _directory_hash(bundle)
    _write_json(bundle / "receipt.json", receipt)
    return receipt


def install_bundle(store_dir: str | Path, bundle_dir: str | Path) -> dict:
    store = Path(store_dir)
    bundle = Path(bundle_dir)
    init_store(store)
    receipt = _read_receipt(bundle / "receipt.json")
    manifest = read_archive_manifest(bundle / "archive")
    if manifest["tree_sha256"] != receipt["archive_tree_sha256"]:
        raise StoreError("bundle archive tree hash does not match receipt")
    expected_bundle_hash = receipt["bundle_sha256"]
    receipt_without_hash = dict(receipt)
    receipt_without_hash["bundle_sha256"] = _directory_hash(bundle)
    if receipt_without_hash["bundle_sha256"] != expected_bundle_hash:
        raise StoreError("bundle hash mismatch")

    key = _package_key(receipt["name"], receipt["version"])
    package_dir = store / "packages" / key
    if package_dir.exists():
        shutil.rmtree(package_dir)
    shutil.copytree(bundle, package_dir)

    install_dir = store / "installed" / key
    restore_receipt = restore_directory_archive(package_dir / "archive", install_dir)
    index = read_store_index(store)
    index["packages"][key] = {
        "name": receipt["name"],
        "version": receipt["version"],
        "package_dir": str(package_dir),
        "install_dir": str(install_dir),
        "archive_tree_sha256": receipt["archive_tree_sha256"],
        "bundle_sha256": expected_bundle_hash,
    }
    _write_json(store / "index.json", index)
    return {
        "format": "BOGSTORE-install-receipt-3.0",
        "package": key,
        "archive_tree_sha256": receipt["archive_tree_sha256"],
        "bundle_sha256": expected_bundle_hash,
        "restore_tree_sha256": restore_receipt["tree_sha256"],
        "execution_status": "completed",
    }


def verify_installed_package(store_dir: str | Path, package: str) -> dict:
    store = Path(store_dir)
    try:
        index = read_store_index(store)
    except StoreError as exc:
        return _blocked_verify_receipt(package, str(exc))

    entry = index["packages"].get(package)
    if entry is None:
        return _blocked_verify_receipt(package, f"package not installed: {package}")

    package_dir = Path(entry["package_dir"])
    install_dir = Path(entry["install_dir"])
    failures = []

    archive_receipt = verify_directory_archive(package_dir / "archive")
    if archive_receipt["execution_status"] != "completed":
        failures.extend(
            {"path": failure["path"], "reason": f"archive: {failure['reason']}"}
            for failure in archive_receipt["failures"]
        )

    installed_tree_sha256 = None
    if not install_dir.is_dir():
        failures.append({"path": str(install_dir), "reason": "installed directory is missing"})
    else:
        installed_tree_sha256 = tree_hash_for_directory(install_dir)
        if installed_tree_sha256 != entry["archive_tree_sha256"]:
            failures.append({
                "path": str(install_dir),
                "reason": "installed tree hash mismatch",
            })

    return {
        "format": "BOGSTORE-verify-receipt-3.0",
        "package": package,
        "store": str(store),
        "archive_tree_sha256": entry["archive_tree_sha256"],
        "installed_tree_sha256": installed_tree_sha256,
        "archive_execution_status": archive_receipt["execution_status"],
        "failures": failures,
        "execution_status": "completed" if not failures else "blocked",
    }


def read_store_index(store_dir: str | Path) -> dict:
    path = Path(store_dir) / "index.json"
    try:
        index = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise StoreError(f"invalid store index: {exc}") from exc
    if index.get("format") != STORE_INDEX_FORMAT:
        raise StoreError(f"unsupported store index format: {index.get('format')}")
    if not isinstance(index.get("packages"), dict):
        raise StoreError("store packages must be an object")
    return index


def _read_receipt(path: Path) -> dict:
    try:
        receipt = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise StoreError(f"invalid package receipt: {exc}") from exc
    if receipt.get("format") != PACKAGE_RECEIPT_FORMAT:
        raise StoreError(f"unsupported package receipt format: {receipt.get('format')}")
    for field in ("name", "version", "archive_tree_sha256", "bundle_sha256"):
        if field not in receipt:
            raise StoreError(f"missing package receipt field: {field}")
    return receipt


def _package_key(name: str, version: str) -> str:
    safe = f"{name}-{version}".replace("/", "_").replace("\\", "_")
    if not safe.strip():
        raise StoreError("package name/version must not be empty")
    return safe


def _directory_hash(path: Path) -> str:
    h = hashlib.sha256()
    for item in sorted(p for p in path.rglob("*") if p.is_file()):
        if item.name == "receipt.json":
            try:
                receipt = json.loads(item.read_text())
            except json.JSONDecodeError:
                receipt = None
            if isinstance(receipt, dict) and "bundle_sha256" in receipt:
                receipt = dict(receipt)
                receipt["bundle_sha256"] = ""
                data = json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode("utf-8")
            else:
                data = item.read_bytes()
        else:
            data = item.read_bytes()
        rel = item.relative_to(path).as_posix()
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(data)
        h.update(b"\n")
    return h.hexdigest()


def _write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")


def _blocked_verify_receipt(package: str, reason: str) -> dict:
    return {
        "format": "BOGSTORE-verify-receipt-3.0",
        "package": package,
        "failures": [{"path": package, "reason": reason}],
        "execution_status": "blocked",
    }
