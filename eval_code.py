import os
import re
import sys
import json
import argparse
from typing import Any

import numpy as np
from tqdm import tqdm
import multiprocessing
import testing_util as test_util
from datasets import load_dataset
from model import DEFAULT_MODEL
sys.set_int_max_str_digits(0)


def _run_test_in_subprocess(in_outs, code, debug, result):
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data_name",
        choices=("apps", "code_contests", "xCodeEval"),
        required=True,
        help='apps, code_contests, xCodeEval',
    )
    parser.add_argument(
        "--model_name",
        default=DEFAULT_MODEL,
        type=str,
        help=f"modello LLM; default: {DEFAULT_MODEL}",
    )
    parser.add_argument("--train", action="store_true")
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

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


if __name__ == '__main__':
    main()
