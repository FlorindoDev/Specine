from dataclasses import dataclass
from enum import Enum


class ArchitectureVariant(str, Enum):
    BASE = "base"
    CUSTOM_CODER = "A"
    CUSTOM_TESTER = "B"
    CUSTOM_CODER_AND_TESTER = "D"


@dataclass(frozen=True)
class VariantCapabilities:
    custom_coder: bool = False
    custom_tester: bool = False


VARIANT_CAPABILITIES = {
    ArchitectureVariant.BASE: VariantCapabilities(),
    ArchitectureVariant.CUSTOM_CODER: VariantCapabilities(custom_coder=True),
    ArchitectureVariant.CUSTOM_TESTER: VariantCapabilities(custom_tester=True),
    ArchitectureVariant.CUSTOM_CODER_AND_TESTER: VariantCapabilities(
        custom_coder=True,
        custom_tester=True,
    ),
}


def get_variant_capabilities(
    variant: ArchitectureVariant,
) -> VariantCapabilities:
    return VARIANT_CAPABILITIES[variant]


def initial_code_cache_name(capabilities: VariantCapabilities) -> str:
    """Share initial code only between variants with the same Coder workflow."""

    return "test_A" if capabilities.custom_coder else "test"
