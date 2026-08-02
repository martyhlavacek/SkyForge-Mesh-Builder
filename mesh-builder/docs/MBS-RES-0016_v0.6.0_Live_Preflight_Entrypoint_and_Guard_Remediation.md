# MBS-RES-0016 — v0.6.0 Live Preflight Entrypoint and Guard Remediation

## Trigger

The exact MBS-CR-0013-cleared candidate passed checksum, clean-environment, exact-pin and NetworkX graph-engine checks on macOS, then failed before Blender launch with `ModuleNotFoundError: No module named 'app'`. The launcher invoked `python scripts/run_live_blender_preflight.py`; direct-file execution places `scripts/`, not the package root, at the head of `sys.path`.

## Scope

- Make the live-preflight script self-bootstrap the package root before importing `app` or `common`.
- Add `PYTHONPATH` in the Finder launcher as defence in depth.
- Add a clean direct-entrypoint regression test that removes `PYTHONPATH` and runs `--help` from an unrelated directory.
- Close MBS-104 by raising the deliberate-asymmetry guard floor from 0.02 to 0.20; Claude measured clean residuals at 0.34–0.38 and mirrored-mutant residuals at 0.057–0.072.
- Close the MBS-99 residual with a deterministic exact-source manifest checked before Blender resolution or fixture work.

## Non-goals

No geometry formula, provider, OpenAI, budget, spend-ledger, Keychain, cache, coordinate-contract, Blender-build, export, animation, destruction, thruster or gameplay behaviour is changed.

## Required independent review

The candidate must not be given to Marty for another run until Claude independently verifies the direct-file entrypoint in a from-contract-only environment, mutation-kills the MBS-104 guard, validates exact-source-binding failure on a changed file, reproduces the three accepted GLB hashes and clears the exact candidate for one automated Blender run.
