from dataclasses import dataclass
from enum import Enum


class ArchitectureVariant(str, Enum):
    BASE = "base"
    METAGPT_CODER = "A"
    METAGPT_TESTER = "B"
    METAGPT_CODER_TESTER_SKILL = "C"
    METAGPT_CODER_AND_TESTER = "D"
    TESTER_SKILL = "E"
    FULL = "F"

    # Backward-compatible name used by the original variant-A implementation.
    METAGPT = "A"


@dataclass(frozen=True)
class VariantCapabilities:
    metagpt_coder: bool = False
    metagpt_tester: bool = False
    tester_skill: bool = False


VARIANT_CAPABILITIES = {
    ArchitectureVariant.BASE: VariantCapabilities(),
    ArchitectureVariant.METAGPT_CODER: VariantCapabilities(metagpt_coder=True),
    ArchitectureVariant.METAGPT_TESTER: VariantCapabilities(metagpt_tester=True),
    ArchitectureVariant.METAGPT_CODER_TESTER_SKILL: VariantCapabilities(
        metagpt_coder=True,
        tester_skill=True,
    ),
    ArchitectureVariant.METAGPT_CODER_AND_TESTER: VariantCapabilities(
        metagpt_coder=True,
        metagpt_tester=True,
    ),
    ArchitectureVariant.TESTER_SKILL: VariantCapabilities(tester_skill=True),
    ArchitectureVariant.FULL: VariantCapabilities(
        metagpt_coder=True,
        metagpt_tester=True,
        tester_skill=True,
    ),
}


def get_variant_capabilities(
    variant: ArchitectureVariant,
) -> VariantCapabilities:
    return VARIANT_CAPABILITIES[variant]


def initial_code_cache_name(capabilities: VariantCapabilities) -> str:
    """Share initial code only between variants with the same Coder workflow."""

    return "test_A" if capabilities.metagpt_coder else "test"
