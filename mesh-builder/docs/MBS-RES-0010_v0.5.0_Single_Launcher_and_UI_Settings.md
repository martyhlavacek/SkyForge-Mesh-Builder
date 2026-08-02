# MBS-RES-0010 — v0.5.0 Single Launcher and UI Settings

## Objective

Remove the developer-oriented multi-script workflow from normal user operation and permit OpenAI API configuration directly inside the sidecar UI.

## Changes implemented

### Single launcher

Added a root-level launcher:

```text
Launch SkyForge Mesh Builder.command
```

It automatically:

- detects an existing running sidecar and opens it;
- creates `.venv` when missing;
- reinstalls pinned dependencies only when the requirements checksum changes;
- detects Blender;
- prepares non-secret defaults;
- starts the server;
- opens the browser.

The launcher does not run the full engineering test suite during routine startup.

### UI Settings panel

Added in-app settings for:

- OpenAI API key;
- image model;
- beauty and authority sizes;
- beauty and authority candidate counts;
- Blender executable path.

Added UI actions for:

- OpenAI connection testing;
- Blender detection/version testing;
- secure settings save;
- API-key removal.

### Secret storage

Added `app/settings_store.py`.

The API key is stored in macOS Keychain using service identifier:

```text
com.skyforge.mesh-builder.openai
```

The application returns only a masked key status to the browser. Plaintext key fields are removed from `config.json` whenever settings are saved.

Historical plaintext configuration is migrated to Keychain at launcher bootstrap when possible. A key is not silently discarded if migration fails.

### Non-secret configuration

`config.json` stores only:

- Blender path;
- image model;
- image sizes;
- candidate-count defaults.

### New routes

- `GET /api/settings`
- `POST /api/settings`
- `POST /api/settings/test-openai`
- `POST /api/settings/test-blender`

All mutating and connection-test routes require the existing CSRF token.

## Preserved boundaries

- Authority-to-mesh geometry is unchanged.
- Prompt hardening is unchanged.
- Thrusters remain disabled.
- Full developer diagnostics remain available but are no longer required for normal use.
