from __future__ import annotations

import socket
import sys
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))


@pytest.fixture(autouse=True)
def deny_real_network(monkeypatch: pytest.MonkeyPatch):
    """Core pytest suites are offline; transport tests must use injected fake sessions."""

    def blocked(*_args, **_kwargs):
        raise RuntimeError("Real network access is prohibited in the core test suite")

    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)
