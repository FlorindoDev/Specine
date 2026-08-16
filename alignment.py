import os
import json
import random
import argparse
import numpy as np
from tqdm import tqdm
from cli_types import positive_int
from coder_workflow import (
    CodeGenerationRequest,
    TextGenerator,
    create_coder_workflow,
)
from code_evaluator import evaluate_code
from benchmarks import BENCHMARKS
from data import build_specification, get_evaluation_test_cases, load_data, to_code_prompt
from model import (
    API_MODELS,
    DEFAULT_MODEL,
    LOCAL_MODELS,
    SUPPORTED_MODELS,
    effective_model_name,
    generate_text,
    load_model,
)
from sanitize import sanitize_code, remove_code_blocks
from tester_workflow import (
    TestGenerationRequest,
    create_tester_workflow,
)
from token_usage import GenerationContext, TokenUsageRecorder
from result_cache import (
    cache_matches_model,
    model_result_namespace,
    save_cache_metadata,
)
from workflow_variants import (
    ArchitectureVariant,
    get_variant_capabilities,
    initial_code_cache_name,
)
os.environ["TOKENIZERS_PARALLELISM"] = "false"


def load_coder_trace(path):
    if not os.path.exists(path):
        return {"workflow": "unknown", "artifacts": []}
    with open(path, 'r', encoding='utf-8') as trace_file:
        return json.load(trace_file)


def save_workflow_trace(path, trace):
    with open(path, 'w', encoding='utf-8') as trace_file:
        json.dump(trace, trace_file, ensure_ascii=False, indent=2)


def alignment_rule(args, problem_id, ori_specification, ori_code, ori_test_result, public_test_cases,
                   coder_workflow, optimization_list, cache_list, iteration,
                   text_generator: TextGenerator):
    initial_mutation_instruction_list = [
        ["Specification Background",
             ["Let's provide a concise background for the provided programming specification, explaining the motivation, application context, or any domain-specific knowledge needed. Ensure the explanation is clear and accessible to developers without deep prior knowledge of the domain. This will help large language models understand it better. (Response constraints: Max 200 words, NO code)",
             ]],
        ["Specification Purpose",
            ["Let's concisely explain the purpose of the provided programming specification to improve clarity for large language models. This will help large language models understand it better. (Response constraints: Max 200 words, NO code)",
             ]],
        ["Key Concepts",
            ["Let's identify and explain the key concepts in the provided programming specification for better understanding by large language models. This will help large language models understand it better. (Response constraints: Max 200 words, NO code)",
             ]],
        ["Input Requirement",
            ["Let's analyze the input of the provided programming specification (e.g., data types and format) and list all constraints or boundaries for the inputs (e.g., value ranges, size limits, or specific conditions to be met). This will help large language models understand it better. (Response constraints: Max 200 words, NO code)",
             ]],
        ["Output Requirement",
            ["Let's clearly specify the format of the output, including data types, any required precision (e.g., number of decimal places), separators, or ordering rules. This will help large language models understand it better. (Response constraints: Max 200 words, NO code)",
             ]],
        ["Examples with Explanations",
            ["Provide three test case examples only if none are included in the programming specification. Then, offer a step-by-step explanation of the logic that produces the output. This will help large language models understand it better. (Response constraints: Max 200 words, NO code)",
             ]],
        ["Edge/Corner Cases",
            ["Let's retain the original test cases in the provided programming specification and generate three additional test cases to cover more edge/corner cases. This will help large language models understand it better. (Response constraints: Max 200 words, NO code)",
             ]],
        ["APIs",
            ["Let's specify external APIs or library functions that may be relevant for solving this task. Include only API/library names and their purpose. This will help large language models understand it better. (Response constraints: Max 200 words, NO code)",
             ]],
        ["Error Handling Requirements",
            ["Let's describe the expected behavior when the function encounters invalid inputs. Should it return a default value, throw an error, or handle the case differently? This will help large language models understand it better. (Response constraints: Max 200 words, NO code)",
             ]],
        ["Hints or Tips",
            ["Offer optional hints or implementation suggestions (e.g., specific algorithms or data structures to use). Keep the hints concise and high-level. This will help large language models understand it better. (Response constraints: Max 200 words, NO code)",
             ]]
    ]

    ori_code = ori_code.strip()
    if ori_specification in cache_list.keys():
        optimization_points = cache_list[ori_specification]
    else:
        code_understanding_instruction = '''Analyze the given code exclusively and translate it as the lifted specification based on the format of defined DSL requirement. Ensure the response does not contain code. Limit the response to 500 words.\nFormat:\n'''
        code_understanding_instruction += '''(1) Problem Background: Describes the background and context of the code, providing the necessary background knowledge for understanding the code's functionality.\n'''
        code_understanding_instruction += '''(2) Functional Requirements: Summarizes the core functionality of the code, specifying its specific objectives or tasks, such as the problem being solved or the task being performed.\n'''
        code_understanding_instruction += '''(3) Input Requirements: Details the inputs required by the code, including input types, formats, and any constraints.\n'''
        code_understanding_instruction += '''(4) Output Requirements: Specifies the outputs of the code, including output types, formats, and any constraints.\n'''
        code_understanding_instruction += '''(5) Test Case Examples (Optional): Extracts the test cases included in the code, which are often used to verify code correctness and serve as usage examples.\n'''
        code_understanding_instruction += '''(6) External APIs (Optional): Lists any external APIs or library functions used by the code and describes their purpose and interactions.\n'''
        code_understanding_instruction += '''(7) Additional Explanation: Provides supplementary information, such as design intentions, potential limitations, or special considerations.\n'''
        code_understanding_prompt = f"#CODE:\n```python\n{ori_code}\n```\n\n#INSTRUCTION:\n{code_understanding_instruction}"
        code_understanding = text_generator(
            code_understanding_prompt,
            512,
            GenerationContext(
                agent="Lifter Agent",
                stage="specification_lifting",
                problem_id=problem_id,
                iteration=iteration,
            ),
        )
        code_understanding = code_understanding.replace("\n\n", "\n")

        optimization_points_instruction = "Analyze the input programming specification and the lifted specification to identify misalignments or omissions. Select one or more ingredients to improve the input programming specification from the following ten options: ['Specification Background', 'Specification Purpose', 'Key Concepts', 'Input Requirement', 'Output Requirement', 'Examples with Explanations', 'Edge/Corner Cases', 'APIs', 'Error Handling Requirements']. Respond with a SORTED list by importance, e.g., ['Output Requirement', 'Specification Purpose', 'Examples with Explanations']. (Response constraints: Max 50 words, NO code)"
        optimization_points_prompt = f"{ori_specification}\n\n#INCORRECT GENERATED CODE:\n```python\n{ori_code}\n```\n\n#LIFTED SPECIFICATION OF INCORRECT GENERATED CODE:\n```plaintext\n{code_understanding}\n```\n\n#INSTRUCTION:\n{optimization_points_instruction}"
        optimization_points = text_generator(
            optimization_points_prompt,
            64,
            GenerationContext(
                agent="Aligner Agent",
                stage="alignment_selection",
                problem_id=problem_id,
                iteration=iteration,
            ),
        )
        cache_list[ori_specification] = optimization_points

    optimization_points_list = []
    now_opl = 0
    for i_op in range(len(initial_mutation_instruction_list)):
        if initial_mutation_instruction_list[i_op][0] in optimization_list:
            continue
        if f"'{initial_mutation_instruction_list[i_op][0]}'" in optimization_points:
            now_opl += 1
            i = optimization_points.find(f"'{initial_mutation_instruction_list[i_op][0]}'")
            optimization_points_list.append([i, initial_mutation_instruction_list[i_op]])
        elif f'"{initial_mutation_instruction_list[i_op][0]}"' in optimization_points:
            now_opl += 1
            i = optimization_points.find(f'"{initial_mutation_instruction_list[i_op][0]}"')
            optimization_points_list.append([i, initial_mutation_instruction_list[i_op]])
        else:
            optimization_points_list.append([1000000+random.randint(0, 1000000), initial_mutation_instruction_list[i_op]])

    if len(optimization_points_list) == 0:
        optimization_points_list = [initial_mutation_instruction_list[random.randint(0, len(initial_mutation_instruction_list)-1)]]
    else:
        optimization_points_list = [elem[1] for elem in sorted(optimization_points_list, key=lambda x: x[0], reverse=False)]

    new_specification = ori_specification.replace('\n\n\n\n', '\n').replace('\n\n\n', '\n').strip()
    optimization_rule_prompt = f"{new_specification}\n\n#INSTRUCTION:\n{optimization_points_list[0][1][0]}"
    optimization_rule = text_generator(
        optimization_rule_prompt,
        256,
        GenerationContext(
            agent="Aligner Agent",
            stage="alignment_rule",
            problem_id=problem_id,
            iteration=iteration,
        ),
    )
    optimization_rule = remove_code_blocks(optimization_rule).replace('\n\n', '\n')
    new_specification += f"\n\n#{optimization_points_list[0][0].upper()}:\n```plaintext\n{optimization_rule}\n```"

    new_prompt = new_specification + f"\n\n#INSTRUCTION:\n"
    new_prompt = new_prompt.replace("Use Standard Input format.", "")
    new_prompt = new_prompt.replace("\n\n\n", "\n")
    new_prompt += "Use Standard Input format. "
    new_prompt += \
        "Please provide a self-contained Python script that solves the above programming specification in a markdown code block (without text and test cases):"
    new_prompt += "\n\n#CODE:\n```python\n\n```\n"

    coder_result = coder_workflow.generate(
        CodeGenerationRequest(
            specification=new_specification,
            code_prompt=new_prompt,
            problem_id=problem_id,
            iteration=iteration,
            stage="aligned_code",
        )
    )
    new_code = coder_result.code
    new_code = sanitize_code(new_code, ["```python", "```"])
    _, new_test_result = evaluate_code(
        public_test_cases,
        new_code,
        debug=args.debug,
    )

    return (
        new_specification,
        new_code,
        new_test_result,
        optimization_points_list[0][0],
        cache_list,
        coder_result.to_dict(),
    )

def alignment():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--benchmark",
        choices=tuple(BENCHMARKS),
        required=True,
        help="apps, apps-eval, codecontests-raw",
    )
    parser.add_argument(
        "--model_name",
        default=DEFAULT_MODEL,
        choices=sorted(SUPPORTED_MODELS),
        help=f"modello LLM; default: {DEFAULT_MODEL}",
    )
    parser.add_argument(
        "--variant",
        default=ArchitectureVariant.BASE.value,
        choices=[variant.value for variant in ArchitectureVariant],
        help=(
            "base: original Specine; A: custom Coder; B: custom Tester; "
            "D: both custom workflows"
        ),
    )
    parser.add_argument("--save_dir", default='', type=str, required=True)
    parser.add_argument("--max_iter", default=10, type=positive_int)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    args.data_name = args.benchmark
    args.variant = ArchitectureVariant(args.variant)
    capabilities = get_variant_capabilities(args.variant)
    if args.variant != ArchitectureVariant.BASE:
        args.save_dir = f"{args.save_dir}_{args.variant.value}"

    test_data = load_data(args.benchmark)

    if args.model_name in LOCAL_MODELS:
        model, tokenizer = load_model(args.model_name)
    elif args.model_name in API_MODELS:
        model, tokenizer = None, None
    else:
        parser.error(
            f"unsupported --model_name '{args.model_name}'; "
            f"choose one of: {', '.join(sorted(SUPPORTED_MODELS))}"
        )

    resolved_model_name = effective_model_name(args.model_name)
    result_model_name = model_result_namespace(
        args.model_name,
        resolved_model_name,
    )
    model_result_dir = f'./Results/{result_model_name}/{args.data_name}'
    run_result_dir = f'{model_result_dir}/{args.save_dir}'
    requires_cache_model_validation = result_model_name != args.model_name
    token_usage_recorder = TokenUsageRecorder(
        output_dir=run_result_dir,
        benchmark=args.benchmark,
        model=resolved_model_name,
        variant=args.variant.value,
    )

    def tracked_generate(
        prompt: str,
        max_tokens: int,
        context: GenerationContext,
    ) -> str:
        return generate_text(
            args,
            prompt,
            model,
            tokenizer,
            max_tokens,
            token_usage_recorder,
            context,
        )

    coder_workflow = create_coder_workflow(args.variant, tracked_generate)
    tester_workflow = create_tester_workflow(
        capabilities.custom_tester,
        tracked_generate,
    )
    initial_run_name = initial_code_cache_name(capabilities)
    initial_result_dir = f'{model_result_dir}/{initial_run_name}'

    ori_test_results = {}
    new_test_results = [{} for _ in range(args.max_iter)]

    for index, data_instance in enumerate(tqdm(test_data)):
        problem_id = data_instance['problem_id']
        all_test_cases = get_evaluation_test_cases(args.benchmark, data_instance)

        initial_prompt_path = f'{initial_result_dir}/{problem_id}_prompt'
        initial_code_path = f'{initial_result_dir}/{problem_id}_code'
        initial_test_result_path = f'{initial_result_dir}/{problem_id}_test_result'
        initial_coder_trace_path = f'{initial_result_dir}/{problem_id}_coder_trace.json'
        initial_cache_metadata_path = f'{initial_code_path}.metadata.json'
        cache_files_exist = all(os.path.exists(path) for path in (
            initial_prompt_path,
            initial_code_path,
            initial_test_result_path,
        ))
        cache_model_matches = (
            not requires_cache_model_validation
            or cache_matches_model(
                initial_cache_metadata_path,
                configured_model=args.model_name,
                effective_model=resolved_model_name,
            )
        )
        if not cache_files_exist or not cache_model_matches:
            ori_specification = build_specification(
                args.benchmark,
                data_instance,
                all_test_cases,
            )
            ori_prompt = to_code_prompt(ori_specification, all_test_cases)

            coder_result = coder_workflow.generate(
                CodeGenerationRequest(
                    specification=ori_specification,
                    code_prompt=ori_prompt,
                    problem_id=problem_id,
                    iteration=None,
                    stage="initial_code",
                )
            )
            ori_code = coder_result.code
            if ori_code is None:
                ori_code = ''
            ori_code = sanitize_code(ori_code, ["```python", "```"])
            _, ori_test_result = evaluate_code(
                all_test_cases,
                ori_code,
                debug=args.debug,
            )

            os.makedirs(initial_result_dir, exist_ok=True)
            open(initial_prompt_path, 'w', encoding='utf-8').write(ori_prompt)
            open(initial_code_path, 'w', encoding='utf-8').write(ori_code)
            open(initial_test_result_path, 'w', encoding='utf-8').write(str(ori_test_result))
            save_workflow_trace(initial_coder_trace_path, coder_result.to_dict())
            save_cache_metadata(
                initial_cache_metadata_path,
                configured_model=args.model_name,
                effective_model=resolved_model_name,
            )

        ori_test_results[problem_id] = \
            float(open(initial_test_result_path, 'r', encoding='utf-8').read())
        for iter_n in range(args.max_iter):
            new_test_results[iter_n][problem_id] = \
                float(open(initial_test_result_path, 'r', encoding='utf-8').read())

    ori_pass1 = round(list(ori_test_results.values()).count(1.0) / len(ori_test_results) * 100, 2)
    ori_apr = round(np.average(list(ori_test_results.values())) * 100, 2)

    for index, data_instance in enumerate(tqdm(test_data)):
        problem_id = data_instance['problem_id']
        all_test_cases = get_evaluation_test_cases(args.benchmark, data_instance)
        public_test_cases = data_instance['public_test_cases']

        all_files_exist = []
        for iter_n in range(args.max_iter):
            all_files_exist.append(os.path.exists(f'{run_result_dir}/{problem_id}_prompt_{iter_n}'))
            all_files_exist.append(os.path.exists(f'{run_result_dir}/{problem_id}_code_{iter_n}'))
            all_files_exist.append(os.path.exists(f'{run_result_dir}/{problem_id}_test_result_{iter_n}'))
        if all(all_files_exist):
            print('*' * 40)
            for iter_n in range(args.max_iter):
                new_test_result_all = float(open(f'{run_result_dir}/{problem_id}_test_result_{iter_n}', 'r', encoding='utf-8').read())
                new_test_results[iter_n][problem_id] = new_test_result_all
                new_pass1 = round(list(new_test_results[iter_n].values()).count(1.0) / len(new_test_results[0]) * 100, 2)
                new_apr = round(np.average(list(new_test_results[iter_n].values())) * 100, 2)
                print(f">> ({args.model_name}, {args.data_name}-{index + 1}/{len(test_data)}, iter={iter_n})        Pass@1: {new_pass1}%, AvgPassRatio: {new_apr}%")
            print('*' * 40)
            continue

        ori_specification = build_specification(
            args.benchmark,
            data_instance,
            public_test_cases,
        )
        ori_specification = f'#PROGRAMMING SPECIFICATION:\n```plaintext\n{ori_specification}\n```'

        initial_prompt_path = f'{initial_result_dir}/{problem_id}_prompt'
        initial_code_path = f'{initial_result_dir}/{problem_id}_code'
        initial_test_result_path = f'{initial_result_dir}/{problem_id}_test_result'
        initial_coder_trace_path = f'{initial_result_dir}/{problem_id}_coder_trace.json'
        if all(os.path.exists(path) for path in (
            initial_prompt_path,
            initial_code_path,
            initial_test_result_path,
        )):
            ori_prompt = open(initial_prompt_path, 'r', encoding='utf-8').read()
            ori_code = open(initial_code_path, 'r', encoding='utf-8').read()
            ori_test_result_all = float(open(initial_test_result_path, 'r', encoding='utf-8').read())
            initial_coder_trace = load_coder_trace(initial_coder_trace_path)
            ori_code = sanitize_code(ori_code, ["```python", "```"])
            if ori_test_result_all == 1.0:
                print()
                print('*' * 40)
                for iter_n in range(args.max_iter):
                    if not os.path.exists(run_result_dir):
                        os.makedirs(run_result_dir)
                    open(f'{run_result_dir}/{problem_id}_prompt_{iter_n}', 'w',
                         encoding='utf-8').write(ori_prompt)
                    open(f'{run_result_dir}/{problem_id}_code_{iter_n}', 'w',
                         encoding='utf-8').write(ori_code)
                    open(f'{run_result_dir}/{problem_id}_test_result_{iter_n}', 'w',
                         encoding='utf-8').write(str(ori_test_result_all))
                    save_workflow_trace(
                        f'{run_result_dir}/{problem_id}_coder_trace_{iter_n}.json',
                        initial_coder_trace,
                    )
                    new_test_results[iter_n][problem_id] = ori_test_result_all
                    new_pass1 = round(list(new_test_results[iter_n].values()).count(1.0) / len(new_test_results[0]) * 100, 2)
                    new_apr = round(np.average(list(new_test_results[iter_n].values())) * 100, 2)
                    print(f">> ({args.model_name}, {args.data_name}-{index + 1}/{len(test_data)}, iter={iter_n})        Pass@1: {new_pass1}%, AvgPassRatio: {new_apr}%")
                print('*' * 40)
                continue
            else:
                _, ori_test_result = evaluate_code(
                    public_test_cases,
                    ori_code,
                    debug=args.debug,
                )
                if ori_test_result == 1.0:
                    print()
                    print('*' * 40)
                    for iter_n in range(args.max_iter):
                        if not os.path.exists(run_result_dir):
                            os.makedirs(run_result_dir)
                        open(f'{run_result_dir}/{problem_id}_prompt_{iter_n}', 'w', encoding='utf-8').write(ori_prompt)
                        open(f'{run_result_dir}/{problem_id}_code_{iter_n}', 'w', encoding='utf-8').write(ori_code)
                        open(f'{run_result_dir}/{problem_id}_test_result_{iter_n}', 'w', encoding='utf-8').write(str(ori_test_result_all))
                        save_workflow_trace(
                            f'{run_result_dir}/{problem_id}_coder_trace_{iter_n}.json',
                            initial_coder_trace,
                        )
                        new_test_results[iter_n][problem_id] = ori_test_result_all
                        new_pass1 = round(list(new_test_results[iter_n].values()).count(1.0) / len(new_test_results[0]) * 100, 2)
                        new_apr = round(np.average(list(new_test_results[iter_n].values())) * 100, 2)
                        print(f">> ({args.model_name}, {args.data_name}-{index + 1}/{len(test_data)}, iter={iter_n})        Pass@1: {new_pass1}%, AvgPassRatio: {new_apr}%")
                    print('*' * 40)
                    continue
        else:
            exit()

        test_case_path = f'{run_result_dir}/{problem_id}_test_case'
        tester_trace_path = f'{run_result_dir}/{problem_id}_tester_trace.json'
        if os.path.exists(test_case_path):
            with open(test_case_path, 'r', encoding='utf-8') as test_case_file:
                generated_test_cases = json.load(test_case_file)
        else:
            tester_result = tester_workflow.generate(
                TestGenerationRequest(
                    specification=ori_specification,
                    public_test_cases=public_test_cases,
                    problem_id=problem_id,
                )
            )
            generated_test_cases = tester_result.test_cases
            os.makedirs(os.path.dirname(test_case_path), exist_ok=True)
            with open(test_case_path, 'w', encoding='utf-8') as test_case_file:
                json.dump(generated_test_cases, test_case_file, ensure_ascii=False)
            save_workflow_trace(tester_trace_path, tester_result.to_dict())

        _, ori_test_result = evaluate_code(
            public_test_cases,
            ori_code,
            debug=args.debug,
        )
        if len(generated_test_cases["inputs"]):
            _, ori_test_result2 = evaluate_code(
                generated_test_cases,
                ori_code,
                debug=args.debug,
            )
        else:
            ori_test_result2 = 0.0

        best_specification, best_code, best_test_result, best_test_result2, best_test_result_all = ori_specification, ori_code, ori_test_result, ori_test_result2, ori_test_result_all
        best_coder_trace = initial_coder_trace
        best_optimization = 'None'
        optimization_list = []
        cache_list = {}
        for iter_n in range(args.max_iter):
            if os.path.exists(f'{run_result_dir}/{problem_id}_prompt_{iter_n}') and \
                os.path.exists(f'{run_result_dir}/{problem_id}_code_{iter_n}') and \
                os.path.exists(f'{run_result_dir}/{problem_id}_test_result_{iter_n}') and \
                os.path.exists(f'{run_result_dir}/{problem_id}_optimization_{iter_n}'):
                new_optimization = open(f'{run_result_dir}/{problem_id}_optimization_{iter_n}', 'r', encoding='utf-8').read()
                optimization_list.append(new_optimization)
                new_specification = open(f'{run_result_dir}/{problem_id}_prompt_{iter_n}', 'r', encoding='utf-8').read()
                new_code = open(f'{run_result_dir}/{problem_id}_code_{iter_n}', 'r', encoding='utf-8').read()
                new_test_result_all = float(open(f'{run_result_dir}/{problem_id}_test_result_{iter_n}', 'r', encoding='utf-8').read())
                coder_trace_path = f'{run_result_dir}/{problem_id}_coder_trace_{iter_n}.json'
                new_coder_trace = load_coder_trace(coder_trace_path)
                new_code = sanitize_code(new_code, ["```python", "```"])
                _, new_test_result = evaluate_code(
                    public_test_cases,
                    new_code,
                    debug=args.debug,
                )
                if len(generated_test_cases["inputs"]):
                    _, new_test_result2 = evaluate_code(
                        generated_test_cases,
                        new_code,
                        debug=args.debug,
                    )
                else:
                    new_test_result2 = 0.0

                print(f"        >> Iter={iter_n} [id={problem_id}](hierarchical criteria): {round(best_test_result * 100, 2)}%({round(best_test_result2 * 100, 2)}%) ==> {round(new_test_result * 100, 2)}%({round(new_test_result2 * 100, 2)}%)")
                if best_test_result < new_test_result:
                    best_specification = new_specification
                    best_code = new_code
                    best_test_result = new_test_result
                    best_test_result2 = new_test_result2
                    best_test_result_all = new_test_result_all
                    best_coder_trace = new_coder_trace
                    new_test_results[iter_n][problem_id] = best_test_result_all
                elif best_test_result == new_test_result and best_test_result2 < new_test_result2:
                    best_specification = new_specification
                    best_code = new_code
                    best_test_result = new_test_result
                    best_test_result2 = new_test_result2
                    best_test_result_all = new_test_result_all
                    best_coder_trace = new_coder_trace
                    new_test_results[iter_n][problem_id] = best_test_result_all
                else:
                    new_test_results[iter_n][problem_id] = best_test_result_all
            else:
                new_specification, new_code, new_test_result, new_optimization, cache_list, new_coder_trace = \
                    alignment_rule(args, problem_id, best_specification, best_code, best_test_result, public_test_cases,
                                  coder_workflow, optimization_list, cache_list, iter_n, tracked_generate)
                optimization_list.append(new_optimization)
                new_code = sanitize_code(new_code, ["```python", "```"])
                if len(generated_test_cases["inputs"]):
                    _, new_test_result2 = evaluate_code(
                        generated_test_cases,
                        new_code,
                        debug=args.debug,
                    )
                else:
                    new_test_result2 = 0.0
                _, new_test_result_all = evaluate_code(
                    all_test_cases,
                    new_code,
                    debug=args.debug,
                )

                print(f"        >> Iter={iter_n} [id={problem_id}](hierarchical criteria): {round(best_test_result * 100, 2)}%({round(best_test_result2 * 100, 2)}%) ==> {round(new_test_result * 100, 2)}%({round(new_test_result2 * 100, 2)}%)")
                if best_test_result < new_test_result:
                    best_optimization = new_optimization
                    best_specification = new_specification
                    best_code = new_code
                    best_test_result = new_test_result
                    best_test_result2 = new_test_result2
                    best_test_result_all = new_test_result_all
                    best_coder_trace = new_coder_trace
                    new_test_results[iter_n][problem_id] = new_test_result_all
                elif best_test_result == new_test_result and best_test_result2 < new_test_result2:
                    best_optimization = new_optimization
                    best_specification = new_specification
                    best_code = new_code
                    best_test_result = new_test_result
                    best_test_result2 = new_test_result2
                    best_test_result_all = new_test_result_all
                    best_coder_trace = new_coder_trace
                    new_test_results[iter_n][problem_id] = new_test_result_all
                else:
                    new_test_results[iter_n][problem_id] = best_test_result_all

                if best_test_result == 1.0 and best_test_result2 == 1.0:
                    for temp_iter_n in range(iter_n, args.max_iter):
                        if not os.path.exists(run_result_dir):
                            os.makedirs(run_result_dir)
                        open(f'{run_result_dir}/{problem_id}_prompt_{temp_iter_n}', 'w', encoding='utf-8').write(best_specification)
                        open(f'{run_result_dir}/{problem_id}_code_{temp_iter_n}', 'w', encoding='utf-8').write(best_code)
                        open(f'{run_result_dir}/{problem_id}_test_result_{temp_iter_n}', 'w', encoding='utf-8').write(str(best_test_result_all))
                        open(f'{run_result_dir}/{problem_id}_optimization_{temp_iter_n}', 'w', encoding='utf-8').write(optimization_list[-1])
                        save_workflow_trace(
                            f'{run_result_dir}/{problem_id}_coder_trace_{temp_iter_n}.json',
                            best_coder_trace,
                        )
                        new_test_results[temp_iter_n][problem_id] = best_test_result_all
                        print(f"        >> Iter={temp_iter_n} [id={problem_id}](hierarchical criteria): {round(best_test_result * 100, 2)}%({round(best_test_result2 * 100, 2)}%) ==> {round(new_test_result * 100, 2)}%({round(new_test_result2 * 100, 2)}%)")
                    break
                else:
                    if not os.path.exists(run_result_dir):
                        os.makedirs(run_result_dir)
                    open(f'{run_result_dir}/{problem_id}_prompt_{iter_n}', 'w', encoding='utf-8').write(best_specification)
                    open(f'{run_result_dir}/{problem_id}_code_{iter_n}', 'w', encoding='utf-8').write(best_code)
                    open(f'{run_result_dir}/{problem_id}_test_result_{iter_n}', 'w', encoding='utf-8').write(str(best_test_result_all))
                    open(f'{run_result_dir}/{problem_id}_optimization_{iter_n}', 'w', encoding='utf-8').write(optimization_list[-1])
                    save_workflow_trace(
                        f'{run_result_dir}/{problem_id}_coder_trace_{iter_n}.json',
                        best_coder_trace,
                    )

        print('*' * 40)
        for iter_n in range(args.max_iter):
            new_pass1 = round(list(new_test_results[iter_n].values()).count(1.0) / len(new_test_results[0]) * 100, 2)
            new_apr = round(np.average(list(new_test_results[iter_n].values())) * 100, 2)
            print(f">> ({args.model_name}, {args.data_name}-{index + 1}/{len(test_data)}, iter={iter_n})        Pass@1: {new_pass1}%, AvgPassRatio: {new_apr}%")
        print('*' * 40)

    print(f"Token usage events: {token_usage_recorder.events_path}")
    print(f"Token usage summary: {token_usage_recorder.summary_path}")


if __name__ == '__main__':
    alignment()
