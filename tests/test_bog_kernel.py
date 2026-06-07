import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.evaluate_bog_kernel_lite import evaluate as evaluate_bog_kernel_lite


class BogKernelTests(unittest.TestCase):
    def test_kernel_boot_creates_state_and_receipt(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = _init_workspace(Path(td))
            receipt = _run_bog(workspace, "kernel", "boot")

            self.assertEqual(receipt.returncode, 0, receipt.stderr + receipt.stdout)
            receipt_obj = json.loads(receipt.stdout)
            self.assertEqual(receipt_obj["format"], "BOGK-boot-receipt-7.0")
            self.assertEqual(receipt_obj["execution_status"], "completed")
            state = json.loads((workspace / ".bogos" / "kernel" / "state.json").read_text())
            self.assertEqual(state["format"], "BOGK-state-7.0")
            self.assertTrue(state["booted"])

    def test_kernel_status_reports_booted_state(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = _init_workspace(Path(td))
            self.assertEqual(_run_bog(workspace, "kernel", "boot").returncode, 0)

            status = _run_bog(workspace, "kernel", "status")
            self.assertEqual(status.returncode, 0, status.stderr + status.stdout)
            status_obj = json.loads(status.stdout)
            self.assertEqual(status_obj["format"], "BOGK-status-receipt-7.0")
            self.assertTrue(status_obj["booted"])
            self.assertGreaterEqual(status_obj["receipt_count"], 2)

    def test_kernel_run_delegates_to_verified_app_and_records_process(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = _kernel_app_workspace(Path(td))

            run = _run_bog(workspace, "kernel", "run", "demo-app")
            self.assertEqual(run.returncode, 0, run.stderr + run.stdout)
            receipt = json.loads(run.stdout)
            self.assertEqual(receipt["format"], "BOGK-process-receipt-7.0")
            self.assertEqual(receipt["delegated_app_receipt"]["format"], "BOGOS-app-run-receipt-6.0")
            self.assertEqual(receipt["execution_status"], "completed")
            self.assertTrue((workspace / ".bogos" / "kernel" / "processes" / "p0001.json").is_file())

    def test_kernel_run_blocks_tampered_installed_package(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = _kernel_app_workspace(Path(td))
            installed = workspace / ".bogos" / "store" / "installed" / "demo-app-1.0.0" / "app.py"
            installed.write_text("print('tampered')\n")

            run = _run_bog(workspace, "kernel", "run", "demo-app")
            self.assertNotEqual(run.returncode, 0)
            receipt = json.loads(run.stdout)
            self.assertEqual(receipt["execution_status"], "blocked")
            self.assertIn("installed tree hash mismatch", receipt["failures"][0]["reason"])

    def test_kernel_syscall_read_succeeds_for_mounted_archive(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = _kernel_mount_workspace(Path(td))

            read = _run_bog(workspace, "kernel", "syscall", "read", "docs", "README.txt")
            self.assertEqual(read.returncode, 0, read.stderr + read.stdout)
            receipt = json.loads(read.stdout)
            self.assertEqual(receipt["format"], "BOGK-syscall-receipt-7.0")
            self.assertEqual(receipt["data_utf8"], "kernel read fixture\n")
            self.assertEqual(receipt["execution_status"], "completed")
            self.assertTrue((workspace / ".bogos" / "kernel" / "mounts" / "docs.json").is_file())

    def test_kernel_syscall_read_blocks_unknown_mount_and_unsafe_path(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = _kernel_mount_workspace(Path(td))

            unknown = _run_bog(workspace, "kernel", "syscall", "read", "missing", "README.txt")
            self.assertNotEqual(unknown.returncode, 0)
            self.assertIn("unknown mount", json.loads(unknown.stdout)["failures"][0]["reason"])

            unsafe = _run_bog(workspace, "kernel", "syscall", "read", "docs", "../README.txt")
            self.assertNotEqual(unsafe.returncode, 0)
            self.assertIn("unsafe syscall path", json.loads(unsafe.stdout)["failures"][0]["reason"])

            unknown_syscall = _run_bog(workspace, "kernel", "syscall", "unknown")
            self.assertNotEqual(unknown_syscall.returncode, 0)
            self.assertIn("unknown syscall", json.loads(unknown_syscall.stdout)["failures"][0]["reason"])

    def test_kernel_syscall_write_succeeds_for_allowed_app_path(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = _kernel_app_workspace(Path(td))

            write = _run_bog(workspace, "kernel", "syscall", "write", "demo-app", "run.log", "kernel write")
            self.assertEqual(write.returncode, 0, write.stderr + write.stdout)
            receipt = json.loads(write.stdout)
            self.assertEqual(receipt["execution_status"], "completed")
            target = workspace / ".bogos" / "appdata" / "demo-app" / "run.log"
            self.assertEqual(target.read_text(), "kernel write")

    def test_kernel_syscall_write_blocks_undeclared_path(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = _kernel_app_workspace(Path(td))

            write = _run_bog(workspace, "kernel", "syscall", "write", "demo-app", "secret.txt", "blocked")
            self.assertNotEqual(write.returncode, 0)
            receipt = json.loads(write.stdout)
            self.assertEqual(receipt["execution_status"], "blocked")
            self.assertIn("write blocked by app write_policy", receipt["failures"][0]["reason"])

    def test_kernel_evaluator_emits_report_and_receipt(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            report, receipt = evaluate_bog_kernel_lite(
                artifact_dir=root / "kernel",
                report_path=root / "bog_kernel_lite_report.json",
                receipt_path=root / "bog_kernel_lite_receipt.json",
            )
            self.assertEqual(report["format"], "BOGK-lite-report-7.0")
            self.assertEqual(receipt["format"], "BOGK-lite-receipt-7.0")
            self.assertEqual(report["execution_status"], "completed")
            self.assertEqual(receipt["execution_status"], "completed")


def _init_workspace(root: Path) -> Path:
    workspace = root / "workspace"
    result = _run_bog(root, "init", str(workspace))
    if result.returncode != 0:
        raise AssertionError(result.stderr + result.stdout)
    return workspace


def _kernel_app_workspace(root: Path) -> Path:
    workspace = _init_workspace(root)
    project = workspace / "demo-app-src"
    _write_demo_app(project)
    install = _run_bog(workspace, "store", "install", "demo-app-src", "--name", "demo-app", "--version", "1.0.0")
    if install.returncode != 0:
        raise AssertionError(install.stderr + install.stdout)
    boot = _run_bog(workspace, "kernel", "boot")
    if boot.returncode != 0:
        raise AssertionError(boot.stderr + boot.stdout)
    return workspace


def _kernel_mount_workspace(root: Path) -> Path:
    workspace = _init_workspace(root)
    project = workspace / "docs-src"
    project.mkdir()
    (project / "README.txt").write_text("kernel read fixture\n")
    archive = _run_bog(workspace, "archive", "docs-src", "--name", "docs")
    if archive.returncode != 0:
        raise AssertionError(archive.stderr + archive.stdout)
    mount = _run_bog(workspace, "fs", "mount", "docs", "docs")
    if mount.returncode != 0:
        raise AssertionError(mount.stderr + mount.stdout)
    boot = _run_bog(workspace, "kernel", "boot")
    if boot.returncode != 0:
        raise AssertionError(boot.stderr + boot.stdout)
    return workspace


def _write_demo_app(root: Path) -> None:
    root.mkdir()
    (root / "README.txt").write_text("BogK demo app\n")
    (root / "app.py").write_text(
        "import os\n"
        "from pathlib import Path\n"
        "print('BogK verified app run')\n"
        "(Path(os.environ['BOG_APP_RUNTIME_DIR']) / 'run.log').write_text('app run\\n')\n"
    )
    manifest = {
        "format": "BOGOS-app-manifest-6.0",
        "apps": {
            "demo-app": {
                "name": "demo-app",
                "entrypoint": [sys.executable, "app.py"],
                "allowed_files": ["README.txt", "app.py"],
                "expected_hashes": {
                    "README.txt": _sha256(root / "README.txt"),
                    "app.py": _sha256(root / "app.py"),
                },
                "permissions": {"network": False, "subprocess": False},
                "environment": {"BOGK_DEMO": "1"},
                "read_policy": {"allow": ["README.txt", "app.py"]},
                "write_policy": {"mode": "allowed", "allow": ["run.log"]},
                "receipt_path": ".bogos/receipts",
            },
        },
    }
    (root / "bog_app.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def _run_bog(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    repo = Path(__file__).resolve().parents[1]
    env["PYTHONPATH"] = str(repo) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return subprocess.run(
        [sys.executable, "-m", "bog", *args],
        cwd=cwd,
        env=env,
        check=False,
        text=True,
        capture_output=True,
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    unittest.main()
