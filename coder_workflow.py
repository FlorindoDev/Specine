from dataclasses import dataclass
from typing import Callable, Protocol

from token_usage import GenerationContext
from workflow_variants import (
    ArchitectureVariant,
    VariantCapabilities,
    get_variant_capabilities,
)


TextGenerator = Callable[[str, int, GenerationContext], str]


@dataclass(frozen=True)
class RoleArtifact:
    role: str
    content: str


@dataclass(frozen=True)
class CodeGenerationRequest:
    specification: str
    code_prompt: str
    problem_id: str | int
    iteration: int | None
    stage: str


@dataclass(frozen=True)
class CodeGenerationResult:
    workflow: str
    code: str
    artifacts: tuple[RoleArtifact, ...] = ()

    def to_dict(self):
        return {
            "workflow": self.workflow,
            "artifacts": [
                {"role": artifact.role, "content": artifact.content}
                for artifact in self.artifacts
            ],
        }


class CoderWorkflow(Protocol):
    def generate(self, request: CodeGenerationRequest) -> CodeGenerationResult:
        ...


class DirectCoderWorkflow:
    def __init__(self, generate_text: TextGenerator):
        self._generate_text = generate_text

    def generate(self, request: CodeGenerationRequest) -> CodeGenerationResult:
        context = GenerationContext(
            agent="Coder Agent",
            stage=request.stage,
            problem_id=request.problem_id,
            iteration=request.iteration,
        )
        code = self._generate_text(request.code_prompt, 1024, context)
        return CodeGenerationResult(workflow="direct", code=code or "")


class MetaGPTCoderWorkflow:
    """MetaGPT software-company SOP adapted to single-file code generation."""

    _ROLE_TOKEN_LIMIT = 512
    _CODE_TOKEN_LIMIT = 1024

    def __init__(self, generate_text: TextGenerator):
        self._generate_text = generate_text

    def generate(self, request: CodeGenerationRequest) -> CodeGenerationResult:
        artifacts = []

        prd = self._run_role(
            role="Product Manager",
            instruction=(
                "Analyze the programming specification and create a concise PRD. "
                "Identify the objective, functional requirements, input/output contract, "
                "constraints, acceptance criteria, and relevant edge cases. Do not write code."
            ),
            specification=request.specification,
            artifacts=artifacts,
            request=request,
        )
        artifacts.append(RoleArtifact("Product Manager", prd))

        architecture = self._run_role(
            role="Architect",
            instruction=(
                "Design the solution architecture for a self-contained Python program. "
                "Define the algorithm, data structures, components or functions, interfaces, "
                "complexity, and handling of constraints and edge cases. Do not write code."
            ),
            specification=request.specification,
            artifacts=artifacts,
            request=request,
        )
        artifacts.append(RoleArtifact("Architect", architecture))

        tasks = self._run_role(
            role="Project Manager",
            instruction=(
                "Turn the PRD and architecture into an ordered implementation plan for one "
                "self-contained Python script. Include verification steps and preserve every "
                "input/output and complexity requirement. Do not write code."
            ),
            specification=request.specification,
            artifacts=artifacts,
            request=request,
        )
        artifacts.append(RoleArtifact("Project Manager", tasks))

        code = self._run_role(
            role="Engineer",
            instruction=(
                "Implement the programming specification using the approved PRD, architecture, "
                "and task plan. Return only a self-contained Python solution in a markdown "
                "code block, without explanations or test cases."
            ),
            specification=request.specification,
            artifacts=artifacts,
            request=request,
            max_tokens=self._CODE_TOKEN_LIMIT,
        )
        artifacts.append(RoleArtifact("Engineer", code))

        return CodeGenerationResult(
            workflow="metagpt",
            code=code,
            artifacts=tuple(artifacts),
        )

    def _run_role(
        self,
        role: str,
        instruction: str,
        specification: str,
        artifacts: list[RoleArtifact],
        request: CodeGenerationRequest,
        max_tokens: int = _ROLE_TOKEN_LIMIT,
    ) -> str:
        context = "\n\n".join(
            f"#{artifact.role.upper()} OUTPUT:\n{artifact.content}"
            for artifact in artifacts
        )
        prompt_parts = [
            f"#ROLE:\n{role}",
            f"#PROGRAMMING SPECIFICATION:\n{specification}",
        ]
        if context:
            prompt_parts.append(context)
        prompt_parts.append(f"#INSTRUCTION:\n{instruction}")
        generation_context = GenerationContext(
            agent=role,
            stage=request.stage,
            problem_id=request.problem_id,
            iteration=request.iteration,
        )
        response = self._generate_text(
            "\n\n".join(prompt_parts),
            max_tokens,
            generation_context,
        )
        return response or ""


def create_coder_workflow(
    variant: ArchitectureVariant,
    generate_text: TextGenerator,
) -> CoderWorkflow:
    capabilities = validate_architecture_variant(variant)
    if capabilities.metagpt_coder:
        return MetaGPTCoderWorkflow(generate_text)
    return DirectCoderWorkflow(generate_text)


def validate_architecture_variant(
    variant: ArchitectureVariant,
) -> VariantCapabilities:
    return get_variant_capabilities(variant)
