import unittest

from coder_workflow import (
    CodeGenerationRequest,
    MetaGPTCoderWorkflow,
    create_coder_workflow,
)
from tester_skill import DEFAULT_TESTER_SKILL, TesterSkill
from tester_workflow import (
    DirectTesterWorkflow,
    MetaGPTTesterWorkflow,
    TestGenerationRequest,
    create_tester_workflow,
    parse_test_cases,
)
from workflow_variants import (
    ArchitectureVariant,
    get_variant_capabilities,
    initial_code_cache_name,
)


class RecordingGenerator:
    def __init__(self, responses):
        self._responses = iter(responses)
        self.calls = []

    def __call__(self, prompt, max_tokens, context):
        self.calls.append((prompt, max_tokens, context))
        return next(self._responses)


class VariantConfigurationTests(unittest.TestCase):
    def test_variants_match_thesis_architecture(self):
        expected = {
            ArchitectureVariant.BASE: (False, False, False),
            ArchitectureVariant.METAGPT_CODER: (True, False, False),
            ArchitectureVariant.METAGPT_TESTER: (False, True, False),
            ArchitectureVariant.METAGPT_CODER_TESTER_SKILL: (True, False, True),
            ArchitectureVariant.METAGPT_CODER_AND_TESTER: (True, True, False),
            ArchitectureVariant.TESTER_SKILL: (False, False, True),
            ArchitectureVariant.FULL: (True, True, True),
        }

        for variant, capability_tuple in expected.items():
            with self.subTest(variant=variant.value):
                capabilities = get_variant_capabilities(variant)
                self.assertEqual(
                    (
                        capabilities.metagpt_coder,
                        capabilities.metagpt_tester,
                        capabilities.tester_skill,
                    ),
                    capability_tuple,
                )

    def test_variants_share_code_cache_by_coder_workflow(self):
        direct_variants = (
            ArchitectureVariant.BASE,
            ArchitectureVariant.METAGPT_TESTER,
            ArchitectureVariant.TESTER_SKILL,
        )
        metagpt_variants = (
            ArchitectureVariant.METAGPT_CODER,
            ArchitectureVariant.METAGPT_CODER_TESTER_SKILL,
            ArchitectureVariant.METAGPT_CODER_AND_TESTER,
            ArchitectureVariant.FULL,
        )

        for variant in direct_variants:
            self.assertEqual(
                initial_code_cache_name(get_variant_capabilities(variant)),
                "test",
            )
        for variant in metagpt_variants:
            self.assertEqual(
                initial_code_cache_name(get_variant_capabilities(variant)),
                "test_A",
            )

    def test_variants_b_through_f_compose_runnable_workflows(self):
        expected = {
            ArchitectureVariant.METAGPT_TESTER: ("direct", "metagpt", None),
            ArchitectureVariant.METAGPT_CODER_TESTER_SKILL: (
                "metagpt",
                "direct",
                "default",
            ),
            ArchitectureVariant.METAGPT_CODER_AND_TESTER: (
                "metagpt",
                "metagpt",
                None,
            ),
            ArchitectureVariant.TESTER_SKILL: ("direct", "direct", "default"),
            ArchitectureVariant.FULL: ("metagpt", "metagpt", "default"),
        }
        code_request = CodeGenerationRequest(
            specification="Add two integers.",
            code_prompt="Return Python code.",
            problem_id="composition",
            iteration=None,
            stage="initial_code",
        )
        test_request = TestGenerationRequest(
            specification="Add two integers.",
            public_test_cases={"inputs": ["1 2\n"], "outputs": ["3\n"]},
            problem_id="composition",
        )

        for variant, expected_result in expected.items():
            with self.subTest(variant=variant.value):
                capabilities = get_variant_capabilities(variant)
                coder_generator = RecordingGenerator(["artifact"] * 4)
                tester_generator = RecordingGenerator([
                    "analysis",
                    "design",
                    '{"inputs": ["2 3\\n"], "outputs": ["5\\n"]}',
                    '{"inputs": ["2 3\\n"], "outputs": ["5\\n"]}',
                ])
                skill = (
                    DEFAULT_TESTER_SKILL
                    if capabilities.tester_skill
                    else None
                )
                coder = create_coder_workflow(variant, coder_generator)
                tester = create_tester_workflow(
                    capabilities.metagpt_tester,
                    tester_generator,
                    skill,
                )

                coder_result = coder.generate(code_request)
                tester_result = tester.generate(test_request)

                self.assertEqual(
                    (
                        coder_result.workflow,
                        tester_result.workflow,
                        tester_result.skill,
                    ),
                    expected_result,
                )


class MetaGPTCoderWorkflowTests(unittest.TestCase):
    def test_variant_a_keeps_four_role_sequence(self):
        generator = RecordingGenerator(["prd", "architecture", "tasks", "```python\npass\n```"])
        workflow = MetaGPTCoderWorkflow(generator)

        result = workflow.generate(
            CodeGenerationRequest(
                specification="specification",
                code_prompt="code prompt",
                problem_id=7,
                iteration=None,
                stage="initial_code",
            )
        )

        self.assertEqual(result.workflow, "metagpt")
        self.assertEqual(
            [call[2].agent for call in generator.calls],
            ["Product Manager", "Architect", "Project Manager", "Engineer"],
        )
        self.assertEqual([artifact.role for artifact in result.artifacts], [
            "Product Manager",
            "Architect",
            "Project Manager",
            "Engineer",
        ])


class TesterWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.request = TestGenerationRequest(
            specification="#PROGRAMMING SPECIFICATION:\nAdd two integers.",
            public_test_cases={"inputs": ["1 2\n"], "outputs": ["3\n"]},
            problem_id=11,
        )

    def test_direct_workflow_generates_and_parses_tests(self):
        generator = RecordingGenerator([
            '```json\n{"inputs": ["2 3\\n"], "outputs": ["5\\n"]}\n```'
        ])

        result = DirectTesterWorkflow(generator).generate(self.request)

        self.assertEqual(result.workflow, "direct")
        self.assertEqual(result.test_cases, {
            "inputs": ["2 3\n"],
            "outputs": ["5\n"],
        })
        self.assertEqual(generator.calls[0][2].stage, "generated_tests")
        self.assertIn("#TEST CASES:", generator.calls[0][0])
        self.assertIn(
            "(1) To verify the fundamental functionality",
            generator.calls[0][0],
        )
        self.assertNotIn("#TESTER SKILL", generator.calls[0][0])

    def test_direct_workflow_keeps_original_prompt_exactly(self):
        generator = RecordingGenerator(['{"inputs": [], "outputs": []}'])

        DirectTesterWorkflow(generator).generate(self.request)

        expected_prompt = (
            "#PROGRAMMING SPECIFICATION:\nAdd two integers."
            "\n\n#TEST CASES:\n```json\n"
            '{"inputs": ["1 2\\n"], "outputs": ["3\\n"]}'
            "\n```"
            "\n\n#INSTRUCTION:\n"
            "Implement a representative set of test cases for the above programming "
            "specification, ensure that the generated test cases are correct:\n"
            "(1) To verify the fundamental functionality of the programming "
            "specification under normal conditions.\n"
            "(2) To evaluate the function's behavior under extreme or unusual "
            "conditions.\n"
            "(3) To assess the function's performance and scalability with large "
            "data samples.\n"
            "Please only provide additional test cases in a json format "
            "(Response constraints: Max 1000 words, NO code and text):\n"
            "e.g.,\n```json\n"
            '{"inputs": ["x1\\n", "x2\\n", "x3\\n", "x4\\n", "x5\\n", '
            '"x6\\n"], "outputs": ["y1\\n", "y2\\n", "y3\\n", y4\\n", '
            '"y5\\n", "y6\\n"]}\n```'
        )
        self.assertEqual(generator.calls[0][0], expected_prompt)

    def test_direct_workflow_injects_custom_skill(self):
        skill = TesterSkill("custom", ("Target integer overflow.",))
        generator = RecordingGenerator(['{"inputs": [], "outputs": []}'])

        result = DirectTesterWorkflow(generator, skill).generate(self.request)

        self.assertEqual(result.skill, "custom")
        self.assertIn("#TESTER SKILL (custom):", generator.calls[0][0])
        self.assertIn("Target integer overflow.", generator.calls[0][0])

    def test_metagpt_workflow_runs_all_roles_and_uses_reviewed_tests(self):
        generator = RecordingGenerator([
            "analysis",
            "design",
            '{"inputs": ["2 2\\n"], "outputs": ["4\\n"]}',
            '{"inputs": ["0 0\\n"], "outputs": ["0\\n"]}',
        ])

        result = MetaGPTTesterWorkflow(generator).generate(self.request)

        self.assertEqual(result.workflow, "metagpt")
        self.assertEqual(result.test_cases["inputs"], ["0 0\n"])
        self.assertEqual(
            [call[2].agent for call in generator.calls],
            [
                "Test Analyst",
                "Test Designer",
                "Test Generator",
                "Test Reviewer / Validator",
            ],
        )
        self.assertIn("#TEST GENERATOR OUTPUT:", generator.calls[3][0])

    def test_metagpt_workflow_falls_back_when_review_is_invalid(self):
        generator = RecordingGenerator([
            "analysis",
            "design",
            '{"inputs": ["4 5\\n"], "outputs": ["9\\n"]}',
            "invalid review",
        ])

        result = MetaGPTTesterWorkflow(generator, DEFAULT_TESTER_SKILL).generate(
            self.request
        )

        self.assertEqual(result.test_cases["outputs"], ["9\n"])
        self.assertEqual(result.skill, "default")
        self.assertTrue(all(
            "#TESTER SKILL (default):" in call[0]
            for call in generator.calls
        ))

    def test_legacy_direct_workflow_does_not_add_function_name(self):
        request = TestGenerationRequest(
            specification="Return the sum.",
            public_test_cases={
                "fn_name": "add",
                "inputs": [[1, 2]],
                "outputs": [3],
            },
            problem_id="call-based",
        )
        generator = RecordingGenerator([
            '{"inputs": [[3, 4]], "outputs": [7]}'
        ])

        result = DirectTesterWorkflow(generator).generate(request)

        self.assertNotIn("fn_name", result.test_cases)

    def test_skill_workflow_preserves_call_based_function_name(self):
        request = TestGenerationRequest(
            specification="Return the sum.",
            public_test_cases={
                "fn_name": "add",
                "inputs": [[1, 2]],
                "outputs": [3],
            },
            problem_id="call-based-skill",
        )
        generator = RecordingGenerator([
            '{"inputs": [[3, 4]], "outputs": [7]}'
        ])

        result = DirectTesterWorkflow(generator, DEFAULT_TESTER_SKILL).generate(
            request
        )

        self.assertEqual(result.test_cases["fn_name"], "add")

    def test_parser_rejects_mismatched_arrays(self):
        parsed = parse_test_cases(
            '{"inputs": ["one"], "outputs": []}',
            function_name="solve",
        )

        self.assertEqual(parsed, {
            "inputs": [],
            "outputs": [],
            "fn_name": "solve",
        })

    def test_parser_accepts_nested_objects_in_fenced_json(self):
        parsed = parse_test_cases(
            '```json\n{"inputs": [[{"1": "value"}]], '
            '"outputs": [[{"1": "expected"}]]}\n```'
        )

        self.assertEqual(parsed["inputs"], [[{"1": "value"}]])


if __name__ == "__main__":
    unittest.main()
