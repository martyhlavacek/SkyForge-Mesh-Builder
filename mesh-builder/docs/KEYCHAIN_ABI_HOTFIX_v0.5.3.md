# Keychain ABI Hotfix — v0.5.3 candidate

## Trigger

The first authorized macOS user session exposed two native Keychain statuses as large positive integers:

- `4294967168`, the zero-extended representation of signed OSStatus `-128` (user cancelled authorization);
- `4294941997`, the zero-extended representation of signed OSStatus `-25299` (`errSecDuplicateItem`).

The v0.5.2 wrapper declared Security.framework `SecItem*` return values as `ctypes.c_long`. On 64-bit macOS, C `long` is 64-bit while OSStatus is signed 32-bit. The duplicate-item branch therefore failed to recognize an existing generic-password item and never executed `SecItemUpdate`.

## Candidate change

- Declare all `SecItem*` return values as `ctypes.c_int32`.
- Normalize every received status through signed 32-bit conversion defensively.
- Classify `-128` as a user-cancelled authorization rather than presenting an unsigned error or crashing `/api/health`.
- Add no-charge regression tests for both observed zero-extended values and for the duplicate-add → update path.

## Scope exclusions

No image pricing, budget, spend-ledger, cache, prompt, geometry, Blender, provider, or v0.6 behavior is changed.

## Test status

This source is a Claude-review candidate, not a user-testing release. The complete exact-pinned preflight and native macOS round trip remain required before sealing.
