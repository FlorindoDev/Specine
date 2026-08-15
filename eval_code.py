import os
import re
import sys
import json
import argparse
import math
import multiprocessing
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import fmean
from typing import Any

from cli_types import positive_int


if hasattr(sys, "set_int_max_str_digits"):
    sys.set_int_max_str_digits(0)


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

    def to_dict(self) -> dict[str, Any]:
        return {
            "results_dir": self.results_dir,
            "discovered_problem_count": self.discovered_problem_count,
            "expected_problem_count": self.expected_problem_count,
            "iteration_count": self.iteration_count,
            "complete": self.complete,
            "iterations": [asdict(metric) for metric in self.iterations],
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


def _run_test_in_subprocess(in_outs, code, debug, result):
    import testing_util as test_util

    try:
        if debug:
            print(f"Running test for problem: {in_outs}")
        result.append(test_util.run_test(in_outs, code, debug))
        if debug:
            print(f"Test completed with result: {result}")
    except Exception as e:
        if debug:
            print(f"Error in _run_test_in_subprocess: {e}")


def check_correctness(in_outs, code, timeout, debug):
    manager = multiprocessing.Manager()
    result = manager.list()
    p = multiprocessing.Process(target=_run_test_in_subprocess, args=(in_outs, code, debug, result))
    p.start()
    p.join(timeout=timeout + 1)
    if p.is_alive():
        if debug:
            print(f"Process is still alive. Killing the process.")
        p.kill()
    if not result:
        avg_number_tests = 21
        result = [[-1] * avg_number_tests]
        if debug:
            print(f"Global timeout occurred, returning default result.")
    if debug:
        print(f"Final result: {result}")
    return result[0]


def eval_code(args, in_outs, code, TIMEOUT=15):
    import numpy as np

    res = [-2]
    try:
        res = check_correctness(in_outs, code, timeout=TIMEOUT, debug=args.debug)
        fixed = []
        for e in res:
            if isinstance(e, np.ndarray):
                e = e.item(0)
            if isinstance(e, np.bool_):
                e = bool(e)
            fixed.append(e)
        res = fixed
    except Exception as e:
        print(f"test framework exception = {repr(e)}{e}\n")
    finally:
        assert isinstance(res, list)

    pass_ratio = res.count(True) / len(in_outs['inputs'])

    return res, pass_ratio


def eval_code_new(args, all_in_outs, code, TIMEOUT=15):
    import numpy as np

    results = []
    for i in range(len(all_in_outs['inputs'])):
        in_outs = {'inputs': [all_in_outs['inputs'][i]], 'outputs': [all_in_outs['outputs'][i]]}
        _, pass_ratio = eval_code(args, in_outs, code, TIMEOUT)
        if True in _:
            results.append(1.0)
        else:
            results.append(0.0)

    return results, np.average(results)


def load_data(data_name: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    from datasets import load_dataset

    if data_name == 'apps':
        ds_train = load_dataset("./Datasets/apps", split="train", trust_remote_code=True)
        ds_test = load_dataset("./Datasets/apps", split="test", trust_remote_code=True)
        train_data = []
        test_data = []
        for temp in ds_train:
            train_data.append(dict(temp))
        for temp in ds_test:
            test_data.append(dict(temp))
        return train_data, test_data
    elif data_name == 'code_contests':
        ds_train = load_dataset("./Datasets/code_contests", split="train", trust_remote_code=True)
        ds_test = load_dataset("./Datasets/code_contests", split="test", trust_remote_code=True)
        train_data = []
        test_data = []
        for i, temp in enumerate(ds_train):
            temp = dict(temp)
            temp['problem_id'] = i
            train_data.append(temp)
        for i, temp in enumerate(ds_test):
            temp = dict(temp)
            temp['problem_id'] = i
            test_data.append(temp)
        return train_data, test_data
    elif data_name == 'xCodeEval':
        train_data = []
        test_data = []
        for temp in open("./Datasets/xCodeEval/program_synthesis/train/train.jsonl", 'r', encoding='utf-8').readlines():
            train_data.append(json.loads(temp))
        for temp in open("./Datasets/xCodeEval/program_synthesis/test/test.jsonl", 'r', encoding='utf-8').readlines():
            test_data.append(json.loads(temp))
        return train_data, test_data
    raise ValueError(f"Dataset non supportato: {data_name}")


def sanitize_code(input_string, split_word):
    if input_string.find(split_word[0]) != -1 and input_string.find(split_word[1]) != -1:
        pattern = re.compile(fr'{re.escape(split_word[0])}(.*?){re.escape(split_word[1])}', re.DOTALL)
        matches = re.findall(pattern, input_string)
        input_string = ''.join(matches)
    code_1 = []
    for i in input_string.split('\n'):
        if i[:7] != 'assert ' and i[:1] != '#':
            code_1.append(i)
    output_string = '\n'.join(code_1)

    return output_string


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--results_dir",
        type=Path,
        help=(
            "directory Specine containing "
            "<problem_id>_test_result_<iteration> files"
        ),
    )
    parser.add_argument(
        "--expected_problems",
        type=positive_int,
        help="expected benchmark problem count; required with --results_dir",
    )
    parser.add_argument(
        "--metrics_output",
        type=Path,
        help="metrics JSON path; default: <results_dir>/iteration_metrics.json",
    )
    parser.add_argument(
        "--data_name",
        choices=("apps", "code_contests", "xCodeEval"),
        help="legacy evaluation mode: apps, code_contests, xCodeEval",
    )
    parser.add_argument(
        "--model_name",
        type=str,
        help="legacy evaluation mode model; default: project DEFAULT_MODEL",
    )
    parser.add_argument("--train", action="store_true")
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--debug", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)

    if args.results_dir is not None:
        if any((
            args.data_name is not None,
            args.model_name is not None,
            args.train,
            args.test,
            args.debug,
        )):
            parser.error(
                "--results_dir cannot be combined with legacy evaluation options"
            )
        if args.expected_problems is None:
            parser.error(
                "--expected_problems is required with --results_dir so incomplete "
                "runs are not reported as paper-comparable"
            )
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
        print(f"Metrics saved: {output_path}")
        if not report.complete:
            print(
                "WARNING: partial run; metrics are not comparable with paper results"
            )
        return 0

    if args.expected_problems is not None or args.metrics_output is not None:
        parser.error("--expected_problems and --metrics_output require --results_dir")
    if args.data_name is None:
        parser.error("--data_name is required in legacy evaluation mode")

    from model import DEFAULT_MODEL

    args.model_name = args.model_name or DEFAULT_MODEL
    return _run_legacy_evaluation(args)


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


def _run_legacy_evaluation(args) -> int:
    from tqdm import tqdm

    train_data, test_data = load_data(args.data_name)
    all_data = {'train': train_data, 'test': test_data}
    if args.train:
        data_mode = 'train'
    elif args.test:
        data_mode = 'test'
    else:
        exit()

    all_pass_ratio = []
    for index, data_instance in enumerate(tqdm(all_data[data_mode])):
        problem_id = data_instance['problem_id']
        if os.path.exists(f'./Results/{args.model_name}/{args.data_name}/{data_mode}/{problem_id}_test_result'):
            pass_ratio = float(open(f'./Results/{args.model_name}/{args.data_name}/{data_mode}/{problem_id}_test_result', 'r', encoding='utf-8').read())
            all_pass_ratio.append(pass_ratio)
            continue
        else:
            if not (os.path.exists(f'./Results/{args.model_name}/{args.data_name}/{data_mode}/{problem_id}_code') or
                    os.path.exists(f'./Results/{args.model_name}/{args.data_name}/{problem_id}_ids.npy')):
                continue

            generated_code = ""
            test_case_list: dict[str, Any] = {'inputs': [], 'outputs': []}
            if args.data_name == 'apps':
                generated_code = open(f'./Results/{args.model_name}/{args.data_name}/{data_mode}/{problem_id}_code', 'r').read()
                generated_code = sanitize_code(generated_code, ["```python", "```"])

                if data_instance['input_output'] == '' or data_instance['input_output'] is None:
                    test_case_list = {'inputs': [], 'outputs': []}
                else:
                    test_case_list = json.loads(data_instance['input_output'])

                if len(test_case_list['inputs']) == 0:
                    continue
            elif args.data_name == 'code_contests':
                generated_code = open(f'./Results/{args.model_name}/{args.data_name}/{data_mode}/{problem_id}_code', 'r').read()
                generated_code = sanitize_code(generated_code, ["```python", "```"])

                private_test_cases = data_instance['private_tests']
                generated_test_cases = data_instance['generated_tests']
                test_case_list = {'inputs': [], 'outputs': []}
                for i_ptc in range(len(private_test_cases['input'])):
                    test_case_list['inputs'].append(private_test_cases['input'][i_ptc])
                    test_case_list['outputs'].append(private_test_cases['output'][i_ptc])
                for i_gtc in range(len(generated_test_cases['input'])):
                    if generated_test_cases['input'][i_gtc] not in test_case_list['inputs']:
                        test_case_list['inputs'].append(generated_test_cases['input'][i_gtc])
                        test_case_list['outputs'].append(generated_test_cases['output'][i_gtc])
                if len(test_case_list['inputs']) == 0:
                    continue
            elif args.data_name == 'xCodeEval':
                generated_code = open(f'./Results/{args.model_name}/{args.data_name}/{data_mode}/{problem_id}_code', 'r').read()
                generated_code = sanitize_code(generated_code, ["```python", "```"])

                sample_inputs = data_instance['sample_inputs']
                sample_outputs = data_instance['sample_outputs']
                unittest = data_instance['unittest']
                test_case_list = {'inputs': [], 'outputs': []}
                for i_si in range(len(sample_inputs)):
                    test_case_list['inputs'].append(sample_inputs[i_si])
                    test_case_list['outputs'].append(sample_outputs[i_si])
                for i_u in range(len(unittest)):
                    test_case_list['inputs'].append(unittest[i_u]['input'])
                    test_case_list['outputs'].append(unittest[i_u]['output'])
                if len(test_case_list['inputs']) == 0:
                    continue
            else:
                raise ValueError(f"Dataset non supportato: {args.data_name}")

            res, pass_ratio = eval_code(args, test_case_list, generated_code)
            all_pass_ratio.append(pass_ratio)
            open(f'./Results/{args.model_name}/{args.data_name}/{data_mode}/{problem_id}_test_result', 'w', encoding='utf-8').write(str(pass_ratio))

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
