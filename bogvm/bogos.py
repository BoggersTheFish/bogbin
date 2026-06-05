from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

from .archive import (
    ArchiveError,
    build_directory_archive,
    restore_directory_archive,
    verify_directory_archive,
)
from .bogfs import BogFS
from .store import init_store, install_bundle, package_directory, read_store_index, verify_installed_package


class BogOSError(Exception):
    pass


WORKSPACE_FORMAT = "BOGOS-workspace-4.0"
RECEIPT_FORMAT = "BOGOS-receipt-4.0"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="bog")
    parser.add_argument("--workspace", default=None)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init")
    p_init.add_argument("workspace")

    p_archive = sub.add_parser("archive")
    p_archive.add_argument("project")
    p_archive.add_argument("--name", default=None)

    p_restore = sub.add_parser("restore")
    p_restore.add_argument("archive")
    p_restore.add_argument("output", nargs="?")

    p_fs = sub.add_parser("fs")
    fs_sub = p_fs.add_subparsers(dest="fs_cmd", required=True)
    p_fs_mount = fs_sub.add_parser("mount")
    p_fs_mount.add_argument("archive")
    p_fs_mount.add_argument("name", nargs="?")
    p_fs_read = fs_sub.add_parser("read")
    p_fs_read.add_argument("mount")
    p_fs_read.add_argument("path")
    p_fs_ls = fs_sub.add_parser("ls")
    p_fs_ls.add_argument("mount")
    p_fs_ls.add_argument("path", nargs="?", default="")
    p_fs_stat = fs_sub.add_parser("stat")
    p_fs_stat.add_argument("mount")
    p_fs_stat.add_argument("path")

    p_store = sub.add_parser("store")
    store_sub = p_store.add_subparsers(dest="store_cmd", required=True)
    p_store_install = store_sub.add_parser("install")
    p_store_install.add_argument("package")
    p_store_install.add_argument("--name", default=None)
    p_store_install.add_argument("--version", default="1.0.0")
    p_store_verify = store_sub.add_parser("verify")
    p_store_verify.add_argument("package")
    p_store_package = store_sub.add_parser("package")
    p_store_package.add_argument("project")
    p_store_package.add_argument("--name", required=True)
    p_store_package.add_argument("--version", default="1.0.0")

    p_app = sub.add_parser("app")
    app_sub = p_app.add_subparsers(dest="app_cmd", required=True)
    p_app_run = app_sub.add_parser("run")
    p_app_run.add_argument("app")
    p_app_run.add_argument("args", nargs=argparse.REMAINDER)

    p_status = sub.add_parser("status")
    p_status.add_argument("--verbose", action="store_true")

    sub.add_parser("doctor")

    p_corrupt = sub.add_parser("corrupt-test")
    p_corrupt.add_argument("package", nargs="?")

    p_receipt = sub.add_parser("receipt")
    p_receipt.add_argument("receipt", nargs="?", default="latest")

    p_workspace = sub.add_parser("workspace")
    workspace_sub = p_workspace.add_subparsers(dest="workspace_cmd", required=True)
    workspace_sub.add_parser("tree")

    p_demo = sub.add_parser("demo")
    p_demo.add_argument("target", nargs="?")
    p_demo.add_argument("--public", action="store_true")

    args = parser.parse_args(argv)

    try:
        if args.cmd == "init":
            result = init_workspace(args.workspace)
            print(json.dumps(result, indent=2, sort_keys=True))
            return

        workspace = Workspace.open(args.workspace)

        if args.cmd == "archive":
            receipt = workspace.archive_project(args.project, name=args.name)
            _print_receipt(receipt)
        elif args.cmd == "restore":
            receipt = workspace.restore_archive(args.archive, output=args.output)
            _print_receipt(receipt)
            if receipt["execution_status"] != "completed":
                raise SystemExit(1)
        elif args.cmd == "fs":
            _run_fs(workspace, args)
        elif args.cmd == "store":
            _run_store(workspace, args)
        elif args.cmd == "app":
            _run_app(workspace, args)
        elif args.cmd == "status":
            print(json.dumps(workspace.status(verbose=args.verbose), indent=2, sort_keys=True))
        elif args.cmd == "doctor":
            receipt = workspace.doctor()
            _print_receipt(receipt)
            if receipt["execution_status"] != "completed":
                raise SystemExit(1)
        elif args.cmd == "corrupt-test":
            receipt = workspace.corrupt_test(package=args.package)
            _print_receipt(receipt)
            if receipt["execution_status"] != "completed":
                raise SystemExit(1)
        elif args.cmd == "receipt":
            print(json.dumps(workspace.read_receipt(args.receipt), indent=2, sort_keys=True))
        elif args.cmd == "workspace":
            if args.workspace_cmd == "tree":
                print(json.dumps(workspace.workspace_tree(), indent=2, sort_keys=True))
        elif args.cmd == "demo":
            receipt = workspace.demo(args.target, public=args.public or args.target == "pack")
            _print_receipt(receipt)
            if receipt["execution_status"] != "completed":
                raise SystemExit(1)
    except BogOSError as exc:
        print(f"bog: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


def init_workspace(path: str | Path) -> dict:
    root = Path(path)
    root.mkdir(parents=True, exist_ok=True)
    bogos = root / ".bogos"
    for child in ("archives", "bundles", "receipts", "store", "demo"):
        (bogos / child).mkdir(parents=True, exist_ok=True)
    (root / "restored").mkdir(exist_ok=True)
    init_store(bogos / "store")
    state = {
        "format": WORKSPACE_FORMAT,
        "root": str(root.resolve()),
        "archives": {},
        "mounts": {},
        "packages": {},
        "apps": {},
        "receipts": [],
        "last_receipt": None,
    }
    _write_json(bogos / "state.json", state)
    return {
        "format": "BOGOS-init-receipt-4.0",
        "workspace": str(root.resolve()),
        "execution_status": "completed",
    }


class Workspace:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.bogos = self.root / ".bogos"
        self.state_path = self.bogos / "state.json"
        self.state = self._read_state()

    @classmethod
    def open(cls, root: str | Path | None = None) -> "Workspace":
        if root is not None:
            candidate = Path(root)
            if candidate.name == ".bogos":
                candidate = candidate.parent
            if not (candidate / ".bogos" / "state.json").exists():
                raise BogOSError(f"not a BogOS workspace: {candidate}")
            return cls(candidate)

        current = Path.cwd()
        for candidate in (current, *current.parents):
            if (candidate / ".bogos" / "state.json").exists():
                return cls(candidate)
        raise BogOSError("not inside a BogOS workspace; run `bog init <workspace>` first")

    def archive_project(self, project: str | Path, name: str | None = None) -> dict:
        source = self._resolve_path(project)
        archive_name = _safe_name(name or source.name)
        archive_dir = self.bogos / "archives" / f"{archive_name}.bogarchive"
        manifest = build_directory_archive(source, archive_dir)
        receipt = {
            "format": "BOGOS-archive-receipt-4.0",
            "workspace": str(self.root),
            "source": str(source),
            "archive": archive_name,
            "archive_path": str(archive_dir),
            "file_count": manifest["file_count"],
            "tree_sha256": manifest["tree_sha256"],
            "execution_status": "completed",
        }
        self.state["archives"][archive_name] = {
            "path": str(archive_dir),
            "tree_sha256": manifest["tree_sha256"],
            "file_count": manifest["file_count"],
        }
        return self._record_receipt("archive", archive_name, receipt)

    def restore_archive(self, archive: str, output: str | Path | None = None) -> dict:
        archive_name, archive_path = self._resolve_archive(archive)
        output_path = self._resolve_path(output) if output else self.root / "restored" / archive_name
        try:
            restore_receipt = restore_directory_archive(archive_path, output_path)
            receipt = {
                "format": "BOGOS-restore-receipt-4.0",
                "workspace": str(self.root),
                "archive": archive_name,
                "archive_path": str(archive_path),
                "output": str(output_path),
                "tree_sha256": restore_receipt["tree_sha256"],
                "expected_tree_sha256": restore_receipt["expected_tree_sha256"],
                "failures": [],
                "execution_status": "completed",
            }
        except Exception as exc:
            receipt = {
                "format": "BOGOS-restore-receipt-4.0",
                "workspace": str(self.root),
                "archive": archive_name,
                "archive_path": str(archive_path),
                "output": str(output_path),
                "failures": [{"path": str(archive_path), "reason": str(exc)}],
                "execution_status": "blocked",
            }
        return self._record_receipt("restore", archive_name, receipt)

    def mount_archive(self, archive: str, name: str | None = None) -> dict:
        archive_name, archive_path = self._resolve_archive(archive)
        mount_name = _safe_name(name or archive_name)
        verify_receipt = verify_directory_archive(archive_path)
        receipt = {
            "format": "BOGOS-fs-mount-receipt-4.0",
            "workspace": str(self.root),
            "mount": mount_name,
            "archive": archive_name,
            "archive_path": str(archive_path),
            "verification": verify_receipt,
            "execution_status": verify_receipt["execution_status"],
        }
        if verify_receipt["execution_status"] == "completed":
            self.state["mounts"][mount_name] = {
                "archive": archive_name,
                "path": str(archive_path),
            }
        return self._record_receipt("fs-mount", mount_name, receipt)

    def read_mount(self, mount: str, path: str) -> tuple[bytes, dict]:
        mount_info = self._resolve_mount(mount)
        try:
            data = BogFS(mount_info["path"]).read_bytes(path)
            receipt = {
                "format": "BOGOS-fs-read-receipt-4.0",
                "workspace": str(self.root),
                "mount": mount,
                "path": path,
                "size": len(data),
                "execution_status": "completed",
            }
        except Exception as exc:
            data = b""
            receipt = {
                "format": "BOGOS-fs-read-receipt-4.0",
                "workspace": str(self.root),
                "mount": mount,
                "path": path,
                "failures": [{"path": path, "reason": str(exc)}],
                "execution_status": "blocked",
            }
        return data, self._record_receipt("fs-read", mount, receipt)

    def list_mount(self, mount: str, path: str = "") -> list[str]:
        mount_info = self._resolve_mount(mount)
        return BogFS(mount_info["path"]).listdir(path)

    def stat_mount(self, mount: str, path: str) -> dict:
        mount_info = self._resolve_mount(mount)
        return BogFS(mount_info["path"]).stat(path)

    def package_project(self, project: str | Path, name: str, version: str) -> dict:
        source = self._resolve_path(project)
        key = _package_key(name, version)
        bundle_dir = self.bogos / "bundles" / key
        package_receipt = package_directory(source, bundle_dir, name=name, version=version)
        receipt = {
            "format": "BOGOS-store-package-receipt-4.0",
            "workspace": str(self.root),
            "bundle": str(bundle_dir),
            "package": key,
            "package_receipt": package_receipt,
            "execution_status": "completed",
        }
        self.state["packages"][key] = {"bundle": str(bundle_dir), "installed": False}
        return self._record_receipt("store-package", key, receipt)

    def install_package(self, package: str | Path, name: str | None = None, version: str = "1.0.0") -> dict:
        package_path = self._resolve_path(package)
        if (package_path / "receipt.json").exists():
            bundle_dir = package_path
        else:
            package_name = name or package_path.name
            key = _package_key(package_name, version)
            bundle_dir = self.bogos / "bundles" / key
            package_directory(package_path, bundle_dir, name=package_name, version=version)

        install_receipt = install_bundle(self.bogos / "store", bundle_dir)
        key = install_receipt["package"]
        receipt = {
            "format": "BOGOS-store-install-receipt-4.0",
            "workspace": str(self.root),
            "bundle": str(bundle_dir),
            "package": key,
            "store_receipt": install_receipt,
            "execution_status": install_receipt["execution_status"],
        }
        self.state["packages"][key] = {"bundle": str(bundle_dir), "installed": True}
        self._index_package_apps(key, Path(install_receipt.get("install_dir", self.bogos / "store" / "installed" / key)))
        return self._record_receipt("store-install", key, receipt)

    def verify_package(self, package: str) -> dict:
        receipt = verify_installed_package(self.bogos / "store", package)
        wrapped = {
            "format": "BOGOS-store-verify-receipt-4.0",
            "workspace": str(self.root),
            "package": package,
            "verification": receipt,
            "failures": receipt.get("failures", []),
            "execution_status": receipt["execution_status"],
        }
        return self._record_receipt("store-verify", package, wrapped)

    def run_app(self, app: str, extra_args: list[str] | None = None) -> dict:
        extra_args = extra_args or []
        self.state = self._read_state()
        app_info = self.state.get("apps", {}).get(app)
        if app_info is None:
            receipt = {
                "format": "BOGOS-app-run-receipt-5.0",
                "workspace": str(self.root),
                "app": app,
                "failures": [{"path": app, "reason": f"app not installed: {app}"}],
                "execution_status": "blocked",
            }
            return self._record_receipt("app-run", app, receipt)

        verify_receipt = verify_installed_package(self.bogos / "store", app_info["package"])
        if verify_receipt["execution_status"] != "completed":
            receipt = {
                "format": "BOGOS-app-run-receipt-5.0",
                "workspace": str(self.root),
                "app": app,
                "package": app_info["package"],
                "verification": verify_receipt,
                "failures": verify_receipt.get("failures", []),
                "execution_status": "blocked",
            }
            return self._record_receipt("app-run", app, receipt)

        install_dir = Path(app_info["install_dir"])
        command = [str(part) for part in app_info["command"]] + extra_args
        try:
            result = subprocess.run(
                command,
                cwd=install_dir,
                check=False,
                text=True,
                capture_output=True,
            )
            failures = [] if result.returncode == 0 else [{
                "path": app,
                "reason": f"app exited with code {result.returncode}",
            }]
            receipt = {
                "format": "BOGOS-app-run-receipt-5.0",
                "workspace": str(self.root),
                "app": app,
                "package": app_info["package"],
                "command": command,
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "verification": verify_receipt,
                "failures": failures,
                "execution_status": "completed" if result.returncode == 0 else "blocked",
            }
        except OSError as exc:
            receipt = {
                "format": "BOGOS-app-run-receipt-5.0",
                "workspace": str(self.root),
                "app": app,
                "package": app_info["package"],
                "command": command,
                "failures": [{"path": app, "reason": str(exc)}],
                "execution_status": "blocked",
            }
        return self._record_receipt("app-run", app, receipt)

    def doctor(self) -> dict:
        self.state = self._read_state()
        checks = []
        failures = []
        for dirname in ("archives", "bundles", "receipts", "store", "demo"):
            path = self.bogos / dirname
            ok = path.is_dir()
            checks.append({"name": f"directory:{dirname}", "path": str(path), "ok": ok})
            if not ok:
                failures.append({"path": str(path), "reason": "workspace directory missing"})

        for name, entry in sorted(self.state["archives"].items()):
            verify_receipt = verify_directory_archive(entry["path"])
            ok = verify_receipt["execution_status"] == "completed"
            checks.append({"name": f"archive:{name}", "ok": ok, "receipt": verify_receipt})
            if not ok:
                failures.extend(
                    {"path": failure["path"], "reason": f"archive {name}: {failure['reason']}"}
                    for failure in verify_receipt.get("failures", [])
                )

        for package in sorted(self.state["packages"]):
            verify_receipt = verify_installed_package(self.bogos / "store", package)
            ok = verify_receipt["execution_status"] == "completed"
            checks.append({"name": f"package:{package}", "ok": ok, "receipt": verify_receipt})
            if not ok:
                failures.extend(
                    {"path": failure["path"], "reason": f"package {package}: {failure['reason']}"}
                    for failure in verify_receipt.get("failures", [])
                )

        receipt = {
            "format": "BOGOS-doctor-receipt-4.1",
            "workspace": str(self.root),
            "checks": checks,
            "failures": failures,
            "execution_status": "completed" if not failures else "blocked",
        }
        return self._record_receipt("doctor", "workspace", receipt)

    def corrupt_test(self, package: str | None = None) -> dict:
        self.state = self._read_state()
        package = package or (sorted(self.state["packages"])[0] if self.state["packages"] else None)
        if package is None:
            receipt = {
                "format": "BOGOS-corrupt-test-receipt-4.1",
                "workspace": str(self.root),
                "failures": [{"path": "store", "reason": "no installed package available for corrupt-test"}],
                "execution_status": "blocked",
            }
            return self._record_receipt("corrupt-test", "none", receipt)

        try:
            index = read_store_index(self.bogos / "store")
            install_dir = Path(index["packages"][package]["install_dir"])
            target = next(path for path in sorted(install_dir.rglob("*")) if path.is_file())
            target.write_bytes(target.read_bytes() + b"\nBOG_CORRUPT_TEST\n")
            verify_receipt = verify_installed_package(self.bogos / "store", package)
            rejected = verify_receipt["execution_status"] == "blocked"
            receipt = {
                "format": "BOGOS-corrupt-test-receipt-4.1",
                "workspace": str(self.root),
                "package": package,
                "corrupted_path": str(target),
                "verification": verify_receipt,
                "rejected": rejected,
                "failures": verify_receipt.get("failures", []),
                "execution_status": "completed" if rejected else "blocked",
            }
        except Exception as exc:
            receipt = {
                "format": "BOGOS-corrupt-test-receipt-4.1",
                "workspace": str(self.root),
                "package": package,
                "failures": [{"path": package, "reason": str(exc)}],
                "execution_status": "blocked",
            }
        return self._record_receipt("corrupt-test", package, receipt)

    def status(self, verbose: bool = False) -> dict:
        self.state = self._read_state()
        status = {
            "format": "BOGOS-status-4.0",
            "workspace": str(self.root),
            "archive_count": len(self.state["archives"]),
            "mount_count": len(self.state["mounts"]),
            "package_count": len(self.state["packages"]),
            "receipt_count": len(self.state["receipts"]),
            "archives": sorted(self.state["archives"]),
            "mounts": sorted(self.state["mounts"]),
            "packages": sorted(self.state["packages"]),
            "last_receipt": self.state.get("last_receipt"),
            "execution_status": "completed",
        }
        if verbose:
            status["format"] = "BOGOS-status-verbose-4.1"
            status["archive_details"] = self.state["archives"]
            status["mount_details"] = self.state["mounts"]
            status["package_details"] = self.state["packages"]
            status["app_details"] = self.state.get("apps", {})
            status["receipt_details"] = self.state["receipts"]
            if self.state.get("last_receipt"):
                status["last_receipt_summary"] = _receipt_summary(json.loads(Path(self.state["last_receipt"]).read_text()))
        return status

    def read_receipt(self, selector: str = "last") -> dict:
        self.state = self._read_state()
        if selector in {"last", "latest"}:
            receipt_path = self.state.get("last_receipt")
            if not receipt_path:
                raise BogOSError("workspace has no receipts")
        elif selector.isdigit():
            index = int(selector) - 1
            try:
                receipt_path = self.state["receipts"][index]["path"]
            except IndexError as exc:
                raise BogOSError(f"receipt index out of range: {selector}") from exc
        else:
            receipt_path = selector
        return json.loads(Path(receipt_path).read_text())

    def workspace_tree(self) -> dict:
        self.state = self._read_state()
        return {
            "format": "BOGOS-workspace-tree-4.1",
            "workspace": str(self.root),
            "tree": {
                ".bogos": {
                    "archives": sorted(self.state["archives"]),
                    "bundles": sorted(path.name for path in (self.bogos / "bundles").glob("*")),
                    "mounts": sorted(self.state["mounts"]),
                    "packages": sorted(self.state["packages"]),
                    "apps": sorted(self.state.get("apps", {})),
                    "receipts": [
                        {
                            "index": receipt["index"],
                            "action": receipt["action"],
                            "name": receipt["name"],
                            "execution_status": receipt["execution_status"],
                        }
                        for receipt in self.state["receipts"]
                    ],
                },
                "restored": sorted(path.name for path in (self.root / "restored").glob("*")),
            },
            "execution_status": "completed",
        }

    def demo(self, project: str | Path | None, public: bool = False) -> dict:
        if public or project is None or project == "pack":
            project_path = self._create_public_demo_project()
            demo_format = "BOGOS-public-demo-report-4.5"
        else:
            project_path = self._resolve_path(project)
            demo_format = "BOGOS-demo-receipt-4.0"

        archive_receipt = self.archive_project(project_path, name=project_path.name)
        restore_receipt = self.restore_archive(archive_receipt["archive"])
        install_receipt = self.install_package(project_path, name=project_path.name)
        mount_receipt = self.mount_archive(archive_receipt["archive"], name="demo")
        data, read_receipt = self.read_mount("demo", "README.txt")
        verify_receipt = self.verify_package(install_receipt["package"])
        app_receipt = self.run_app("demo-app") if public or (project_path / "bog_app.json").exists() else None
        corrupt_receipt = self.corrupt_test(install_receipt["package"]) if public else None
        steps = [archive_receipt, restore_receipt, install_receipt, mount_receipt, read_receipt, verify_receipt]
        if app_receipt:
            steps.append(app_receipt)
        if corrupt_receipt:
            steps.append(corrupt_receipt)
        receipt = {
            "format": demo_format,
            "workspace": str(self.root),
            "project": str(project_path),
            "read_size": len(data),
            "steps": [
                {"format": step["format"], "execution_status": step["execution_status"]}
                for step in steps
            ],
            "execution_status": "completed" if all(step["execution_status"] == "completed" for step in steps) else "blocked",
        }
        return self._record_receipt("demo", project_path.name, receipt)

    def _read_state(self) -> dict:
        try:
            state = json.loads(self.state_path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise BogOSError(f"invalid workspace state: {exc}") from exc
        if state.get("format") != WORKSPACE_FORMAT:
            raise BogOSError(f"unsupported workspace format: {state.get('format')}")
        return state

    def _write_state(self) -> None:
        _write_json(self.state_path, self.state)

    def _record_receipt(self, action: str, name: str, receipt: dict) -> dict:
        receipt = {
            **receipt,
            "receipt_format": RECEIPT_FORMAT,
            "action": action,
        }
        index = len(self.state["receipts"]) + 1
        path = self.bogos / "receipts" / f"{index:04d}_{_safe_name(action)}_{_safe_name(name)}.json"
        _write_json(path, receipt)
        self.state["receipts"].append({
            "index": index,
            "action": action,
            "name": name,
            "path": str(path),
            "execution_status": receipt["execution_status"],
        })
        self.state["last_receipt"] = str(path)
        self._write_state()
        return receipt

    def _resolve_archive(self, archive: str) -> tuple[str, Path]:
        if archive in self.state["archives"]:
            return archive, Path(self.state["archives"][archive]["path"])
        path = self._resolve_path(archive)
        if not path.exists():
            raise BogOSError(f"archive not found: {archive}")
        return path.stem.replace(".bogarchive", ""), path

    def _resolve_mount(self, mount: str) -> dict:
        mount_info = self.state["mounts"].get(mount)
        if mount_info is None:
            raise BogOSError(f"mount not found: {mount}")
        return mount_info

    def _resolve_path(self, path: str | Path | None) -> Path:
        if path is None:
            raise BogOSError("missing path")
        path_obj = Path(path)
        if path_obj.is_absolute():
            return path_obj
        return (self.root / path_obj).resolve()

    def _index_package_apps(self, package: str, install_dir: Path) -> None:
        manifest_path = install_dir / "bog_app.json"
        if not manifest_path.exists():
            return
        try:
            manifest = json.loads(manifest_path.read_text())
        except json.JSONDecodeError:
            return
        apps = manifest.get("apps", {})
        if not isinstance(apps, dict):
            return
        self.state.setdefault("apps", {})
        for app_name, app_entry in sorted(apps.items()):
            command = app_entry.get("command")
            if isinstance(command, list) and command:
                self.state["apps"][_safe_name(app_name)] = {
                    "package": package,
                    "install_dir": str(install_dir),
                    "command": command,
                }

    def _create_public_demo_project(self) -> Path:
        project = self.bogos / "demo" / "public-demo-app"
        if project.exists():
            shutil.rmtree(project)
        project.mkdir(parents=True)
        (project / "README.txt").write_text("BogOS Lite public demo package\n")
        (project / "app.py").write_text(
            "from pathlib import Path\n"
            "print('demo-app verified run')\n"
            "print(Path('README.txt').read_text().strip())\n"
        )
        (project / "bog_app.json").write_text(json.dumps({
            "format": "BOGOS-app-manifest-5.0",
            "apps": {
                "demo-app": {
                    "command": [sys.executable, "app.py"],
                },
            },
        }, indent=2, sort_keys=True) + "\n")
        (project / "data.json").write_text(json.dumps({
            "name": "public-demo-app",
            "purpose": "verified software environment demo",
        }, indent=2, sort_keys=True) + "\n")
        return project


def _run_fs(workspace: Workspace, args: argparse.Namespace) -> None:
    if args.fs_cmd == "mount":
        receipt = workspace.mount_archive(args.archive, name=args.name)
        _print_receipt(receipt)
        if receipt["execution_status"] != "completed":
            raise SystemExit(1)
    elif args.fs_cmd == "read":
        data, receipt = workspace.read_mount(args.mount, args.path)
        if receipt["execution_status"] != "completed":
            _print_receipt(receipt)
            raise SystemExit(1)
        sys.stdout.buffer.write(data)
    elif args.fs_cmd == "ls":
        print(json.dumps(workspace.list_mount(args.mount, args.path), indent=2))
    elif args.fs_cmd == "stat":
        print(json.dumps(workspace.stat_mount(args.mount, args.path), indent=2, sort_keys=True))


def _run_store(workspace: Workspace, args: argparse.Namespace) -> None:
    if args.store_cmd == "package":
        receipt = workspace.package_project(args.project, name=args.name, version=args.version)
        _print_receipt(receipt)
    elif args.store_cmd == "install":
        receipt = workspace.install_package(args.package, name=args.name, version=args.version)
        _print_receipt(receipt)
        if receipt["execution_status"] != "completed":
            raise SystemExit(1)
    elif args.store_cmd == "verify":
        receipt = workspace.verify_package(args.package)
        _print_receipt(receipt)
        if receipt["execution_status"] != "completed":
            raise SystemExit(1)


def _run_app(workspace: Workspace, args: argparse.Namespace) -> None:
    if args.app_cmd == "run":
        receipt = workspace.run_app(args.app, extra_args=args.args)
        _print_receipt(receipt)
        if receipt["execution_status"] != "completed":
            raise SystemExit(1)


def _print_receipt(receipt: dict) -> None:
    print(json.dumps(receipt, indent=2, sort_keys=True))


def _safe_name(value: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in value)
    return safe.strip("._") or "item"


def _package_key(name: str, version: str) -> str:
    return f"{_safe_name(name)}-{_safe_name(version)}"


def _receipt_summary(receipt: dict) -> dict:
    return {
        "format": receipt.get("format"),
        "action": receipt.get("action"),
        "execution_status": receipt.get("execution_status"),
        "failures": receipt.get("failures", []),
    }


def _write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")
