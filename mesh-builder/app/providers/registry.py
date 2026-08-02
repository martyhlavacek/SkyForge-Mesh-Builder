from __future__ import annotations

from .base import MeshProvider
from .local_deterministic import LocalDeterministicProvider
from .models import ProviderContractError


def resolve_provider(provider_id: str) -> MeshProvider:
    if provider_id == LocalDeterministicProvider.PROVIDER_ID:
        return LocalDeterministicProvider()
    raise ProviderContractError(f"Unsupported mesh provider: {provider_id!r}")
