from __future__ import annotations

from abc import ABC, abstractmethod

from .models import ProviderCapabilities, ProviderCapture, ProviderRequest


class MeshProvider(ABC):
    @property
    @abstractmethod
    def capabilities(self) -> ProviderCapabilities:
        raise NotImplementedError

    @abstractmethod
    def execute(self, request: ProviderRequest) -> ProviderCapture:
        raise NotImplementedError
