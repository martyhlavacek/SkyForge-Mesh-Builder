# MBS-RES-0008 — v0.4.1 Prompt Hardening

## Objective

Carry forward the previously learned SkyForge visual-governance lessons into the actual OpenAI prompt builders used by the sidecar.

## Problem

v0.4.0 restored the OpenAI concept workflow, but its prompt builders were still too soft. They described the beauty and authority outputs in the correct general direction, but they did not explicitly encode all of the operational constraints learned from earlier experiments:

- strict camera discipline;
- lighting discipline;
- reduced cinematic effects and clutter;
- full in-frame coverage; and
- stronger binding between the approved beauty concept and the derived top-down authority.

## Corrective changes

### Beauty prompt

Added explicit requirements for:

- strict 3/4 front beauty-shot presentation;
- slightly elevated fixed camera angle;
- ship centered and fully visible in frame;
- no cropped extremities;
- moderate lens / no extreme wide-angle distortion;
- controlled studio-style lighting;
- no heavy rim-light washout or shadow ambiguity;
- simple dark or neutral background only;
- no smoke, motion blur, lens flare, explosions, starscape clutter, extra vehicles, or props;
- readable design suitable for later top-down conversion.

### Authority prompt

Added explicit requirements for:

- exact same ship, not a redesign or reinterpretation;
- true overhead top-down view;
- orthographic or near-orthographic presentation;
- zero roll;
- nose oriented upward in frame;
- ship centered, fully visible, and surrounded by a small clean margin;
- plain neutral background only;
- minimal neutral lighting;
- no dramatic shading, atmosphere, glow, cast-shadow clutter, perspective tricks, or decorative effects.

### Regression protection

Added a source-level test that asserts the required prompt phrases are still present. This reduces the risk that a later refactor silently weakens the prompt contract.

## Recommendation for the next live test

Use v0.4.1 for the next full beauty → authority → mesh run. The main validation goal is now whether the live OpenAI outputs actually respond well to the stronger instructions across multiple craft classes, especially more delicate winged ships.
