from __future__ import annotations

import hashlib
import importlib.metadata

import pytest

from common.canonical_json import (
    JCS_VERSION,
    CanonicalizationUnavailable,
    canonical_sha256,
    canonicalize,
)


def test_exact_rfc8785_distribution_executes_documented_canonicalization_vector():
    assert importlib.metadata.version("rfc8785") == JCS_VERSION
    value = {
        "key": "value",
        "another-key": 2,
        "a-third": [1, 2, 3, [4], (5, 6, "this works too")],
        "more": [None, True, False],
    }
    expected = (
        b'{"a-third":[1,2,3,[4],[5,6,"this works too"]],'
        b'"another-key":2,"key":"value","more":[null,true,false]}'
    )
    assert canonicalize(value) == expected
    assert canonical_sha256(value) == hashlib.sha256(expected).hexdigest()


def test_canonicalization_fails_closed_when_implementation_is_unavailable(monkeypatch):
    def missing(_name: str):
        raise ModuleNotFoundError("forced missing dependency")

    monkeypatch.setattr("common.canonical_json.importlib.import_module", missing)
    with pytest.raises(CanonicalizationUnavailable, match="rfc8785==0.1.4"):
        canonicalize({"value": 1})
