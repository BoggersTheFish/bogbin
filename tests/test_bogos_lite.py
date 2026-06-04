import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest

from tests.test_directory_store import _write_mixed_fixture


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


if __name__ == "__main__":
    unittest.main()
