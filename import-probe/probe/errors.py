from __future__ import annotations


class ProbeReject(ValueError):
    """Structured fail-closed import rejection."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
