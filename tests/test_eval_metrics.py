import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from eval_code import build_iteration_metrics_report, main


class IterationMetricsTests(unittest.TestCase):
    def test_calculates_paper_metrics_independently_for_each_iteration(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            results_dir = Path(temp_dir)
            self._write_result(results_dir, "problem_1", 0, 1.0)
            self._write_result(results_dir, "problem_2", 0, 0.5)
            self._write_result(results_dir, "problem_3", 0, 0.0)
            self._write_result(results_dir, "problem_1", 1, 1.0)
            self._write_result(results_dir, "problem_2", 1, 1.0)
            self._write_result(results_dir, "problem_3", 1, 0.5)

            report = build_iteration_metrics_report(
                results_dir,
                expected_problem_count=3,
            )

        self.assertTrue(report.complete)
        self.assertEqual(report.discovered_problem_count, 3)
        self.assertEqual(
            [metric.iteration for metric in report.iterations],
            [1, 2],
        )
        self.assertEqual(report.iterations[0].pass_at_1_percent, 33.33)
        self.assertEqual(report.iterations[0].avg_pass_ratio_percent, 50.0)
        self.assertEqual(report.iterations[1].pass_at_1_percent, 66.67)
        self.assertEqual(report.iterations[1].avg_pass_ratio_percent, 83.33)

    def test_marks_incomplete_iteration_without_mixing_other_iterations(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            results_dir = Path(temp_dir)
            self._write_result(results_dir, "1", 0, 1.0)
            self._write_result(results_dir, "2", 0, 0.0)
            self._write_result(results_dir, "1", 1, 0.5)

            report = build_iteration_metrics_report(
                results_dir,
                expected_problem_count=3,
            )

        self.assertFalse(report.complete)
        first, second = report.iterations
        self.assertEqual(first.problem_count, 2)
        self.assertEqual(first.missing_problem_count, 1)
        self.assertEqual(first.pass_at_1_percent, 50.0)
        self.assertEqual(first.avg_pass_ratio_percent, 50.0)
        self.assertEqual(second.problem_count, 1)
        self.assertEqual(second.missing_problem_count, 2)
        self.assertEqual(second.pass_at_1_percent, 0.0)
        self.assertEqual(second.avg_pass_ratio_percent, 50.0)

    def test_rejects_pass_ratio_outside_unit_interval(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            results_dir = Path(temp_dir)
            self._write_result(results_dir, "1", 0, 1.5)

            with self.assertRaisesRegex(ValueError, "between 0 and 1"):
                build_iteration_metrics_report(results_dir)

    def test_reports_an_entirely_missing_iteration(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            results_dir = Path(temp_dir)
            self._write_result(results_dir, "1", 0, 1.0)
            self._write_result(results_dir, "1", 2, 0.5)

            report = build_iteration_metrics_report(
                results_dir,
                expected_problem_count=1,
            )

        self.assertEqual(report.iteration_count, 3)
        missing_iteration = report.iterations[1]
        self.assertEqual(missing_iteration.iteration, 2)
        self.assertEqual(missing_iteration.problem_count, 0)
        self.assertIsNone(missing_iteration.pass_at_1_percent)
        self.assertIsNone(missing_iteration.avg_pass_ratio_percent)
        self.assertFalse(report.complete)

    def test_cli_saves_json_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            results_dir = Path(temp_dir) / "run"
            results_dir.mkdir()
            output_path = Path(temp_dir) / "metrics.json"
            self._write_result(results_dir, "1", 0, 1.0)
            self._write_result(results_dir, "2", 0, 0.5)

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main([
                    "--results_dir",
                    str(results_dir),
                    "--expected_problems",
                    "2",
                    "--metrics_output",
                    str(output_path),
                ])

            saved_report = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertTrue(saved_report["complete"])
        self.assertEqual(saved_report["iterations"][0]["pass_at_1_percent"], 50.0)
        self.assertIn("Pass@1", stdout.getvalue())
        self.assertIn("AvgPassRatio", stdout.getvalue())

    @staticmethod
    def _write_result(
        results_dir: Path,
        problem_id: str,
        iteration_index: int,
        pass_ratio: float,
    ) -> None:
        path = results_dir / f"{problem_id}_test_result_{iteration_index}"
        path.write_text(str(pass_ratio), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
