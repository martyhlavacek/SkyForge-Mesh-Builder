# MBS-RES-0009 — v0.4.2 Preflight Hotfix

## Verdict

v0.4.1 was not ready for user testing because its mandatory Ruff gate failed on the target Mac.

## Root cause

The build environment did not have Ruff available. Although the executable regression suite passed there, two lint defects remained:

- an unused imported symbol;
- an import-order violation in a Flask-dependent test module.

## Resolution

Both reported defects are corrected in v0.4.2. No behavior or prompt content was altered.

## Required acceptance

The replacement package must report a clean Ruff result and complete test suite on the target Mac before the Concept Lab is used.
