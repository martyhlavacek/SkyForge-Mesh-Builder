from __future__ import annotations

import socket

import pytest


def test_core_test_suite_blocks_real_network():
    with pytest.raises(RuntimeError, match="Real network access is prohibited"):
        socket.create_connection(("127.0.0.1", 1), timeout=0.01)
    sock = socket.socket()
    try:
        with pytest.raises(RuntimeError, match="Real network access is prohibited"):
            sock.connect(("127.0.0.1", 1))
    finally:
        sock.close()
