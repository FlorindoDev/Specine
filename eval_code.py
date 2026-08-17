import argparse
import json
import math
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import fmean
from typing import Any

from cli_types import positive_int
from token_usage import (
    TokenUsageReport,
    TruncationReport,
    TruncationStats,
    load_token_usage_report,
    load_truncation_report,
)


_ITERATION_RESULT_PATTERN = re.compile(
    r"^(?P<problem_id>.+)_test_result_(?P<iteration_index>\d+)$"
)


@dataclass(frozen=True)
class IterationMetrics:
    iteration: int
    file_iteration_index: int
    problem_count: int
    missing_problem_count: int
    pass_at_1_percent: float | None
    avg_pass_ratio_percent: float | None
    complete: bool


@dataclass(frozen=True)
class IterationMetricsReport:
    results_dir: str
    discovered_problem_count: int
    expected_problem_count: int | None
    iteration_count: int
    complete: bool
    iterations: tuple[IterationMetrics, ...]
    token_usage: TokenUsageReport | None
    truncation: TruncationReport | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "results_dir": self.results_dir,
            "discovered_problem_count": self.discovered_problem_count,
            "expected_problem_count": self.expected_problem_count,
            "iteration_count": self.iteration_count,
            "complete": self.complete,
            "iterations": [asdict(metric) for metric in self.iterations],
            "token_usage": (
                None if self.token_usage is None else self.token_usage.to_dict()
            ),
            "truncation": (
                None if self.truncation is None else self.truncation.to_dict()
            ),
        }


def build_iteration_metrics_report(
    results_dir: str | Path,
    expected_problem_count: int | None = None,
) -> IterationMetricsReport:
    """Aggregate paper-style Pass@1 and AvgPassRatio for every iteration."""

    if expected_problem_count is not None and expected_problem_count <= 0:
        raise ValueError("expected_problem_count must be greater than 0")

    directory = Path(results_dir)
    results_by_iteration = _load_iteration_results(directory)
    discovered_problem_ids = {
        problem_id
        for iteration_results in results_by_iteration.values()
        for problem_id in iteration_results
    }
    discovered_problem_count = len(discovered_problem_ids)
    if (
        expected_problem_count is not None
        and discovered_problem_count > expected_problem_count
    ):
        raise ValueError(
            "expected_problem_count is smaller than discovered problem count "
            f"({expected_problem_count} < {discovered_problem_count})"
        )

    target_problem_count = expected_problem_count or discovered_problem_count
    last_iteration_index = max(results_by_iteration)
    iteration_metrics = tuple(
        _calculate_iteration_metrics(
            iteration_index,
            results_by_iteration.get(iteration_index, {}),
            target_problem_count,
        )
        for iteration_index in range(last_iteration_index + 1)
    )
    report_complete = (
        discovered_problem_count == target_problem_count
        and all(metric.complete for metric in iteration_metrics)
    )
    return IterationMetricsReport(
        results_dir=str(directory.resolve()),
        discovered_problem_count=discovered_problem_count,
        expected_problem_count=expected_problem_count,
        iteration_count=len(iteration_metrics),
        complete=report_complete,
        iterations=iteration_metrics,
        token_usage=load_token_usage_report(directory),
        truncation=load_truncation_report(directory),
    )


def save_iteration_metrics_report(
    report: IterationMetricsReport,
    output_path: str | Path,
) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as output_file:
        json.dump(report.to_dict(), output_file, ensure_ascii=False, indent=2)


def _load_iteration_results(
    results_dir: Path,
) -> dict[int, dict[str, float]]:
    if not results_dir.is_dir():
        raise ValueError(f"results directory does not exist: {results_dir}")

    results_by_iteration: dict[int, dict[str, float]] = {}
    for path in results_dir.iterdir():
        if not path.is_file():
            continue
        match = _ITERATION_RESULT_PATTERN.fullmatch(path.name)
        if match is None:
            continue

        pass_ratio = _read_pass_ratio(path)
        iteration_index = int(match.group("iteration_index"))
        problem_id = match.group("problem_id")
        results_by_iteration.setdefault(iteration_index, {})[problem_id] = pass_ratio

    if not results_by_iteration:
        raise ValueError(
            f"no <problem_id>_test_result_<iteration> files found in {results_dir}"
        )
    return results_by_iteration


def _read_pass_ratio(path: Path) -> float:
    try:
        pass_ratio = float(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError) as error:
        raise ValueError(f"invalid pass ratio in {path}") from error
    if not math.isfinite(pass_ratio) or not 0.0 <= pass_ratio <= 1.0:
        raise ValueError(
            f"invalid pass ratio in {path}: expected finite value between 0 and 1"
        )
    return pass_ratio


def _calculate_iteration_metrics(
    iteration_index: int,
    problem_results: dict[str, float],
    target_problem_count: int,
) -> IterationMetrics:
    pass_ratios = list(problem_results.values())
    problem_count = len(pass_ratios)
    if pass_ratios:
        pass_at_1_percent = round(
            pass_ratios.count(1.0) / problem_count * 100,
            2,
        )
        avg_pass_ratio_percent = round(fmean(pass_ratios) * 100, 2)
    else:
        pass_at_1_percent = None
        avg_pass_ratio_percent = None

    return IterationMetrics(
        iteration=iteration_index + 1,
        file_iteration_index=iteration_index,
        problem_count=problem_count,
        missing_problem_count=target_problem_count - problem_count,
        pass_at_1_percent=pass_at_1_percent,
        avg_pass_ratio_percent=avg_pass_ratio_percent,
        complete=problem_count == target_problem_count,
    )


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--results_dir",
        type=Path,
        required=True,
        help=(
            "directory Specine containing "
            "<problem_id>_test_result_<iteration> files"
        ),
    )
    parser.add_argument(
        "--expected_problems",
        type=positive_int,
        required=True,
        help="expected benchmark problem count",
    )
    parser.add_argument(
        "--metrics_output",
        type=Path,
        help="metrics JSON path; default: <results_dir>/iteration_metrics.json",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)

    try:
        report = build_iteration_metrics_report(
            args.results_dir,
            expected_problem_count=args.expected_problems,
        )
        output_path = (
            args.metrics_output
            if args.metrics_output is not None
            else args.results_dir / "iteration_metrics.json"
        )
        save_iteration_metrics_report(report, output_path)
    except (OSError, ValueError) as error:
        parser.error(str(error))

    _print_iteration_metrics(report)
    _print_token_usage(report.token_usage)
    _print_truncation(report.truncation)
    print(f"Metrics saved: {output_path}")
    if not report.complete:
        print("WARNING: partial run; metrics are not comparable with paper results")
    return 0


def _print_iteration_metrics(report: IterationMetricsReport) -> None:
    target_problem_count = (
        report.expected_problem_count or report.discovered_problem_count
    )
    print("N  Problems  Pass@1  AvgPassRatio  Status")
    for metric in report.iterations:
        pass_at_1 = _format_percentage(metric.pass_at_1_percent)
        avg_pass_ratio = _format_percentage(metric.avg_pass_ratio_percent)
        status = "complete" if metric.complete else "partial"
        print(
            f"{metric.iteration:<2} "
            f"{metric.problem_count:>4}/{target_problem_count:<4} "
            f"{pass_at_1:>8}  {avg_pass_ratio:>12}  {status}"
        )


def _format_percentage(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}%"


def _print_token_usage(token_usage: TokenUsageReport | None) -> None:
    print()
    if token_usage is None:
        print("Token usage: unavailable (token_usage_summary.json not found)")
        return

    print(f"Total tokens: {token_usage.total_tokens}")
    print("Tokens by iteration")
    for iteration in token_usage.iterations:
        label = "Initial" if iteration.iteration is None else str(iteration.iteration)
        print(f"  {label}: {iteration.total_tokens}")

    print("Tokens by agent")
    for agent in token_usage.agents:
        print(f"  {agent.agent}: {agent.total_tokens}")

    print("Tokens by agent and iteration")
    for iteration in token_usage.iterations:
        label = "Initial" if iteration.iteration is None else str(iteration.iteration)
        for agent in iteration.agents:
            print(f"  {label} | {agent.agent}: {agent.total_tokens}")


def _print_truncation(truncation: TruncationReport | None) -> None:
    print()
    if truncation is None:
        print("Response truncation: unavailable (token_usage.jsonl not found)")
        return

    methods = ", ".join(truncation.detection_methods) or "none"
    print(f"Response truncation detection: {methods}")
    print(f"Truncated responses: {_format_truncation(truncation.stats)}")

    print("Truncated responses by agent")
    for agent in truncation.agents:
        print(f"  {agent.agent}: {_format_truncation(agent.stats)}")

    print("Truncated responses by agent and iteration")
    for iteration in truncation.iterations:
        label = "Initial" if iteration.iteration is None else str(iteration.iteration)
        for agent in iteration.agents:
            print(
                f"  {label} | {agent.agent}: "
                f"{_format_truncation(agent.stats)}"
            )


def _format_truncation(stats: TruncationStats) -> str:
    percentage = stats.truncated_response_percent
    formatted_percentage = "n/a" if percentage is None else f"{percentage:.2f}%"
    return (
        f"{formatted_percentage} "
        f"({stats.truncated_calls}/{stats.analyzed_calls})"
    )


if __name__ == '__main__':
    raise SystemExit(main())
