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
from .schema import SchemaError, validate_schema
from .signing import sign_object, verify_object_signature


class StoreError(Exception):
    pass


STORE_INDEX_FORMAT = "BOGSTORE-index-3.0"
PACKAGE_RECEIPT_FORMAT = "BOGPKG-receipt-7.0"


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
    dependencies: list[str] | None = None,
    signing_key: str | Path | None = None,
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
        "dependencies": sorted(set(dependencies or [])),
        "bundle_sha256": _directory_hash(bundle),
    }
    _write_json(bundle / "receipt.json", receipt)
    receipt["bundle_sha256"] = _directory_hash(bundle)
    if signing_key is not None:
        receipt["signature"] = sign_object(receipt, signing_key)
    validate_schema(receipt, "package-receipt.schema.json")
    _write_json(bundle / "receipt.json", receipt)
    return receipt


def install_bundle(
    store_dir: str | Path,
    bundle_dir: str | Path,
    trusted_public_keys: list[str | Path] | None = None,
    require_signature: bool = False,
) -> dict:
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
    signature_verification = _verify_signature(receipt, trusted_public_keys or [], require_signature)
    if signature_verification["execution_status"] != "completed":
        raise StoreError(signature_verification["failures"][0]["reason"])

    index = read_store_index(store)
    missing_dependencies = [dependency for dependency in receipt["dependencies"] if dependency not in index["packages"]]
    if missing_dependencies:
        raise StoreError(f"missing package dependencies: {', '.join(missing_dependencies)}")
    for dependency in receipt["dependencies"]:
        dependency_receipt = verify_installed_package(
            store,
            dependency,
            trusted_public_keys=trusted_public_keys,
            require_signature=require_signature,
        )
        if dependency_receipt["execution_status"] != "completed":
            raise StoreError(f"dependency verification failed: {dependency}")

    key = _package_key(receipt["name"], receipt["version"])
    package_dir = store / "packages" / key
    if package_dir.exists():
        shutil.rmtree(package_dir)
    shutil.copytree(bundle, package_dir)

    install_dir = store / "installed" / key
    restore_receipt = restore_directory_archive(package_dir / "archive", install_dir)
    index["packages"][key] = {
        "name": receipt["name"],
        "version": receipt["version"],
        "package_dir": str(package_dir),
        "install_dir": str(install_dir),
        "archive_tree_sha256": receipt["archive_tree_sha256"],
        "bundle_sha256": expected_bundle_hash,
        "dependencies": receipt["dependencies"],
        "signature": receipt.get("signature"),
        "signature_verification": signature_verification,
    }
    _write_json(store / "index.json", index)
    return {
        "format": "BOGSTORE-install-receipt-3.0",
        "package": key,
        "package_dir": str(package_dir),
        "install_dir": str(install_dir),
        "archive_tree_sha256": receipt["archive_tree_sha256"],
        "bundle_sha256": expected_bundle_hash,
        "restore_tree_sha256": restore_receipt["tree_sha256"],
        "dependencies": receipt["dependencies"],
        "signature_verification": signature_verification,
        "execution_status": "completed",
    }


def verify_installed_package(
    store_dir: str | Path,
    package: str,
    trusted_public_keys: list[str | Path] | None = None,
    require_signature: bool = False,
    _seen: set[str] | None = None,
) -> dict:
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
    seen = set(_seen or ())
    if package in seen:
        return _blocked_verify_receipt(package, f"dependency cycle detected: {package}")
    seen.add(package)
    try:
        package_receipt = _read_receipt(package_dir / "receipt.json")
    except StoreError as exc:
        return _blocked_verify_receipt(package, str(exc))
    signature_verification = _verify_signature(package_receipt, trusted_public_keys or [], require_signature)
    failures.extend(signature_verification.get("failures", []))
    actual_bundle_hash = _directory_hash(package_dir)
    if actual_bundle_hash != package_receipt["bundle_sha256"]:
        failures.append({"path": str(package_dir), "reason": "installed package bundle hash mismatch"})
    dependencies = package_receipt["dependencies"]
    if entry.get("dependencies", []) != dependencies:
        failures.append({"path": package, "reason": "store index dependency metadata mismatch"})
    missing_dependencies = [
        dependency for dependency in dependencies
        if dependency not in index["packages"]
    ]
    failures.extend(
        {"path": dependency, "reason": f"missing package dependency: {dependency}"}
        for dependency in missing_dependencies
    )
    dependency_verifications = {}
    for dependency in dependencies:
        if dependency in missing_dependencies:
            continue
        dependency_receipt = verify_installed_package(
            store,
            dependency,
            trusted_public_keys=trusted_public_keys,
            require_signature=require_signature,
            _seen=seen,
        )
        dependency_verifications[dependency] = dependency_receipt
        if dependency_receipt["execution_status"] != "completed":
            failures.append({"path": dependency, "reason": f"dependency verification failed: {dependency}"})

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
        if installed_tree_sha256 != package_receipt["archive_tree_sha256"]:
            failures.append({
                "path": str(install_dir),
                "reason": "installed tree hash mismatch",
            })

    return {
        "format": "BOGSTORE-verify-receipt-3.0",
        "package": package,
        "store": str(store),
        "archive_tree_sha256": package_receipt["archive_tree_sha256"],
        "bundle_sha256": package_receipt["bundle_sha256"],
        "actual_bundle_sha256": actual_bundle_hash,
        "installed_tree_sha256": installed_tree_sha256,
        "archive_execution_status": archive_receipt["execution_status"],
        "dependencies": dependencies,
        "dependency_verifications": dependency_verifications,
        "signature_verification": signature_verification,
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
    try:
        validate_schema(receipt, "package-receipt.schema.json")
    except SchemaError as exc:
        raise StoreError(str(exc)) from exc
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
                receipt.pop("signature", None)
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


def _verify_signature(receipt: dict, trusted_public_keys: list[str | Path], require_signature: bool) -> dict:
    signature = receipt.get("signature")
    if signature is None:
        failures = [{"path": "receipt.json", "reason": "package signature is required"}] if require_signature else []
        return {
            "format": "BOGPKG-signature-verification-receipt-7.0",
            "signed": False,
            "trusted": False,
            "failures": failures,
            "execution_status": "blocked" if failures else "completed",
        }
    unsigned = dict(receipt)
    unsigned.pop("signature")
    result = verify_object_signature(unsigned, signature, trusted_public_keys)
    failures = [] if result["verified"] else [{"path": "receipt.json", "reason": result["reason"]}]
    return {
        "format": "BOGPKG-signature-verification-receipt-7.0",
        "signed": True,
        "trusted": result["verified"],
        "key_id": result["key_id"],
        "failures": failures,
        "execution_status": "completed" if not failures else "blocked",
    }
