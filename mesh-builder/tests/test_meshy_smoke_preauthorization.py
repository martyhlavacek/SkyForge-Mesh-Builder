from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.reconstruction_v1.preflight import preflight_artifact_url
from app.reconstruction_v1.provider import (
    ARTIFACT_HOST_CONTRACT_VERSION,
    DEFAULT_ARTIFACT_HOST_POLICY,
    ArtifactHostPolicy,
    ProviderError,
    operating_system_address_resolver,
)


class Response:
    def __init__(self, status_code=200, *, headers=None, url=None):
        self.status_code = status_code
        self.headers = headers or {}
        self.url = url


class HeadOnlyTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        assert method == "HEAD"
        assert kwargs == {"allow_redirects": False}
        return self.responses.pop(0)


def policy(*addresses):
    return ArtifactHostPolicy(
        contract_version=ARTIFACT_HOST_CONTRACT_VERSION,
        approved_hosts=frozenset({"assets.meshy.ai"}),
        address_resolver=lambda _hostname: tuple(addresses),
    )


def test_production_policy_is_exact_and_uses_os_resolver():
    assert DEFAULT_ARTIFACT_HOST_POLICY.approved_hosts == frozenset({"assets.meshy.ai"})
    assert DEFAULT_ARTIFACT_HOST_POLICY.address_resolver is operating_system_address_resolver


def test_approved_host_requires_only_global_addresses():
    assert policy("8.8.8.8", "2606:4700:4700::1111").validate("https://assets.meshy.ai/model.glb")


@pytest.mark.parametrize(
    "hostname",
    ["api.meshy.ai", "evil.example", "sub.assets.meshy.ai", "assets.meshy.ai.evil.example", "evilassets.meshy.ai"],
)
def test_every_other_or_deceptive_hostname_is_rejected(hostname):
    with pytest.raises(ProviderError, match="not approved"):
        policy("8.8.8.8").validate(f"https://{hostname}/model.glb")


@pytest.mark.parametrize(
    "addresses",
    [
        ("10.0.0.1",),
        ("127.0.0.1",),
        ("169.254.1.1",),
        ("192.0.2.1",),
        ("8.8.8.8", "10.0.0.1"),
        (),
    ],
)
def test_non_global_empty_and_mixed_dns_results_fail_closed(addresses):
    with pytest.raises(ProviderError):
        policy(*addresses).validate("https://assets.meshy.ai/model.glb")


def test_missing_resolver_fails_closed():
    without_resolver = ArtifactHostPolicy(ARTIFACT_HOST_CONTRACT_VERSION, frozenset({"assets.meshy.ai"}))
    with pytest.raises(ProviderError, match="unavailable"):
        without_resolver.validate("https://assets.meshy.ai/model.glb")


def test_unknown_redirect_is_recorded_and_refused_without_following():
    transport = HeadOnlyTransport(
        [Response(302, headers={"Location": "https://unknown.example/object.glb?signature=secret"})]
    )
    report = preflight_artifact_url(
        "https://assets.meshy.ai/model.glb?token=secret", policy=policy("8.8.8.8"), transport=transport
    )
    assert report["finalDecision"] == "REFUSE"
    assert report["redirects"] == [
        {"hostname": "unknown.example", "path": "/object.glb", "queryRedacted": True, "approved": False}
    ]
    assert len(transport.calls) == 1
    assert "secret" not in json.dumps(report)


def test_same_host_relative_redirect_and_final_url_are_checked():
    transport = HeadOnlyTransport(
        [
            Response(302, headers={"Location": "/next.glb?signed=secret"}),
            Response(200, url="https://assets.meshy.ai/final.glb?other=secret"),
        ]
    )
    report = preflight_artifact_url(
        "https://assets.meshy.ai/model.glb?token=secret", policy=policy("8.8.8.8"), transport=transport
    )
    assert report["finalDecision"] == "ALLOW"
    assert report["redirectPresent"] is True
    assert [call[0] for call in transport.calls] == ["HEAD", "HEAD"]
    assert "secret" not in json.dumps(report)


def test_final_response_url_escape_is_refused():
    transport = HeadOnlyTransport([Response(200, url="https://unknown.example/final.glb")])
    report = preflight_artifact_url(
        "https://assets.meshy.ai/model.glb", policy=policy("8.8.8.8"), transport=transport
    )
    assert report["finalDecision"] == "REFUSE"


def test_non_global_dns_is_safely_reported_and_non_success_head_is_refused():
    dns_report = preflight_artifact_url("https://assets.meshy.ai/model.glb", policy=policy("10.0.0.1"))
    assert dns_report["dnsResults"] == ["10.0.0.1"]
    assert dns_report["everyAddressGloballyRoutable"] is False
    assert dns_report["finalDecision"] == "REFUSE"
    status_report = preflight_artifact_url(
        "https://assets.meshy.ai/model.glb",
        policy=policy("8.8.8.8"),
        transport=HeadOnlyTransport([Response(404)]),
    )
    assert status_report["responseStatus"] == 404
    assert status_report["finalDecision"] == "REFUSE"


def test_offline_preflight_uses_no_key_and_performs_no_http():
    transport = HeadOnlyTransport([])
    report = preflight_artifact_url("https://assets.meshy.ai/model.glb?key=never-read", policy=policy("8.8.8.8"))
    assert report["finalDecision"] == "ALLOW"
    assert report["responseStatus"] is None
    assert "never-read" not in json.dumps(report)
    assert transport.calls == []


def test_request_preview_is_explicitly_no_spend_and_bundle_missing():
    preview = json.loads(
        (Path(__file__).parents[2] / "docs" / "testing" / "V0.8.1_MESHY_SMOKE_DRY_RUN_PREVIEW.json").read_text()
    )
    assert preview["bundleStatus"] == "HUMAN_APPROVED_TOP_FRONT_RIGHT_BUNDLE_NOT_AVAILABLE"
    assert preview["paidOperationPerformed"] is False
    assert preview["providerTaskId"] is None
    assert preview["maximumCredits"] == preview["estimatedCredits"] == 20
    assert preview["request"]["image_urls"] == [
        "<redacted-data-uri-top-not-available>",
        "<redacted-data-uri-front-not-available>",
        "<redacted-data-uri-right-not-available>",
    ]
