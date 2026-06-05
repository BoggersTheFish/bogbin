import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest

from tests.test_directory_store import _write_mixed_fixture
from scripts.evaluate_bogos_lite_demo import evaluate as evaluate_bogos_lite_demo


class BogOSLiteTests(unittest.TestCase):
    def test_workspace_killer_demo_rejects_corruption_with_receipt_reason(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            workspace = root / "workspace"

            init_result = _run_bog(root, "init", str(workspace))
            self.assertEqual(init_result.returncode, 0, init_result.stderr + init_result.stdout)

            project = workspace / "project"
            _write_mixed_fixture(project)

            archive = _run_bog(workspace, "archive", "project")
            self.assertEqual(archive.returncode, 0, archive.stderr + archive.stdout)
            archive_receipt = json.loads(archive.stdout)
            self.assertEqual(archive_receipt["execution_status"], "completed")
            self.assertEqual(archive_receipt["archive"], "project")

            restore = _run_bog(workspace, "restore", "project")
            self.assertEqual(restore.returncode, 0, restore.stderr + restore.stdout)
            restore_receipt = json.loads(restore.stdout)
            self.assertEqual(restore_receipt["execution_status"], "completed")
            self.assertEqual(
                (workspace / "restored" / "project" / "README.txt").read_text(),
                (project / "README.txt").read_text(),
            )

            mount = _run_bog(workspace, "fs", "mount", "project", "proj")
            self.assertEqual(mount.returncode, 0, mount.stderr + mount.stdout)
            self.assertEqual(json.loads(mount.stdout)["execution_status"], "completed")

            read = _run_bog(workspace, "fs", "read", "proj", "README.txt")
            self.assertEqual(read.returncode, 0, read.stderr + read.stdout)
            self.assertEqual(read.stdout, "mixed text fixture\n")

            install = _run_bog(
                workspace,
                "store",
                "install",
                "project",
                "--name",
                "mixed-project",
                "--version",
                "1.0.0",
            )
            self.assertEqual(install.returncode, 0, install.stderr + install.stdout)
            install_receipt = json.loads(install.stdout)
            self.assertEqual(install_receipt["execution_status"], "completed")
            self.assertEqual(install_receipt["package"], "mixed-project-1.0.0")

            verify = _run_bog(workspace, "store", "verify", "mixed-project-1.0.0")
            self.assertEqual(verify.returncode, 0, verify.stderr + verify.stdout)
            self.assertEqual(json.loads(verify.stdout)["execution_status"], "completed")

            installed_readme = workspace / ".bogos" / "store" / "installed" / "mixed-project-1.0.0" / "README.txt"
            installed_readme.write_text("corrupted\n")

            rejected = _run_bog(workspace, "store", "verify", "mixed-project-1.0.0")
            self.assertNotEqual(rejected.returncode, 0)
            rejected_receipt = json.loads(rejected.stdout)
            self.assertEqual(rejected_receipt["execution_status"], "blocked")
            self.assertIn("installed tree hash mismatch", rejected_receipt["failures"][0]["reason"])

            last = _run_bog(workspace, "receipt")
            self.assertEqual(last.returncode, 0, last.stderr + last.stdout)
            last_receipt = json.loads(last.stdout)
            self.assertEqual(last_receipt["execution_status"], "blocked")
            self.assertIn("installed tree hash mismatch", last_receipt["failures"][0]["reason"])

            status = _run_bog(workspace, "status")
            self.assertEqual(status.returncode, 0, status.stderr + status.stdout)
            status_obj = json.loads(status.stdout)
            self.assertEqual(status_obj["archive_count"], 1)
            self.assertEqual(status_obj["mount_count"], 1)
            self.assertEqual(status_obj["package_count"], 1)
            self.assertGreaterEqual(status_obj["receipt_count"], 7)

    def test_ux_hardening_commands_explain_workspace_state(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            workspace = root / "workspace"
            self.assertEqual(_run_bog(root, "init", str(workspace)).returncode, 0)
            project = workspace / "project"
            _write_mixed_fixture(project)

            self.assertEqual(_run_bog(workspace, "archive", "project").returncode, 0)
            self.assertEqual(_run_bog(workspace, "restore", "project").returncode, 0)
            self.assertEqual(_run_bog(workspace, "fs", "mount", "project", "proj").returncode, 0)
            self.assertEqual(_run_bog(workspace, "store", "install", "project", "--name", "mixed-project").returncode, 0)

            doctor = _run_bog(workspace, "doctor")
            self.assertEqual(doctor.returncode, 0, doctor.stderr + doctor.stdout)
            self.assertEqual(json.loads(doctor.stdout)["execution_status"], "completed")

            verbose = _run_bog(workspace, "status", "--verbose")
            self.assertEqual(verbose.returncode, 0, verbose.stderr + verbose.stdout)
            verbose_status = json.loads(verbose.stdout)
            self.assertEqual(verbose_status["format"], "BOGOS-status-verbose-4.1")
            self.assertIn("archive_details", verbose_status)
            self.assertIn("receipt_details", verbose_status)

            latest = _run_bog(workspace, "receipt", "latest")
            self.assertEqual(latest.returncode, 0, latest.stderr + latest.stdout)
            self.assertEqual(json.loads(latest.stdout)["action"], "doctor")

            tree = _run_bog(workspace, "workspace", "tree")
            self.assertEqual(tree.returncode, 0, tree.stderr + tree.stdout)
            tree_obj = json.loads(tree.stdout)
            self.assertIn("project", tree_obj["tree"][".bogos"]["archives"])
            self.assertIn("proj", tree_obj["tree"][".bogos"]["mounts"])

            corrupt = _run_bog(workspace, "corrupt-test", "mixed-project-1.0.0")
            self.assertEqual(corrupt.returncode, 0, corrupt.stderr + corrupt.stdout)
            corrupt_receipt = json.loads(corrupt.stdout)
            self.assertEqual(corrupt_receipt["format"], "BOGOS-corrupt-test-receipt-4.1")
            self.assertTrue(corrupt_receipt["rejected"])
            self.assertIn("installed tree hash mismatch", corrupt_receipt["failures"][0]["reason"])

    def test_public_demo_pack_and_verified_app_run(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            workspace = root / "workspace"
            self.assertEqual(_run_bog(root, "init", str(workspace)).returncode, 0)

            demo = _run_bog(workspace, "demo", "pack")
            self.assertEqual(demo.returncode, 0, demo.stderr + demo.stdout)
            demo_receipt = json.loads(demo.stdout)
            self.assertEqual(demo_receipt["format"], "BOGOS-public-demo-report-4.5")
            self.assertEqual(demo_receipt["execution_status"], "completed")
            self.assertTrue(any(step["format"] == "BOGOS-app-run-receipt-5.0" for step in demo_receipt["steps"]))
            self.assertTrue(any(step["format"] == "BOGOS-corrupt-test-receipt-4.1" for step in demo_receipt["steps"]))

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            workspace = root / "workspace"
            self.assertEqual(_run_bog(root, "init", str(workspace)).returncode, 0)
            app_project = workspace / "demo-app-src"
            _write_demo_app_fixture(app_project)

            install = _run_bog(workspace, "store", "install", "demo-app-src", "--name", "demo-app", "--version", "1.0.0")
            self.assertEqual(install.returncode, 0, install.stderr + install.stdout)
            verify = _run_bog(workspace, "store", "verify", "demo-app-1.0.0")
            self.assertEqual(verify.returncode, 0, verify.stderr + verify.stdout)

            run = _run_bog(workspace, "app", "run", "demo-app")
            self.assertEqual(run.returncode, 0, run.stderr + run.stdout)
            run_receipt = json.loads(run.stdout)
            self.assertEqual(run_receipt["execution_status"], "completed")
            self.assertIn("demo-app verified run", run_receipt["stdout"])

            installed_app = workspace / ".bogos" / "store" / "installed" / "demo-app-1.0.0" / "app.py"
            installed_app.write_text("print('tampered')\n")
            rejected = _run_bog(workspace, "app", "run", "demo-app")
            self.assertNotEqual(rejected.returncode, 0)
            rejected_receipt = json.loads(rejected.stdout)
            self.assertEqual(rejected_receipt["execution_status"], "blocked")
            self.assertIn("installed tree hash mismatch", rejected_receipt["failures"][0]["reason"])

    def test_public_demo_report_script_emits_receipt_and_report(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            report, receipt = evaluate_bogos_lite_demo(
                artifact_dir=root / "demo",
                report_path=root / "bogos_lite_demo_report.json",
                receipt_path=root / "bogos_lite_demo_receipt.json",
            )

            self.assertEqual(report["format"], "BOGOS-lite-public-demo-report-5.0")
            self.assertEqual(receipt["format"], "BOGOS-lite-public-demo-receipt-5.0")
            self.assertEqual(receipt["execution_status"], "completed")
            self.assertEqual(report["demo_receipt"]["execution_status"], "completed")
            self.assertEqual(report["latest_receipt"]["format"], "BOGOS-public-demo-report-4.5")


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


def _write_demo_app_fixture(root: Path) -> None:
    root.mkdir(parents=True)
    (root / "README.txt").write_text("demo app package\n")
    (root / "app.py").write_text("print('demo-app verified run')\n")
    (root / "bog_app.json").write_text(json.dumps({
        "format": "BOGOS-app-manifest-5.0",
        "apps": {
            "demo-app": {
                "command": [sys.executable, "app.py"],
            },
        },
    }, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    unittest.main()
