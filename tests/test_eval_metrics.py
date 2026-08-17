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
        self.assertIn("Token usage: unavailable", stdout.getvalue())

    def test_includes_token_totals_by_iteration_and_agent(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            results_dir = Path(temp_dir)
            self._write_result(results_dir, "1", 0, 1.0)
            self._write_token_summary(results_dir)

            report = build_iteration_metrics_report(
                results_dir,
                expected_problem_count=1,
            )

        token_usage = report.token_usage
        self.assertIsNotNone(token_usage)
        assert token_usage is not None
        self.assertEqual(token_usage.total_tokens, 1000)
        self.assertEqual(
            {agent.agent: agent.total_tokens for agent in token_usage.agents},
            {"Aligner Agent": 400, "Coder Agent": 600},
        )
        self.assertEqual(
            [iteration.iteration for iteration in token_usage.iterations],
            [None, 1],
        )
        self.assertEqual(token_usage.iterations[0].total_tokens, 300)
        self.assertEqual(token_usage.iterations[1].total_tokens, 700)
        self.assertEqual(
            {
                agent.agent: agent.total_tokens
                for agent in token_usage.iterations[0].agents
            },
            {"Aligner Agent": 0, "Coder Agent": 300},
        )
        self.assertEqual(
            {
                agent.agent: agent.total_tokens
                for agent in token_usage.iterations[1].agents
            },
            {"Aligner Agent": 400, "Coder Agent": 300},
        )

        serialized = report.to_dict()["token_usage"]
        assert serialized is not None
        self.assertEqual(serialized["total_tokens"], 1000)
        self.assertEqual(serialized["iterations"][0]["iteration"], "initial")
        self.assertEqual(serialized["iterations"][1]["iteration"], 1)

    def test_cli_prints_all_token_breakdowns(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            results_dir = Path(temp_dir)
            output_path = results_dir / "metrics.json"
            self._write_result(results_dir, "1", 0, 1.0)
            self._write_token_summary(results_dir)

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main([
                    "--results_dir",
                    str(results_dir),
                    "--expected_problems",
                    "1",
                    "--metrics_output",
                    str(output_path),
                ])

        output = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("Total tokens: 1000", output)
        self.assertIn("Tokens by iteration", output)
        self.assertIn("Tokens by agent", output)
        self.assertIn("Tokens by agent and iteration", output)
        self.assertIn("Initial | Aligner Agent: 0", output)
        self.assertIn("1 | Aligner Agent: 400", output)

    def test_calculates_truncation_by_agent_and_iteration(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            results_dir = Path(temp_dir)
            self._write_result(results_dir, "1", 0, 1.0)
            self._write_token_events(results_dir, [
                {
                    "agent": "Coder Agent",
                    "stage": "initial_code",
                    "iteration": None,
                    "output_tokens": 1024,
                    "estimated": False,
                    "truncated": True,
                    "truncation_detection": "api_finish_reason",
                },
                {
                    "agent": "Coder Agent",
                    "stage": "aligned_code",
                    "iteration": 0,
                    "output_tokens": 200,
                    "estimated": False,
                    "truncated": False,
                    "truncation_detection": "api_finish_reason",
                },
                {
                    "agent": "Aligner Agent",
                    "stage": "alignment_rule",
                    "iteration": 0,
                    "output_tokens": 256,
                    "estimated": False,
                },
                {
                    "agent": "Aligner Agent",
                    "stage": "alignment_rule",
                    "iteration": 1,
                    "output_tokens": 100,
                    "estimated": False,
                },
                {
                    "agent": "Unknown Agent",
                    "stage": "unknown",
                    "iteration": 1,
                    "output_tokens": 100,
                    "estimated": False,
                },
            ])

            report = build_iteration_metrics_report(
                results_dir,
                expected_problem_count=1,
            )

        truncation = report.truncation
        self.assertIsNotNone(truncation)
        assert truncation is not None
        self.assertEqual(truncation.stats.analyzed_calls, 4)
        self.assertEqual(truncation.stats.truncated_calls, 2)
        self.assertEqual(truncation.stats.truncated_response_percent, 50.0)
        self.assertEqual(
            truncation.detection_methods,
            ("api_finish_reason", "legacy_output_limit_heuristic"),
        )
        self.assertEqual(
            [iteration.iteration for iteration in truncation.iterations],
            [None, 1, 2],
        )
        initial_agents = {
            agent.agent: agent.stats
            for agent in truncation.iterations[0].agents
        }
        self.assertEqual(
            initial_agents["Coder Agent"].truncated_response_percent,
            100.0,
        )
        self.assertIsNone(
            initial_agents["Aligner Agent"].truncated_response_percent
        )

        serialized = report.to_dict()["truncation"]
        assert serialized is not None
        self.assertEqual(serialized["truncated_response_percent"], 50.0)
        self.assertEqual(
            serialized["iterations"][1]["agents"]["Aligner Agent"][
                "truncated_response_percent"
            ],
            100.0,
        )

    def test_cli_prints_truncation_breakdown(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            results_dir = Path(temp_dir)
            output_path = results_dir / "metrics.json"
            self._write_result(results_dir, "1", 0, 1.0)
            self._write_token_events(results_dir, [{
                "agent": "Coder Agent",
                "stage": "aligned_code",
                "iteration": 0,
                "output_tokens": 1024,
                "estimated": False,
            }])

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main([
                    "--results_dir",
                    str(results_dir),
                    "--expected_problems",
                    "1",
                    "--metrics_output",
                    str(output_path),
                ])

        output = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("Response truncation detection", output)
        self.assertIn("Coder Agent: 100.00% (1/1)", output)
        self.assertIn("1 | Coder Agent: 100.00% (1/1)", output)

    @staticmethod
    def _write_result(
        results_dir: Path,
        problem_id: str,
        iteration_index: int,
        pass_ratio: float,
    ) -> None:
        path = results_dir / f"{problem_id}_test_result_{iteration_index}"
        path.write_text(str(pass_ratio), encoding="utf-8")

    @staticmethod
    def _write_token_summary(results_dir: Path) -> None:
        def bucket(total: int) -> dict[str, int]:
            return {
                "calls": 1,
                "input_tokens": 0,
                "output_tokens": total,
                "total_tokens": total,
                "estimated_calls": 0,
            }

        summary = {
            "totals": bucket(1000),
            "agents": {
                "Coder Agent": bucket(600),
                "Aligner Agent": bucket(400),
            },
            "iterations": {
                "0": {
                    "totals": bucket(700),
                    "agents": {
                        "Coder Agent": bucket(300),
                        "Aligner Agent": bucket(400),
                    },
                },
                "initial": {
                    "totals": bucket(300),
                    "agents": {"Coder Agent": bucket(300)},
                },
            },
        }
        (results_dir / "token_usage_summary.json").write_text(
            json.dumps(summary),
            encoding="utf-8",
        )

    @staticmethod
    def _write_token_events(
        results_dir: Path,
        events: list[dict[str, object]],
    ) -> None:
        (results_dir / "token_usage.jsonl").write_text(
            "".join(json.dumps(event) + "\n" for event in events),
            encoding="utf-8",
        )


if __name__ == "__main__":
    unittest.main()
