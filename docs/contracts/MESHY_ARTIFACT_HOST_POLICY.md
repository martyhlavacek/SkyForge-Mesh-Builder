# Meshy Artifact Host Policy

Contract version: `skyforge.meshy-artifact-hosts.unverified.v1`.

The committed Meshy snapshot documents temporary model URLs but does not name their serving hostnames. Production therefore defaults to an empty approved-host set and cannot download a live artifact. This is intentionally fail-closed and must not be broadened by inference.

Immediately before any separately authorized live smoke task, re-verify the official Meshy endpoint, request parameters, `meshy-6` availability, asset-serving hostnames, redirect behavior, retention, and current 20-credit estimate. Configure only the exact verified artifact hostnames under a new or explicitly updated contract version.

The policy requires HTTPS, a hostname, no embedded credentials, no IP literals, no localhost, no unexpected port, and an exact approved-host match. Approved names must also resolve exclusively to globally routable addresses; private, loopback, link-local, multicast, reserved, and unspecified results fail closed. It validates every redirect target before following it and validates the final response URL before accepting bytes. Deterministic offline tests inject the reserved fixture hostname `assets.meshy.test` and a public fixture address; neither is a production authorization.
