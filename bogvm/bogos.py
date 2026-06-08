from __future__ import annotations

import argparse
import hashlib
import json
import os
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
from .kernel import BogKernel, BogKernelError
from .schema import SchemaError, validate_schema
from .signing import generate_keypair, public_key_info
from .store import StoreError, init_store, install_bundle, package_directory, read_store_index, verify_installed_package


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
    p_store_install.add_argument("--dependency", action="append", default=[])
    p_store_verify = store_sub.add_parser("verify")
    p_store_verify.add_argument("package")
    p_store_package = store_sub.add_parser("package")
    p_store_package.add_argument("project")
    p_store_package.add_argument("--name", required=True)
    p_store_package.add_argument("--version", default="1.0.0")
    p_store_package.add_argument("--dependency", action="append", default=[])

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

    p_kernel = sub.add_parser("kernel")
    kernel_sub = p_kernel.add_subparsers(dest="kernel_cmd", required=True)
    kernel_sub.add_parser("boot")
    kernel_sub.add_parser("status")
    p_kernel_run = kernel_sub.add_parser("run")
    p_kernel_run.add_argument("--brokered", action="store_true")
    p_kernel_run.add_argument("app")
    p_kernel_run.add_argument("args", nargs=argparse.REMAINDER)
    p_kernel_replay = kernel_sub.add_parser("replay")
    p_kernel_replay.add_argument("receipt")
    p_kernel_syscall = kernel_sub.add_parser("syscall")
    p_kernel_syscall.add_argument("syscall")
    p_kernel_syscall.add_argument("args", nargs=argparse.REMAINDER)

    sub.add_parser("boot")

    p_registry = sub.add_parser("registry")
    registry_sub = p_registry.add_subparsers(dest="registry_cmd", required=True)
    p_registry_sync = registry_sub.add_parser("sync")
    p_registry_sync.add_argument("--source", default=None)
    registry_sub.add_parser("verify")

    p_install = sub.add_parser("install")
    p_install.add_argument("package")

    p_shell = sub.add_parser("shell")
    p_shell.add_argument("--command", default=None)

    p_rollback = sub.add_parser("rollback")
    p_rollback.add_argument("receipt")

    p_replay_session = sub.add_parser("replay-session")
    p_replay_session.add_argument("receipt", nargs="?", default=None)

    p_genesis = sub.add_parser("genesis")
    genesis_sub = p_genesis.add_subparsers(dest="genesis_cmd", required=True)
    genesis_sub.add_parser("demo")

    p_build = sub.add_parser("build")
    p_build.add_argument("source")
    p_build.add_argument("--output", required=True)

    p_package = sub.add_parser("package")
    p_package.add_argument("project")
    p_package.add_argument("--name", required=True)
    p_package.add_argument("--version", default="1.0.0")
    p_package.add_argument("--dependency", action="append", default=[])

    p_run_cell = sub.add_parser("run-cell")
    p_run_cell.add_argument("app")

    p_proof = sub.add_parser("proof")
    proof_sub = p_proof.add_subparsers(dest="proof_cmd", required=True)
    p_proof_export = proof_sub.add_parser("export")
    p_proof_export.add_argument("receipt")
    p_proof_export.add_argument("output")
    p_proof_verify = proof_sub.add_parser("verify")
    p_proof_verify.add_argument("proof")
    p_proof_replay = proof_sub.add_parser("replay")
    p_proof_replay.add_argument("proof")

    p_ledger = sub.add_parser("ledger")
    ledger_sub = p_ledger.add_subparsers(dest="ledger_cmd", required=True)
    ledger_sub.add_parser("verify")

    p_state = sub.add_parser("state")
    state_sub = p_state.add_subparsers(dest="state_cmd", required=True)
    p_state_diff = state_sub.add_parser("diff")
    p_state_diff.add_argument("root_a")
    p_state_diff.add_argument("root_b")
    p_state_checkout = state_sub.add_parser("checkout")
    p_state_checkout.add_argument("root")
    p_state_prove = state_sub.add_parser("prove-file")
    p_state_prove.add_argument("path")
    p_state_prove.add_argument("--root", default=None)

    p_pilot = sub.add_parser("pilot")
    p_pilot.add_argument("prompt")

    p_hyper = sub.add_parser("hypergenesis")
    hyper_sub = p_hyper.add_subparsers(dest="hypergenesis_cmd", required=True)
    hyper_sub.add_parser("demo")

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
        elif args.cmd == "kernel":
            _run_kernel(workspace, args)
        elif args.cmd == "boot":
            from .genesis import Genesis
            _print_receipt(Genesis(workspace).boot())
        elif args.cmd == "registry":
            from .genesis import Genesis
            genesis = Genesis(workspace)
            result = (
                genesis.sync_registry_from(args.source) if args.registry_cmd == "sync" and args.source
                else genesis.sync_registry() if args.registry_cmd == "sync"
                else genesis.verify_registry(required=True)
            )
            _print_receipt(result)
            if result["execution_status"] != "completed":
                raise SystemExit(1)
        elif args.cmd == "install":
            from .genesis import Genesis
            receipt = Genesis(workspace).install(args.package)
            _print_receipt(receipt)
            if receipt["execution_status"] != "completed":
                raise SystemExit(1)
        elif args.cmd == "shell":
            from .genesis import Genesis
            _run_genesis_shell(Genesis(workspace), args.command)
        elif args.cmd == "rollback":
            from .genesis import Genesis
            receipt = Genesis(workspace).rollback(args.receipt)
            _print_receipt(receipt)
            if receipt["execution_status"] != "completed":
                raise SystemExit(1)
        elif args.cmd == "replay-session":
            from .genesis import Genesis
            receipt = Genesis(workspace).replay_session(args.receipt)
            _print_receipt(receipt)
            if receipt["execution_status"] != "completed":
                raise SystemExit(1)
        elif args.cmd == "genesis":
            from .genesis import Genesis
            receipt = Genesis(workspace).demo()
            _print_receipt(receipt)
            if receipt["execution_status"] != "completed":
                raise SystemExit(1)
        elif args.cmd == "build":
            from .hypergenesis import HyperGenesis
            _print_receipt(HyperGenesis(workspace).build(args.source, args.output))
        elif args.cmd == "package":
            from .hypergenesis import HyperGenesis
            _print_receipt(HyperGenesis(workspace).package_build(args.project, args.name, args.version, args.dependency))
        elif args.cmd == "run-cell":
            from .hypergenesis import HyperGenesis
            receipt = HyperGenesis(workspace).run_cell(args.app)
            _print_receipt(receipt)
            if receipt["execution_status"] != "completed":
                raise SystemExit(1)
        elif args.cmd == "proof":
            from .hypergenesis import HyperGenesis
            hyper = HyperGenesis(workspace)
            receipt = (
                hyper.export_proof(args.receipt, args.output)
                if args.proof_cmd == "export"
                else hyper.verify_proof(workspace._resolve_path(args.proof))
            )
            _print_receipt(receipt)
            if receipt["execution_status"] != "completed":
                raise SystemExit(1)
        elif args.cmd == "ledger":
            from .hypergenesis import HyperGenesis
            receipt = HyperGenesis(workspace).ledger_verify()
            _print_receipt(receipt)
            if receipt["execution_status"] != "completed":
                raise SystemExit(1)
        elif args.cmd == "state":
            from .hypergenesis import HyperGenesis
            hyper = HyperGenesis(workspace)
            receipt = (
                hyper.state_diff(args.root_a, args.root_b) if args.state_cmd == "diff"
                else hyper.state_checkout(args.root) if args.state_cmd == "checkout"
                else hyper.prove_file(args.path, args.root)
            )
            _print_receipt(receipt)
            if receipt["execution_status"] != "completed":
                raise SystemExit(1)
        elif args.cmd == "pilot":
            from .hypergenesis import HyperGenesis
            receipt = HyperGenesis(workspace).pilot(args.prompt)
            _print_receipt(receipt)
            if receipt["execution_status"] != "completed":
                raise SystemExit(1)
        elif args.cmd == "hypergenesis":
            from .hypergenesis import HyperGenesis
            receipt = HyperGenesis(workspace).demo()
            _print_receipt(receipt)
            if receipt["execution_status"] != "completed":
                raise SystemExit(1)
    except (BogOSError, BogKernelError) as exc:
        print(f"bog: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


def init_workspace(path: str | Path) -> dict:
    root = Path(path)
    root.mkdir(parents=True, exist_ok=True)
    bogos = root / ".bogos"
    for child in ("archives", "bundles", "receipts", "store", "demo", "appdata", "keys", "trust"):
        (bogos / child).mkdir(parents=True, exist_ok=True)
    private_key = bogos / "keys" / "workspace.key"
    public_key = bogos / "trust" / "workspace.pub"
    key = (
        public_key_info(public_key)
        if private_key.exists() and public_key.exists()
        else generate_keypair(private_key, public_key)
    )
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
        "signing_key_id": key["key_id"],
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

    def package_project(self, project: str | Path, name: str, version: str, dependencies: list[str] | None = None) -> dict:
        source = self._resolve_path(project)
        key = _package_key(name, version)
        bundle_dir = self.bogos / "bundles" / key
        package_receipt = package_directory(
            source,
            bundle_dir,
            name=name,
            version=version,
            dependencies=dependencies,
            signing_key=self.bogos / "keys" / "workspace.key",
        )
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

    def install_package(
        self,
        package: str | Path,
        name: str | None = None,
        version: str = "1.0.0",
        dependencies: list[str] | None = None,
    ) -> dict:
        package_path = self._resolve_path(package)
        if (package_path / "receipt.json").exists():
            bundle_dir = package_path
        else:
            package_name = name or package_path.name
            key = _package_key(package_name, version)
            bundle_dir = self.bogos / "bundles" / key
            package_directory(
                package_path,
                bundle_dir,
                name=package_name,
                version=version,
                dependencies=dependencies,
                signing_key=self.bogos / "keys" / "workspace.key",
            )

        try:
            install_receipt = install_bundle(
                self.bogos / "store",
                bundle_dir,
                trusted_public_keys=self._trusted_public_keys(),
                require_signature=True,
            )
        except StoreError as exc:
            receipt = {
                "format": "BOGOS-store-install-receipt-7.0",
                "workspace": str(self.root),
                "bundle": str(bundle_dir),
                "failures": [{"path": str(bundle_dir), "reason": str(exc)}],
                "execution_status": "blocked",
            }
            return self._record_receipt("store-install", bundle_dir.name, receipt)
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
        receipt = self._verify_installed_package(package)
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
                "format": "BOGOS-app-run-receipt-6.0",
                "workspace": str(self.root),
                "app": app,
                "failures": [{"path": app, "reason": f"app not installed: {app}"}],
                "execution_status": "blocked",
            }
            return self._record_receipt("app-run", app, receipt)

        verify_receipt = self._verify_installed_package(app_info["package"])
        if verify_receipt["execution_status"] != "completed":
            receipt = {
                "format": "BOGOS-app-run-receipt-6.0",
                "workspace": str(self.root),
                "app": app,
                "package": app_info["package"],
                "verification": verify_receipt,
                "failures": verify_receipt.get("failures", []),
                "execution_status": "blocked",
            }
            return self._record_receipt("app-run", app, receipt)

        install_dir = Path(app_info["install_dir"])
        policy_receipt = self._verify_app_runtime_policy(app, app_info, verify_receipt)
        if policy_receipt["execution_status"] != "completed":
            receipt = {
                "format": "BOGOS-app-run-receipt-6.0",
                "workspace": str(self.root),
                "app": app,
                "package": app_info["package"],
                "verification": verify_receipt,
                "runtime_policy": policy_receipt,
                "failures": policy_receipt["failures"],
                "execution_status": "blocked",
            }
            return self._record_receipt("app-run", app, receipt)

        runtime_dir = self.bogos / "appdata" / app
        runtime_dir.mkdir(parents=True, exist_ok=True)
        receipt_path = self._resolve_policy_receipt_path(app_info["receipt_path"])
        command = _resolve_entrypoint(install_dir, app_info["entrypoint"]) + extra_args
        environment = _runtime_environment(app_info, app, runtime_dir, receipt_path)
        runtime_before = _file_snapshot(runtime_dir)
        package_before = _file_snapshot(install_dir)
        try:
            result = subprocess.run(
                command,
                cwd=runtime_dir,
                env=environment,
                check=False,
                text=True,
                capture_output=True,
            )
            runtime_after = _file_snapshot(runtime_dir)
            package_after = _file_snapshot(install_dir)
            post_verify_receipt = self._verify_installed_package(app_info["package"])
            failures = []
            if result.returncode != 0:
                failures.append({
                    "path": app,
                    "reason": f"app exited with code {result.returncode}",
                })
            failures.extend(_write_policy_failures(app_info["write_policy"], runtime_before, runtime_after))
            if package_after != package_before:
                failures.append({
                    "path": str(install_dir),
                    "reason": "installed package changed during app run",
                })
            failures.extend(post_verify_receipt.get("failures", []))
            receipt = {
                "format": "BOGOS-app-run-receipt-6.0",
                "workspace": str(self.root),
                "app": app,
                "package": app_info["package"],
                "command": command,
                "runtime_dir": str(runtime_dir),
                "receipt_path": str(receipt_path),
                "environment": sorted(environment),
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "verification": verify_receipt,
                "post_run_verification": post_verify_receipt,
                "runtime_policy": policy_receipt,
                "runtime_changes": _snapshot_changes(runtime_before, runtime_after),
                "failures": failures,
                "execution_status": "completed" if not failures else "blocked",
            }
        except OSError as exc:
            receipt = {
                "format": "BOGOS-app-run-receipt-6.0",
                "workspace": str(self.root),
                "app": app,
                "package": app_info["package"],
                "command": command,
                "runtime_dir": str(runtime_dir),
                "receipt_path": str(receipt_path),
                "runtime_policy": policy_receipt,
                "failures": [{"path": app, "reason": str(exc)}],
                "execution_status": "blocked",
            }
        return self._record_receipt("app-run", app, receipt, receipt_dir=receipt_path)

    def _verify_app_runtime_policy(self, app: str, app_info: dict, verify_receipt: dict) -> dict:
        install_dir = Path(app_info.get("install_dir", ""))
        failures = []
        required_fields = (
            "name",
            "entrypoint",
            "allowed_files",
            "expected_hashes",
            "permissions",
            "environment",
            "read_policy",
            "write_policy",
            "receipt_path",
        )
        for field in required_fields:
            if field not in app_info:
                failures.append({"path": "bog_app.json", "reason": f"missing app manifest field: {field}"})

        if app_info.get("name") != app:
            failures.append({"path": "bog_app.json", "reason": f"app name mismatch: expected {app}"})
        if not isinstance(app_info.get("entrypoint"), list) or not all(isinstance(part, str) for part in app_info.get("entrypoint", [])):
            failures.append({"path": "bog_app.json", "reason": "entrypoint must be a list of strings"})
        if not app_info.get("entrypoint"):
            failures.append({"path": "bog_app.json", "reason": "entrypoint must not be empty"})

        allowed_files = app_info.get("allowed_files", [])
        expected_hashes = app_info.get("expected_hashes", {})
        permissions = app_info.get("permissions", {})
        environment = app_info.get("environment", {})
        read_policy = app_info.get("read_policy", {})
        write_policy = app_info.get("write_policy", {})
        capabilities = app_info.get("capabilities")

        if not isinstance(allowed_files, list) or not all(_is_safe_relpath(path) for path in allowed_files):
            failures.append({"path": "bog_app.json", "reason": "allowed_files must be safe relative paths"})
            allowed_files = []
        if not isinstance(expected_hashes, dict) or not all(_is_safe_relpath(path) and isinstance(value, str) for path, value in expected_hashes.items()):
            failures.append({"path": "bog_app.json", "reason": "expected_hashes must map safe relative paths to hashes"})
            expected_hashes = {}
        if not isinstance(permissions, dict):
            failures.append({"path": "bog_app.json", "reason": "permissions must be an object"})
        elif not all(isinstance(key, str) and isinstance(value, bool) for key, value in permissions.items()):
            failures.append({"path": "bog_app.json", "reason": "permissions must map strings to booleans"})
        else:
            for permission, enabled in sorted(permissions.items()):
                if permission not in {"network", "subprocess"}:
                    failures.append({"path": "bog_app.json", "reason": f"unsupported permission: {permission}"})
                elif enabled:
                    failures.append({"path": "bog_app.json", "reason": f"permission is not supported in v6: {permission}"})
        if not isinstance(environment, dict) or not all(isinstance(key, str) and isinstance(value, str) for key, value in environment.items()):
            failures.append({"path": "bog_app.json", "reason": "environment must map strings to strings"})
        if not _valid_access_policy(read_policy):
            failures.append({"path": "bog_app.json", "reason": "read_policy must be an object with a safe allow list"})
        if not _valid_write_policy(write_policy):
            failures.append({"path": "bog_app.json", "reason": "write_policy must be mode none or allowed with a safe allow list"})
        if capabilities is not None and not _valid_capabilities(capabilities):
            failures.append({"path": "bog_app.json", "reason": "capabilities must declare safe read/write/env/dependencies lists"})
        if capabilities is not None:
            if not set(capabilities.get("read", [])).issubset(set(read_policy.get("allow", []))):
                failures.append({"path": "bog_app.json", "reason": "read capabilities must be allowed by read_policy"})
            if not set(capabilities.get("write", [])).issubset(set(write_policy.get("allow", []))):
                failures.append({"path": "bog_app.json", "reason": "write capabilities must be allowed by write_policy"})
            if not set(capabilities.get("env", [])).issubset(set(environment)):
                failures.append({"path": "bog_app.json", "reason": "env capabilities must be declared in environment"})
            if set(capabilities.get("dependencies", [])) != set(verify_receipt.get("dependencies", [])):
                failures.append({"path": "bog_app.json", "reason": "dependency capabilities must match signed package dependencies"})

        try:
            self._resolve_policy_receipt_path(app_info.get("receipt_path"))
        except BogOSError as exc:
            failures.append({"path": "bog_app.json", "reason": str(exc)})

        allowed_set = set(allowed_files)
        for relpath in expected_hashes:
            if relpath not in allowed_set:
                failures.append({"path": relpath, "reason": "expected hash path is not in allowed_files"})
        for relpath in read_policy.get("allow", []) if isinstance(read_policy, dict) else []:
            if relpath not in allowed_set:
                failures.append({"path": relpath, "reason": "read policy path is not in allowed_files"})
        for relpath, expected_hash in sorted(expected_hashes.items()):
            target = install_dir / relpath
            if not target.is_file():
                failures.append({"path": relpath, "reason": "expected hashed file is missing"})
                continue
            actual_hash = hashlib.sha256(target.read_bytes()).hexdigest()
            if actual_hash != expected_hash:
                failures.append({"path": relpath, "reason": "app manifest expected hash mismatch"})
        entrypoint = app_info.get("entrypoint", [])
        if len(entrypoint) >= 2 and _is_safe_relpath(entrypoint[1]) and entrypoint[1] not in allowed_set:
            failures.append({"path": entrypoint[1], "reason": "entrypoint file is not in allowed_files"})

        return {
            "format": "BOGOS-app-runtime-policy-receipt-6.0",
            "workspace": str(self.root),
            "app": app,
            "package": app_info.get("package"),
            "package_verification_status": verify_receipt["execution_status"],
            "policy": {
                "allowed_files": allowed_files,
                "expected_hashes": expected_hashes,
                "permissions": permissions,
                "environment": environment,
                "read_policy": read_policy,
                "write_policy": write_policy,
                "receipt_path": app_info.get("receipt_path"),
                "capabilities": capabilities,
            },
            "failures": failures,
            "execution_status": "completed" if not failures else "blocked",
        }

    def _resolve_policy_receipt_path(self, receipt_path: str | None) -> Path:
        receipt_path = receipt_path or ".bogos/receipts"
        if not _is_safe_relpath(receipt_path):
            raise BogOSError("receipt_path must be a safe relative workspace path")
        resolved = (self.root / receipt_path).resolve()
        if not resolved.is_relative_to(self.root):
            raise BogOSError("receipt_path must stay inside the workspace")
        return resolved

    def doctor(self) -> dict:
        self.state = self._read_state()
        checks = []
        failures = []
        for dirname in ("archives", "bundles", "receipts", "store", "demo", "appdata"):
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
            verify_receipt = self._verify_installed_package(package)
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
            verify_receipt = self._verify_installed_package(package)
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

    def _record_receipt(self, action: str, name: str, receipt: dict, receipt_dir: Path | None = None) -> dict:
        receipt = {
            **receipt,
            "receipt_format": RECEIPT_FORMAT,
            "action": action,
        }
        try:
            validate_schema(receipt, "receipt.schema.json")
        except SchemaError as exc:
            raise BogOSError(str(exc)) from exc
        index = len(self.state["receipts"]) + 1
        path = (receipt_dir or self.bogos / "receipts") / f"{index:04d}_{_safe_name(action)}_{_safe_name(name)}.json"
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
        self.state.setdefault("apps", {})
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text())
                validate_schema(manifest, "bog-app.schema.json")
            except (json.JSONDecodeError, SchemaError):
                manifest = {}
            for app_name, app_entry in sorted(manifest.get("apps", {}).items()):
                indexed_app = _normalize_app_manifest_entry(app_name, app_entry, install_dir)
                if indexed_app is not None:
                    indexed_app["package"] = package
                    indexed_app["install_dir"] = str(install_dir)
                    self.state["apps"][_safe_name(app_name)] = indexed_app
        cell_path = install_dir / "bog_cell.json"
        if cell_path.exists():
            try:
                manifest = json.loads(cell_path.read_text())
                validate_schema(manifest, "bogcell-app.schema.json")
            except (json.JSONDecodeError, SchemaError):
                manifest = {}
            if manifest.get("format") == "BOGCELL-app-manifest-10.0":
                for app_name, entry in sorted(manifest.get("apps", {}).items()):
                    if isinstance(entry, dict) and isinstance(entry.get("program"), str) and isinstance(entry.get("capabilities"), dict):
                        self.state["apps"][_safe_name(app_name)] = {
                            "name": app_name,
                            "package": package,
                            "install_dir": str(install_dir),
                            "cell_program": entry["program"],
                            "cell_capabilities": entry["capabilities"],
                            "cell_environment": entry.get("environment", {}),
                            "build_receipt": entry.get("build_receipt", "build_receipt.json"),
                        }

    def _trusted_public_keys(self) -> list[Path]:
        return sorted((self.bogos / "trust").glob("*.pub"))

    def _verify_installed_package(self, package: str) -> dict:
        return verify_installed_package(
            self.bogos / "store",
            package,
            trusted_public_keys=self._trusted_public_keys(),
            require_signature=True,
        )

    def _create_public_demo_project(self) -> Path:
        project = self.bogos / "demo" / "public-demo-app"
        if project.exists():
            shutil.rmtree(project)
        project.mkdir(parents=True)
        (project / "README.txt").write_text("BogOS Lite public demo package\n")
        (project / "app.py").write_text(
            "import os\n"
            "from pathlib import Path\n"
            "package_dir = Path(os.environ['BOG_PACKAGE_DIR'])\n"
            "output_dir = Path(os.environ['BOG_APP_RUNTIME_DIR'])\n"
            "print('demo-app verified run')\n"
            "print((package_dir / 'README.txt').read_text().strip())\n"
            "(output_dir / 'run.log').write_text('verified runtime write\\n')\n"
        )
        readme_hash = hashlib.sha256((project / "README.txt").read_bytes()).hexdigest()
        app_hash = hashlib.sha256((project / "app.py").read_bytes()).hexdigest()
        (project / "bog_app.json").write_text(json.dumps({
            "format": "BOGOS-app-manifest-6.0",
            "apps": {
                "demo-app": {
                    "name": "demo-app",
                    "entrypoint": [sys.executable, "app.py"],
                    "allowed_files": ["README.txt", "app.py"],
                    "expected_hashes": {
                        "README.txt": readme_hash,
                        "app.py": app_hash,
                    },
                    "permissions": {
                        "network": False,
                        "subprocess": False,
                    },
                    "environment": {
                        "DEMO_MODE": "public",
                    },
                    "read_policy": {
                        "allow": ["README.txt", "app.py"],
                    },
                    "write_policy": {
                        "mode": "allowed",
                        "allow": ["run.log"],
                    },
                    "receipt_path": ".bogos/receipts",
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
        receipt = workspace.package_project(args.project, name=args.name, version=args.version, dependencies=args.dependency)
        _print_receipt(receipt)
    elif args.store_cmd == "install":
        receipt = workspace.install_package(args.package, name=args.name, version=args.version, dependencies=args.dependency)
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


def _run_kernel(workspace: Workspace, args: argparse.Namespace) -> None:
    kernel = BogKernel(workspace)
    if args.kernel_cmd == "boot":
        receipt = kernel.boot()
    elif args.kernel_cmd == "status":
        receipt = kernel.status()
    elif args.kernel_cmd == "run":
        receipt = kernel.run(args.app, args=args.args, brokered=args.brokered)
    elif args.kernel_cmd == "replay":
        receipt = kernel.replay(args.receipt)
    else:
        receipt = kernel.syscall(args.syscall, *args.args)
    _print_receipt(receipt)
    if receipt["execution_status"] != "completed":
        raise SystemExit(1)


def _run_genesis_shell(genesis, command: str | None) -> None:
    if command is not None:
        result = genesis.shell_command(command)
        print(json.dumps(result, indent=2, sort_keys=True) if isinstance(result, dict) else result)
        return
    while True:
        try:
            line = input("bog> ")
        except EOFError:
            return
        if line.strip() in {"exit", "quit"}:
            return
        try:
            result = genesis.shell_command(line)
            print(json.dumps(result, indent=2, sort_keys=True) if isinstance(result, dict) else result)
        except BogOSError as exc:
            print(f"blocked: {exc}", file=sys.stderr)


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


def _normalize_app_manifest_entry(app_name: str, app_entry: dict, install_dir: Path) -> dict | None:
    if not isinstance(app_entry, dict):
        return None
    if app_entry.get("format") and app_entry["format"] != "BOGOS-app-manifest-entry-6.0":
        return None

    entrypoint = app_entry.get("entrypoint", app_entry.get("command"))
    if not isinstance(entrypoint, list) or not entrypoint:
        return None
    normalized = {"entrypoint": entrypoint}
    for field in (
        "name",
        "allowed_files",
        "expected_hashes",
        "permissions",
        "environment",
        "read_policy",
        "write_policy",
        "receipt_path",
        "capabilities",
    ):
        if field in app_entry:
            normalized[field] = app_entry[field]
    return normalized


def _runtime_environment(app_info: dict, app: str, runtime_dir: Path, receipt_path: Path) -> dict[str, str]:
    path = os.environ.get("PATH")
    env = {"PYTHONUNBUFFERED": "1"}
    if path:
        env["PATH"] = path
    env.update(app_info["environment"])
    env["BOG_APP_NAME"] = app
    env["BOG_APP_PACKAGE"] = app_info["package"]
    env["BOG_PACKAGE_DIR"] = app_info["install_dir"]
    env["BOG_APP_RUNTIME_DIR"] = str(runtime_dir)
    env["BOG_APP_RECEIPT_PATH"] = str(receipt_path)
    env["BOG_APP_ALLOWED_FILES"] = json.dumps(app_info["allowed_files"], sort_keys=True)
    env["BOG_APP_READ_POLICY"] = json.dumps(app_info["read_policy"], sort_keys=True)
    env["BOG_APP_WRITE_POLICY"] = json.dumps(app_info["write_policy"], sort_keys=True)
    return env


def _resolve_entrypoint(install_dir: Path, entrypoint: list[str]) -> list[str]:
    command = [str(part) for part in entrypoint]
    if len(command) >= 2 and _is_safe_relpath(command[1]) and (install_dir / command[1]).is_file():
        command[1] = str((install_dir / command[1]).resolve())
    elif command and _is_safe_relpath(command[0]) and (install_dir / command[0]).is_file():
        command[0] = str((install_dir / command[0]).resolve())
    return command


def _file_snapshot(root: Path) -> dict[str, str]:
    snapshot = {}
    if not root.exists():
        return snapshot
    for item in sorted(path for path in root.rglob("*") if path.is_file()):
        relpath = item.relative_to(root).as_posix()
        snapshot[relpath] = hashlib.sha256(item.read_bytes()).hexdigest()
    return snapshot


def _snapshot_changes(before: dict[str, str], after: dict[str, str]) -> dict[str, list[str]]:
    before_paths = set(before)
    after_paths = set(after)
    return {
        "added": sorted(after_paths - before_paths),
        "removed": sorted(before_paths - after_paths),
        "changed": sorted(path for path in before_paths & after_paths if before[path] != after[path]),
    }


def _write_policy_failures(write_policy: dict, before: dict[str, str], after: dict[str, str]) -> list[dict[str, str]]:
    changes = _snapshot_changes(before, after)
    changed_paths = set(changes["added"] + changes["removed"] + changes["changed"])
    if not changed_paths:
        return []
    mode = write_policy.get("mode")
    allowed = set(write_policy.get("allow", []))
    if mode == "none":
        return [
            {"path": path, "reason": "runtime write rejected by write_policy:none"}
            for path in sorted(changed_paths)
        ]
    unexpected = sorted(changed_paths - allowed)
    return [
        {"path": path, "reason": "runtime write outside write_policy allow list"}
        for path in unexpected
    ]


def _valid_access_policy(policy: object) -> bool:
    return (
        isinstance(policy, dict)
        and isinstance(policy.get("allow"), list)
        and all(_is_safe_relpath(path) for path in policy["allow"])
    )


def _valid_write_policy(policy: object) -> bool:
    return (
        isinstance(policy, dict)
        and policy.get("mode") in {"none", "allowed"}
        and isinstance(policy.get("allow", []), list)
        and all(_is_safe_relpath(path) for path in policy.get("allow", []))
    )


def _valid_capabilities(capabilities: object) -> bool:
    return (
        isinstance(capabilities, dict)
        and set(capabilities) == {"read", "write", "env", "dependencies"}
        and all(isinstance(capabilities.get(name), list) for name in capabilities)
        and all(_is_safe_relpath(path) for name in ("read", "write") for path in capabilities[name])
        and all(isinstance(value, str) and value for name in ("env", "dependencies") for value in capabilities[name])
    )


def _is_safe_relpath(path: object) -> bool:
    if not isinstance(path, str) or not path:
        return False
    candidate = Path(path)
    return not candidate.is_absolute() and ".." not in candidate.parts


def _write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")
