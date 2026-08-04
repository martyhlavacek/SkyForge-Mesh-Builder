# Meshy Artifact Host Policy

Contract version: `skyforge.meshy-artifact-hosts.2026-08-04.v1`.

The exact production approved-host set is `assets.meshy.ai`. Meshy's official Multi-Image to 3D response example was re-retrieved on 2026-08-04 and identifies that exact hostname for the initial GLB artifact URL. `api.meshy.ai`, subdomains, suffix matches, wildcard domains, CDN hosts, cloud-storage hosts, and undocumented redirect destinations are not approved.

Production uses the operating system's `getaddrinfo` resolver for both address families. Trust is not cached: every initial URL, redirect target, and final response URL is checked. An empty answer, resolver failure, malformed address, non-global address, or mixed public/non-public answer fails closed. Unknown redirect hosts are recorded in redacted preflight evidence and refused; they are never dynamically trusted.

The policy requires HTTPS, a hostname, no embedded credentials, no IP literals, no localhost, port absent or exactly 443, and an exact case-folded approved-host match. Redirects are bounded to four. The no-download preflight performs policy-only validation by default; an injected or separately invoked HEAD transport may inspect a bounded redirect chain without downloading artifact bytes. It never reads an API key, submits a task, or polls one, and it strips signed query values and fragments from evidence.

This policy enables security preauthorization review only. It does not authorize a Meshy task, provider download, credit use, or an undocumented redirect.
