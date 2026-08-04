# MBS-DEC-0001 — Multivolume Visual Failure and Multiview Pivot

**Decision date:** 3 August 2026  
**Decision owner:** Marty Hlavacek  
**Status:** Approved

## Human visual-test result

The v0.8.0 Alpha 1 `geometry_v2` experiment failed the controlled human visual gate.

The implementation successfully demonstrated deterministic assembly, validation, evidence production, and technical isolation. Those engineering results remain valid. They do not establish visual suitability.

The generated geometry was rejected because:

- the v0.7.1 shell remained a thin terraced slab;
- cockpits appeared as oversized generic ellipsoids rather than integrated canopies;
- the added fuselage appeared as a generic spindle over the craft;
- weapons appeared as simple boxes;
- gunship engine primitives did not correspond to the visible nacelles;
- the belly appeared as a generic attached capsule;
- side, front, and banking views did not form a coherent authored vehicle;
- generic overlapping primitives sat on the silhouette instead of reconstructing the approved hard-surface design.

## Disposition

`geometry_v2` is retained only as an archived, opt-in negative experiment.

Do not promote it, add further primitive recipes, rescue it with boolean union, reposition its primitives, improve its textures as a rescue strategy, or use it as the basis for Alpha 2 deterministic refinement.

Codex should inspect the current findings register and record this visual failure using the next available finding number, expected to be **MBS-180**. It blocks further promotion of `geometry_v2`, not the accepted v0.7.1 route or the new multiview pilot.

## Accepted operational baseline

The deterministic v0.7.1 route remains acceptable for game development, continued tooling, provisional gameplay assets, and a no-cost offline fallback. Its limitations remain open. “Acceptable for use” does not mean visually final.

## Approved pivot

The next fidelity experiment is a provider-backed multiview reconstruction route. It must remain opt-in, preserve v0.7.1, use approved top/front/right views, bind all inputs and outputs, begin with Meshy behind strict authorization, and permit future providers without implementing them now.

## Findings posture

- MBS-150 through MBS-154 remain open.
- The failed multivolume route is no longer the intended closure path.
- The multiview route becomes the next candidate visual-fidelity path.
- MBS-136 remains open against a real provider.
- MBS-177 through MBS-179 remain non-blocking carry-forward items.
