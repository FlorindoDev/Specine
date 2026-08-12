import json
import os
from pathlib import Path

from benchmarks import get_benchmark


os.environ["TOKENIZERS_PARALLELISM"] = "false"
DATASET_DIR = Path(__file__).resolve().parent / "Datasets"


def load_data(benchmark_name):
    benchmark = get_benchmark(benchmark_name)
    dataset_path = DATASET_DIR / benchmark.dataset_file
    if not dataset_path.is_file():
        raise FileNotFoundError(
            f"Dataset mancante: {dataset_path}. Esegui: "
            f"python download_datasets.py --benchmark {benchmark_name}"
        )

    with dataset_path.open("r", encoding="utf-8") as dataset_file:
        return [json.loads(line) for line in dataset_file if line.strip()]


def get_evaluation_test_cases(benchmark_name, data_instance):
    benchmark = get_benchmark(benchmark_name)
    try:
        return data_instance[benchmark.evaluation_field]
    except KeyError as error:
        raise KeyError(
            f"Il record {data_instance.get('problem_id', '?')} non contiene "
            f"il campo {benchmark.evaluation_field} richiesto da "
            f"{benchmark.display_name}."
        ) from error


def get_specification(benchmark_name, test_case, prompt, starter_code=None):
    benchmark = get_benchmark(benchmark_name)
    if benchmark.dataset_family in ["apps", "code_contests"]:
        _input = ""
        data = prompt
        _input += data
        if starter_code is not None:
            _input += "\n" + starter_code

        data = test_case
        if data is None:
            _input += "\n\n"
        elif not data.get("fn_name"):
            _input += "\n\nUse Standard Input format. "
        else:
            _input += "\n\nUse Call-Based format. "
    return _input


def build_specification(benchmark_name, data_instance, test_cases):
    benchmark = get_benchmark(benchmark_name)
    if benchmark.dataset_family == "apps":
        prompt = data_instance["question"]
        starter_code = data_instance["starter_code"] or None
    elif benchmark.dataset_family == "code_contests":
        prompt = data_instance["description"]
        starter_code = None
    else:
        raise ValueError(
            f"Famiglia dataset non supportata: {benchmark.dataset_family}"
        )

    return get_specification(
        benchmark_name,
        test_cases,
        prompt,
        starter_code,
    )


def to_code_prompt(specification, test_case_list):
    new_prompt = f"#QUESTION:\n{specification.strip()}\n\n#INSTRUCTION:\n"
    if test_case_list is None:
        new_prompt += ""
    elif not test_case_list.get("fn_name"):
        new_prompt = new_prompt.replace("Use Standard Input format.", "")
        new_prompt += "Use Standard Input format. "
    else:
        new_prompt = new_prompt.replace("Use Call-Based format.", "")
        new_prompt += "Use Call-Based format. "
    instruction_suffix = \
        "Please provide a self-contained Python script that solves the above programming specification in a markdown code block (without text and test cases):"
    new_prompt += instruction_suffix
    new_prompt += "\n\n#ANSWER:\n```python\n\n```\n"
    return new_prompt
