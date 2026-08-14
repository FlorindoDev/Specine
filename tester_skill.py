from dataclasses import dataclass


@dataclass(frozen=True)
class TesterSkill:
    """Reusable instructions injected into a Tester Agent workflow."""

    name: str
    instructions: tuple[str, ...]

    def to_prompt(self) -> str:
        numbered_steps = "\n".join(
            f"{index}. {instruction}"
            for index, instruction in enumerate(self.instructions, start=1)
        )
        return (
            f"#TESTER SKILL ({self.name}):\n"
            "Apply every step while designing, generating, and validating tests.\n"
            f"{numbered_steps}"
        )


# Edit or replace this object to provide different instructions to variants C, E, and F.
DEFAULT_TESTER_SKILL = TesterSkill(
    name="default",
    instructions=(
        "Extract every functional requirement, input/output rule, and constraint.",
        "Create representative base cases and boundary cases.",
        "Create adversarial cases that target ambiguous wording and common "
        "implementation mistakes.",
        "Calculate each expected output from the specification, independently of generated code.",
        "Verify JSON structure, input/output pairing, requirement coverage, and "
        "expected outputs before returning tests.",
    ),
)
