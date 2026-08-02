# BUILD VERIFICATION — SkyForge Mesh Builder Sidecar v0.5.0

## Scope

This revision changes installation, launch, and settings management. It does not alter the accepted deterministic authority-to-mesh geometry path.

## Verification performed

- Python compilation: **PASS**
- Available regression suite: **41 passed, 2 dependency-gated modules skipped**
- Shell syntax for root launcher and engineering `.command` scripts: **PASS**
- New-module unused-import AST audit: **PASS**
- API key absent from `config.json.example`: **PASS**
- API key removed from config by settings-save path: **PASS**
- Settings payload does not expose the raw key: **PASS**
- Keychain commands use argument arrays rather than shell interpolation: **PASS**
- Single launcher automatically creates the environment and installs dependencies: **PASS**
- Single launcher does not run `pytest` or the engineering preflight during routine startup: **PASS**
- Existing concept and authority-mesh regression tests retained: **PASS**

## Sandbox limits

The two skipped modules require Flask/Werkzeug, which are installed by the launcher on the target Mac but unavailable from this sandbox package index.

Ruff is also unavailable in this sandbox. The exact unused-import failure class that blocked v0.4.1 was checked independently through AST analysis, and all new/modified modules reported no unused imports.

No live macOS Keychain, Blender, or OpenAI connection was executed in this Linux build environment. Dedicated test doubles validate Keychain command construction and secret redaction. The target Mac remains the required environment for those operating-system and network integration checks.
