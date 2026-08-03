# BUILD VERIFICATION — v0.6.0 CR-0011 Remediation Candidate

**Status:** immutable review candidate; not release-sealed and not cleared for user testing.

Executed in the authoring environment:

- Python compilation: PASS.
- Deterministic geometry generation for three fixtures: PASS.
- Available no-charge tests: 87 passed, 0 skipped.
- Paid OpenAI transport: none.

Unavailable here and therefore not predicted green:

- Ruff 0.15.22.
- Flask-dependent 12 tests in the exact pinned environment.
- Live Blender neutral/banked render, silhouette and export gates.

The candidate includes an automated live Blender preflight command. Claude must run the pinned suite and live Blender gates, or keep user testing withheld.
