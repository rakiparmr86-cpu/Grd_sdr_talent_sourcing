from __future__ import annotations

from grd.config import Settings
from grd.enrichment.base import (
    IMPORTANT_FIELDS,
    EnrichmentProvider,
    assemble_profile,
    recompute_completeness,
)
from grd.enrichment.capabilities import ALL_CAPABILITIES, CapabilityResult, Fact
from grd.enrichment.mock import MockEnrichmentProvider
from grd.enrichment.web import WebEnrichmentProvider


def build_providers(settings: Settings) -> list[EnrichmentProvider]:
    providers: list[EnrichmentProvider] = []
    for name in settings.provider_list:
        if name == "mock":
            providers.append(MockEnrichmentProvider())
        elif name == "web":
            providers.append(WebEnrichmentProvider(timeout=settings.http_timeout))
        else:
            raise ValueError(f"Unknown enrichment provider: {name!r}")
    if not providers:
        raise ValueError("GRD_ENRICHMENT_PROVIDERS resolved to an empty list")
    return providers


__all__ = [
    "ALL_CAPABILITIES",
    "CapabilityResult",
    "EnrichmentProvider",
    "Fact",
    "IMPORTANT_FIELDS",
    "MockEnrichmentProvider",
    "WebEnrichmentProvider",
    "assemble_profile",
    "build_providers",
    "recompute_completeness",
]
