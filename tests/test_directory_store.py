import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest

from bogvm.archive import build_directory_archive, restore_directory_archive
from bogvm.bogfs import BogFS
from bogvm.signing import generate_keypair
from bogvm.store import StoreError, install_bundle, package_directory, read_store_index, verify_installed_package


class DirectoryStoreTests(unittest.TestCase):
    def test_directory_archive_roundtrips_mixed_project_folder(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "source"
            recovered = root / "recovered"
            archive = root / "archive"
            _write_mixed_fixture(source)

            manifest = build_directory_archive(source, archive)
            receipt = restore_directory_archive(archive, recovered)

            self.assertEqual(manifest["file_count"], 7)
            self.assertEqual(receipt["execution_status"], "completed")
            self.assertEqual(_hash_tree(source), _hash_tree(recovered))

    def test_bogfs_reads_from_recipes_without_restoring_directory(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "source"
            archive = root / "archive"
            _write_mixed_fixture(source)
            build_directory_archive(source, archive)

            fs = BogFS(archive)

            self.assertEqual(fs.listdir(), ["README.txt", "assets", "data", "site"])
            self.assertIn("index.html", fs.listdir("site"))
            self.assertEqual(fs.read_text("site/index.html"), (source / "site" / "index.html").read_text())
            self.assertEqual(fs.stat("data/config.json")["sha256"], hashlib.sha256((source / "data/config.json").read_bytes()).hexdigest())

    def test_package_store_installs_verified_recipe_bundle(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "source"
            bundle = root / "bundle"
            store = root / "store"
            _write_mixed_fixture(source)

            package_receipt = package_directory(source, bundle, name="mixed-project", version="1.0.0")
            install_receipt = install_bundle(store, bundle)
            index = read_store_index(store)

            self.assertEqual(package_receipt["format"], "BOGPKG-receipt-7.0")
            self.assertEqual(install_receipt["execution_status"], "completed")
            self.assertIn("mixed-project-1.0.0", index["packages"])
            self.assertEqual(_hash_tree(source), _hash_tree(Path(index["packages"]["mixed-project-1.0.0"]["install_dir"])))

    def test_archive_restore_cli_roundtrips_folder(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "source"
            archive = root / "archive"
            recovered = root / "recovered"
            receipt = root / "restore.json"
            create_receipt = root / "archive.json"
            _write_mixed_fixture(source)

            create_result = subprocess.run(
                [sys.executable, "-m", "bogvm", "archive", str(source), str(archive), "--receipt", str(create_receipt)],
                check=False,
                text=True,
                capture_output=True,
            )
            self.assertEqual(create_result.returncode, 0, create_result.stderr + create_result.stdout)
            restore_result = subprocess.run(
                [sys.executable, "-m", "bogvm", "restore", str(archive), str(recovered), "--receipt", str(receipt)],
                check=False,
                text=True,
                capture_output=True,
            )
            self.assertEqual(restore_result.returncode, 0, restore_result.stderr + restore_result.stdout)
            self.assertEqual(json.loads(receipt.read_text())["execution_status"], "completed")
            self.assertEqual(_hash_tree(source), _hash_tree(recovered))

    def test_signed_package_and_dependency_are_verified_transitively(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            private_key = root / "signing.key"
            public_key = root / "signing.pub"
            generate_keypair(private_key, public_key)
            dependency = root / "dependency"
            app = root / "app"
            dependency.mkdir()
            app.mkdir()
            (dependency / "dep.txt").write_text("dependency\n")
            (app / "app.txt").write_text("app\n")
            dep_bundle = root / "dep-bundle"
            app_bundle = root / "app-bundle"
            store = root / "store"

            package_directory(dependency, dep_bundle, "dep", "1.0.0", signing_key=private_key)
            install_bundle(store, dep_bundle, trusted_public_keys=[public_key], require_signature=True)
            package_directory(
                app,
                app_bundle,
                "app",
                "1.0.0",
                dependencies=["dep-1.0.0"],
                signing_key=private_key,
            )
            install_bundle(store, app_bundle, trusted_public_keys=[public_key], require_signature=True)
            receipt = verify_installed_package(store, "app-1.0.0", [public_key], require_signature=True)

            self.assertEqual(receipt["execution_status"], "completed")
            self.assertTrue(receipt["signature_verification"]["trusted"])
            self.assertEqual(receipt["dependency_verifications"]["dep-1.0.0"]["execution_status"], "completed")

            (store / "installed" / "dep-1.0.0" / "dep.txt").write_text("tampered\n")
            rejected = verify_installed_package(store, "app-1.0.0", [public_key], require_signature=True)
            self.assertEqual(rejected["execution_status"], "blocked")
            self.assertIn("dependency verification failed", rejected["failures"][0]["reason"])

    def test_signature_required_rejects_unsigned_package(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "source"
            source.mkdir()
            (source / "file.txt").write_text("unsigned\n")
            bundle = root / "bundle"
            package_directory(source, bundle, "unsigned", "1.0.0")
            with self.assertRaisesRegex(StoreError, "package signature is required"):
                install_bundle(root / "store", bundle, require_signature=True)


def _write_mixed_fixture(root: Path) -> None:
    (root / "site").mkdir(parents=True)
    (root / "data").mkdir()
    (root / "assets").mkdir()
    (root / "site/index.html").write_text("<!doctype html><title>Bog</title><main>roundtrip</main>\n")
    (root / "site/app.py").write_text("def add(a, b):\n    return a + b\n")
    (root / "data/config.json").write_text(json.dumps({"name": "bog", "enabled": True, "items": [1, 2, 3]}, sort_keys=True) + "\n")
    (root / "data/blob.bin").write_bytes(bytes((i * 37 + 11) % 256 for i in range(96)))
    (root / "assets/image.raw").write_bytes(bytes([0, 255, 127, 64]) * 48)
    (root / "assets/audio.raw").write_bytes(bytes((128 + (i % 17) * 3) % 256 for i in range(160)))
    (root / "README.txt").write_text("mixed text fixture\n")


def _hash_tree(root: Path) -> str:
    h = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix()
        data = path.read_bytes()
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(str(len(data)).encode("ascii"))
        h.update(b"\0")
        h.update(hashlib.sha256(data).hexdigest().encode("ascii"))
        h.update(b"\n")
    return h.hexdigest()


if __name__ == "__main__":
    unittest.main()
