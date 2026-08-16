import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol

from token_usage import GenerationContext
from sanitize import sanitize_code


TextGenerator = Callable[[str, int, GenerationContext], str]
TestCases = dict[str, Any]


@dataclass(frozen=True)
class TesterArtifact:
    role: str
    content: str


@dataclass(frozen=True)
class TestGenerationRequest:
    specification: str
    public_test_cases: Mapping[str, Any]
    problem_id: str | int
    iteration: int | None = None

    @property
    def function_name(self) -> str | None:
        value = self.public_test_cases.get("fn_name")
        return value if isinstance(value, str) and value else None


@dataclass(frozen=True)
class TestGenerationResult:
    workflow: str
    test_cases: TestCases
    artifacts: tuple[TesterArtifact, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow": self.workflow,
            "artifacts": [
                {"role": artifact.role, "content": artifact.content}
                for artifact in self.artifacts
            ],
        }


class TesterWorkflow(Protocol):
    def generate(self, request: TestGenerationRequest) -> TestGenerationResult:
        ...


class DirectTesterWorkflow:
    """Original single-agent Tester workflow."""

    _TEST_TOKEN_LIMIT = 1024

    def __init__(self, generate_text: TextGenerator):
        self._generate_text = generate_text

    def generate(self, request: TestGenerationRequest) -> TestGenerationResult:
        prompt = _build_direct_generation_prompt(request)
        response = self._generate_text(
            prompt,
            self._TEST_TOKEN_LIMIT,
            GenerationContext(
                agent="Tester Agent",
                stage="generated_tests",
                problem_id=request.problem_id,
                iteration=request.iteration,
            ),
        ) or ""
        test_cases = _parse_legacy_test_cases(response)
        return TestGenerationResult(
            workflow="direct",
            test_cases=test_cases,
            artifacts=(TesterArtifact("Tester Agent", response),),
        )


class CustomTesterWorkflow:
    """Custom four-role workflow for test analysis, design, generation, and review."""

    _ROLE_TOKEN_LIMIT = 512
    _TEST_TOKEN_LIMIT = 1024

    def __init__(self, generate_text: TextGenerator):
        self._generate_text = generate_text

    def generate(self, request: TestGenerationRequest) -> TestGenerationResult:
        artifacts: list[TesterArtifact] = []

        analysis = self._run_role(
            role="Test Analyst",
            stage="test_analysis",
            instruction=(
                "Interpret the specification. Extract all testable behavior, input/output "
                "formats, constraints, invariants, and ambiguities. Do not generate JSON tests."
            ),
            request=request,
            artifacts=artifacts,
        )
        artifacts.append(TesterArtifact("Test Analyst", analysis))

        design = self._run_role(
            role="Test Designer",
            stage="test_design",
            instruction=(
                "Design a concise test plan from the analysis. Define concrete normal, "
                "boundary, edge, and adversarial cases. State what requirement or likely "
                "implementation fault each case covers. Do not generate final JSON."
            ),
            request=request,
            artifacts=artifacts,
        )
        artifacts.append(TesterArtifact("Test Designer", design))

        generated = self._run_role(
            role="Test Generator",
            stage="test_generation",
            instruction=_json_test_instruction(),
            request=request,
            artifacts=artifacts,
            max_tokens=self._TEST_TOKEN_LIMIT,
        )
        artifacts.append(TesterArtifact("Test Generator", generated))

        reviewed = self._run_role(
            role="Test Reviewer / Validator",
            stage="test_review",
            instruction=(
                "Review every generated input and expected output against the original "
                "specification and test plan. Fix invalid, duplicate, uncovered, or incorrectly "
                "calculated cases. Return only the corrected JSON object with equally sized "
                '"inputs" and "outputs" arrays; no markdown or commentary.'
            ),
            request=request,
            artifacts=artifacts,
            max_tokens=self._TEST_TOKEN_LIMIT,
        )
        artifacts.append(TesterArtifact("Test Reviewer / Validator", reviewed))

        test_cases = parse_test_cases(reviewed, request.function_name)
        if not test_cases["inputs"]:
            test_cases = parse_test_cases(generated, request.function_name)

        return TestGenerationResult(
            workflow="custom",
            test_cases=test_cases,
            artifacts=tuple(artifacts),
        )

    def _run_role(
        self,
        role: str,
        stage: str,
        instruction: str,
        request: TestGenerationRequest,
        artifacts: list[TesterArtifact],
        max_tokens: int = _ROLE_TOKEN_LIMIT,
    ) -> str:
        prompt_parts = [
            f"#ROLE:\n{role}",
            _build_specification_context(request),
        ]
        prompt_parts.extend(
            f"#{artifact.role.upper()} OUTPUT:\n{artifact.content}"
            for artifact in artifacts
        )
        prompt_parts.append(f"#INSTRUCTION:\n{instruction}")
        return self._generate_text(
            "\n\n".join(prompt_parts),
            max_tokens,
            GenerationContext(
                agent=role,
                stage=stage,
                problem_id=request.problem_id,
                iteration=request.iteration,
            ),
        ) or ""


def create_tester_workflow(
    custom_tester: bool,
    generate_text: TextGenerator,
) -> TesterWorkflow:
    if custom_tester:
        return CustomTesterWorkflow(generate_text)
    return DirectTesterWorkflow(generate_text)


def parse_test_cases(
    response: str | Mapping[str, Any],
    function_name: str | None = None,
) -> TestCases:
    payload = _load_test_case_payload(response)
    if not isinstance(payload, Mapping):
        return _empty_test_cases(function_name)

    inputs = payload.get("inputs")
    outputs = payload.get("outputs")
    if not isinstance(inputs, list) or not isinstance(outputs, list):
        return _empty_test_cases(function_name)
    if len(inputs) != len(outputs):
        return _empty_test_cases(function_name)

    test_cases: TestCases = {"inputs": list(inputs), "outputs": list(outputs)}
    if function_name:
        test_cases["fn_name"] = function_name
    return test_cases


def _load_test_case_payload(
    response: str | Mapping[str, Any],
) -> Mapping[str, Any] | None:
    if isinstance(response, Mapping):
        return response

    candidate = response.strip()
    fenced_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", candidate, re.DOTALL)
    if fenced_match:
        candidate = fenced_match.group(1)
    elif "{" in candidate and "}" in candidate:
        candidate = candidate[candidate.find("{"):candidate.rfind("}") + 1]

    try:
        payload = json.loads(candidate)
    except (json.JSONDecodeError, TypeError):
        return None
    return payload if isinstance(payload, Mapping) else None


def _empty_test_cases(function_name: str | None = None) -> TestCases:
    test_cases: TestCases = {"inputs": [], "outputs": []}
    if function_name:
        test_cases["fn_name"] = function_name
    return test_cases


def _build_specification_context(request: TestGenerationRequest) -> str:
    parts = [request.specification]
    serialized_public_tests = json.dumps(request.public_test_cases)
    if len(serialized_public_tests) < 1024:
        parts.append(f"#PUBLIC TEST CASES:\n```json\n{serialized_public_tests}\n```")
    return "\n\n".join(parts)


def _build_direct_generation_prompt(request: TestGenerationRequest) -> str:
    prompt = request.specification
    serialized_public_tests = json.dumps(request.public_test_cases)
    includes_public_tests = len(serialized_public_tests) < 1024
    if includes_public_tests:
        prompt += f"\n\n#TEST CASES:\n```json\n{serialized_public_tests}\n```"

    instruction = _original_test_instruction(includes_public_tests)
    return f"{prompt}\n\n#INSTRUCTION:\n{instruction}"


def _parse_legacy_test_cases(response: str) -> TestCases:
    """Match original Specine parsing used by Base and variant A."""

    try:
        payload = json.loads(sanitize_code(response, ["```json", "```"]))
    except (json.JSONDecodeError, TypeError, AttributeError):
        return {"inputs": [], "outputs": []}

    if not isinstance(payload, Mapping):
        return {"inputs": [], "outputs": []}
    inputs = payload.get("inputs")
    outputs = payload.get("outputs")
    if type(inputs) is not list or type(outputs) is not list:
        return {"inputs": [], "outputs": []}
    if len(inputs) != len(outputs):
        return {"inputs": [], "outputs": []}
    return {"inputs": list(inputs), "outputs": list(outputs)}


def _original_test_instruction(includes_public_tests: bool) -> str:
    """Original Specine Tester prompt retained by Base and variant A."""

    possessive = "function's" if includes_public_tests else "function’s"
    return (
        "Implement a representative set of test cases for the above programming "
        "specification, ensure that the generated test cases are correct:\n"
        "(1) To verify the fundamental functionality of the programming specification "
        "under normal conditions.\n"
        "(2) To evaluate the function's behavior under extreme or unusual conditions.\n"
        f"(3) To assess the {possessive} performance and scalability with large data samples.\n"
        "Please only provide additional test cases in a json format "
        "(Response constraints: Max 1000 words, NO code and text):\n"
        "e.g.,\n"
        '```json\n{"inputs": ["x1\\n", "x2\\n", "x3\\n", "x4\\n", "x5\\n", '
        '"x6\\n"], "outputs": ["y1\\n", "y2\\n", "y3\\n", y4\\n", "y5\\n", '
        '"y6\\n"]}\n```'
    )


def _json_test_instruction() -> str:
    return (
        "Implement a representative set of additional test cases for the programming "
        "specification. Verify fundamental behavior under normal conditions, boundary and "
        "unusual conditions, adversarial cases, and performance with large inputs. Calculate "
        "each expected output only from the specification. Return only one JSON object with "
        'equally sized "inputs" and "outputs" arrays; no code, markdown, or commentary. '
        'Example: {"inputs": ["x1\\n", "x2\\n"], "outputs": ["y1\\n", "y2\\n"]}'
    )
