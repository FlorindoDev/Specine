import multiprocessing
from typing import Any


def _run_test_in_subprocess(
    test_cases: dict[str, Any],
    code: str,
    debug: bool,
    shared_results: Any,
) -> None:
    import testing_util

    try:
        if debug:
            print(f"Running test for problem: {test_cases}")
        shared_results.append(testing_util.run_test(test_cases, code, debug))
        if debug:
            print(f"Test completed with result: {shared_results}")
    except Exception as error:
        if debug:
            print(f"Error while running tests: {error}")


def check_correctness(
    test_cases: dict[str, Any],
    code: str,
    timeout: int,
    debug: bool = False,
) -> list[Any]:
    with multiprocessing.Manager() as manager:
        shared_results = manager.list()
        process = multiprocessing.Process(
            target=_run_test_in_subprocess,
            args=(test_cases, code, debug, shared_results),
        )
        process.start()
        process.join(timeout=timeout + 1)
        if process.is_alive():
            if debug:
                print("Test process timed out; terminating it")
            process.kill()
            process.join()
        results = list(shared_results)

    if not results:
        if debug:
            print("Global timeout occurred; returning default results")
        return [-1] * 21
    return results[0]


def evaluate_code(
    test_cases: dict[str, Any],
    code: str,
    timeout: int = 15,
    debug: bool = False,
) -> tuple[list[Any], float]:
    import numpy as np

    results: list[Any] = [-2]
    try:
        raw_results = check_correctness(test_cases, code, timeout, debug)
        results = []
        for result in raw_results:
            if isinstance(result, np.ndarray):
                result = result.item(0)
            if isinstance(result, np.bool_):
                result = bool(result)
            results.append(result)
    except Exception as error:
        print(f"test framework exception = {error!r}{error}\n")

    pass_ratio = results.count(True) / len(test_cases["inputs"])
    return results, pass_ratio
