# Blender 5.2 signal 139 diagnosis

Date: 2026-08-11. Host: Apple arm64, macOS 14.4.1 (23E224). Selected executable:
`/Applications/Blender.app/Contents/MacOS/Blender`, Blender 5.2.0 LTS build `fbe6228777e7`, native arm64.
The macOS crash report records `translated: false`.

`Blender --version` exits successfully. The minimal background command
`Blender --background --factory-startup --python-expr "print('SKYFORGE_BLENDER_SMOKE_OK')"` exits 139 and never
prints the marker. Temporary isolated user config/scripts/data paths plus `--disable-autoexec` produce the same
result. This build accepts only the Metal GPU backend; requesting OpenGL is rejected and startup still crashes.

The exact preceding USD warning is:

```text
ArchWarn: ARCH_CACHE_LINE_SIZE != Arch_ObtainCacheLineSize()
Function: Arch_ValidateAssumptions
File: /Users/jonas/blender-dev-deps/build_darwin/deps_arm64/build/usd/src/external_usd/pxr/base/arch/assumptions.cpp
Line: 140
```

The macOS diagnostic report records native ARM-64 `EXC_CRASH`, `SIGSEGV`, termination signal 11. The meaningful
startup frames are `_platform_strstr`, `blender::gpu::supports_barycentric_whitelist`,
`blender::gpu::MTLBackend::metal_is_supported`, and GPU backend selection. The evidence therefore classifies this
as **State A: Blender crashes before executing SkyForge Python**, in Metal capability detection. The USD warning
is observed but is not implicated by the crash stack, so causation is not claimed.

No GLB was passed to Blender, no SkyForge normalization was attempted, and no Blender preferences or system
settings were changed. A human must select/install a Blender build that passes the minimal background Python smoke
gate, then configure Mesh Builder to use it. Do not proceed to real normalization until that gate passes.
