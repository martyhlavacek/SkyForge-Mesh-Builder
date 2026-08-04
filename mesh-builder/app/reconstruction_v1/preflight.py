from __future__ import annotations

from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

from .provider import REDIRECT_STATUSES, ArtifactHostPolicy, ProviderError

MAXIMUM_REDIRECTS = 4


def redact_url(url: str) -> str:
    try:
        parsed = urlsplit(url)
    except ValueError:
        return "<malformed-url-redacted>"
    query = "<redacted>" if parsed.query else ""
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, query, ""))


def redirect_metadata(url: str) -> dict[str, Any]:
    parsed = urlsplit(url)
    return {
        "hostname": parsed.hostname.lower() if parsed.hostname else None,
        "path": parsed.path,
        "queryRedacted": bool(parsed.query),
    }


def preflight_artifact_url(
    url: str,
    *,
    policy: ArtifactHostPolicy,
    transport: Any | None = None,
    maximum_redirects: int = MAXIMUM_REDIRECTS,
) -> dict[str, Any]:
    """Validate an artifact URL and optional HEAD-only redirect chain without reading bytes."""
    report: dict[str, Any] = {
        "policyContractVersion": policy.contract_version,
        "redactedUrl": redact_url(url),
        "responseStatus": None,
        "redirectPresent": False,
        "redirects": [],
        "finalDecision": "REFUSE",
    }
    try:
        inspected = policy.inspect(url)
        report.update(
            scheme=inspected["scheme"],
            hostname=inspected["hostname"],
            dnsResults=inspected["addresses"],
            everyAddressGloballyRoutable=inspected["allAddressesGloballyRoutable"],
        )
        if transport is None:
            report["finalDecision"] = "ALLOW"
            return report
        if maximum_redirects < 0:
            raise ProviderError("Artifact preflight redirect limit must not be negative")
        current = url
        for redirect_count in range(maximum_redirects + 1):
            response = transport.request("HEAD", current, allow_redirects=False)
            response_url = getattr(response, "url", None)
            if response_url:
                policy.validate(response_url)
            report["responseStatus"] = response.status_code
            if response.status_code not in REDIRECT_STATUSES:
                if 200 <= response.status_code < 300:
                    report["finalDecision"] = "ALLOW"
                else:
                    report["refusalReason"] = f"Artifact preflight HEAD returned HTTP {response.status_code}"
                return report
            report["redirectPresent"] = True
            location = (getattr(response, "headers", None) or {}).get("Location")
            if not location:
                raise ProviderError("Provider artifact redirect omitted Location")
            target = urljoin(current, location)
            metadata = redirect_metadata(target)
            try:
                policy.validate(target)
            except ProviderError:
                metadata["approved"] = False
                report["redirects"].append(metadata)
                raise
            metadata["approved"] = True
            report["redirects"].append(metadata)
            current = target
            if redirect_count == maximum_redirects:
                raise ProviderError("Artifact preflight redirect limit exceeded")
    except ProviderError as exc:
        if exc.details:
            report["dnsResults"] = exc.details.get("addresses")
            report["everyAddressGloballyRoutable"] = exc.details.get("allAddressesGloballyRoutable")
        report["refusalReason"] = str(exc)
        return report
    return report
