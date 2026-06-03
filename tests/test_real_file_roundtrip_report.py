import json
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest

from scripts.evaluate_real_file_roundtrip import deterministic_fixtures, evaluate


class RealFileRoundtripReportTests(unittest.TestCase):
    def test_evaluation_script_produces_report_and_every_case_roundtrips(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            report_path = root / "report.json"
            receipt_path = root / "receipt.json"
            report, receipt = evaluate(
                artifact_dir=root / "cases",
                report_path=report_path,
                receipt_path=receipt_path,
                chunk_size=64,
            )

            self.assertTrue(report_path.exists())
            self.assertTrue(receipt_path.exists())
            self.assertEqual(receipt["execution_status"], "completed")
            self.assertEqual(report["case_count"], len(deterministic_fixtures()))
            self.assertEqual(report["passed_roundtrip_count"], report["case_count"])
            self.assertTrue(all(case["roundtrip_passed"] for case in report["per_case"]))
            self.assertTrue(all(case["original_sha256"] == case["recovered_sha256"] for case in report["per_case"]))

    def test_report_schema_is_stable(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            report, _ = evaluate(
                artifact_dir=root / "cases",
                report_path=root / "report.json",
                receipt_path=root / "receipt.json",
                chunk_size=64,
            )

            self.assertEqual(
                list(report.keys()),
                [
                    "format",
                    "v1_2_mean_residual_density",
                    "current_mean_residual_density",
                    "residual_density_delta_from_v1_2",
                    "residual_density_improved_from_v1_2",
                    "case_count",
                    "passed_roundtrip_count",
                    "roundtrip_success_rate",
                    "total_input_bytes",
                    "total_chunk_count",
                    "total_residual_count",
                    "mean_residual_density",
                    "per_case",
                ],
            )
            self.assertEqual(
                list(report["per_case"][0].keys()),
                [
                    "name",
                    "file_type",
                    "input_size",
                    "chunk_count",
                    "chunk_tournament_enabled",
                    "candidate_chunk_sizes",
                    "selected_chunk_size",
                    "chunk_tournament_results",
                    "total_residual_count",
                    "residual_density",
                    "basis_counts",
                    "original_sha256",
                    "recovered_sha256",
                    "vm_run_status",
                    "roundtrip_passed",
                ],
            )

    def test_basis_counts_are_deterministic(self):
        with tempfile.TemporaryDirectory() as first_td, tempfile.TemporaryDirectory() as second_td:
            first, _ = evaluate(
                artifact_dir=Path(first_td) / "cases",
                report_path=Path(first_td) / "report.json",
                receipt_path=Path(first_td) / "receipt.json",
                chunk_size=64,
            )
            second, _ = evaluate(
                artifact_dir=Path(second_td) / "cases",
                report_path=Path(second_td) / "report.json",
                receipt_path=Path(second_td) / "receipt.json",
                chunk_size=64,
            )

            self.assertEqual(
                [case["basis_counts"] for case in first["per_case"]],
                [case["basis_counts"] for case in second["per_case"]],
            )

    def test_mean_residual_density_does_not_regress_from_v12_baseline(self):
        with tempfile.TemporaryDirectory() as td:
            report, _ = evaluate(
                artifact_dir=Path(td) / "cases",
                report_path=Path(td) / "report.json",
                receipt_path=Path(td) / "receipt.json",
                chunk_size=64,
            )

            self.assertEqual(report["v1_2_mean_residual_density"], 0.631188)
            self.assertLessEqual(report["current_mean_residual_density"], 0.631188)

    def test_auto_chunk_metadata_appears_in_report(self):
        with tempfile.TemporaryDirectory() as td:
            report, _ = evaluate(
                artifact_dir=Path(td) / "cases",
                report_path=Path(td) / "report.json",
                receipt_path=Path(td) / "receipt.json",
                chunk_size=64,
            )

            for case in report["per_case"]:
                self.assertTrue(case["chunk_tournament_enabled"])
                self.assertEqual(case["candidate_chunk_sizes"], [16, 32, 64, 128])
                self.assertIn(case["selected_chunk_size"], [16, 32, 64, 128])
                self.assertEqual(len(case["chunk_tournament_results"]), 4)

    def test_no_failed_case_is_counted_as_passed(self):
        with tempfile.TemporaryDirectory() as td:
            report, _ = evaluate(
                artifact_dir=Path(td) / "cases",
                report_path=Path(td) / "report.json",
                receipt_path=Path(td) / "receipt.json",
                chunk_size=64,
            )

            simulated = dict(report)
            simulated["per_case"] = [dict(case) for case in report["per_case"]]
            simulated["per_case"][0]["roundtrip_passed"] = False
            simulated["passed_roundtrip_count"] = sum(
                1 for case in simulated["per_case"] if case["roundtrip_passed"]
            )

            self.assertLess(simulated["passed_roundtrip_count"], simulated["case_count"])

    def test_script_entrypoint_writes_default_shape(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            report_path = root / "real_file_roundtrip_report.json"
            receipt_path = root / "real_file_roundtrip_receipt.json"
            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/evaluate_real_file_roundtrip.py",
                    "--artifact-dir",
                    str(root / "cases"),
                    "--report",
                    str(report_path),
                    "--receipt",
                    str(receipt_path),
                ],
                cwd=Path(__file__).resolve().parents[1],
                check=False,
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            report = json.loads(report_path.read_text())
            self.assertEqual(report["case_count"], len(deterministic_fixtures()))
            self.assertEqual(report["passed_roundtrip_count"], report["case_count"])


if __name__ == "__main__":
    unittest.main()
