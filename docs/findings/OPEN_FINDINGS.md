# Open findings

This register records the current disposition of open and recently closed findings. Findings are closed only where an identified independent review explicitly did so.

- **MBS-136:** Real-provider request-correspondence recovery remains unproven. Paid-provider work is not authorized.
- **MBS-150:** Perimeter terracing and ribbed edge walls remain a geometry-quality issue.
- **MBS-151:** Major craft volumes remain fused into one height field.
- **MBS-152:** Engine housings remain broad rounded slabs.
- **MBS-153:** The underside remains plausible but generic.
- **MBS-154:** Forward weapons remain simple extruded prongs.
- **MBS-158:** macOS launcher usability remains open.
- **MBS-159:** macOS setup usability remains open.
- **MBS-177 (Minor, non-blocking):** The attachment/exposure diagnostic image duplicates the side view.
- **MBS-178 (Observation):** Attachment acceptance thresholds are permissive.
- **MBS-179 (Observation):** The historical Import Probe check uses a mutable tag.
- **MBS-180 (Blocking `geometry_v2` promotion only):** v0.8.0 Alpha 1 passed its technical review but failed controlled human visual acceptance. Its generic overlapping-primitives route must remain inactive and must not be promoted or used as the Alpha 2 basis.
- **MBS-182 (Observation):** The submission reservation is created before request construction. This fails in the safe direction and the reservation model is unchanged by the MBS-181 remediation.
- **MBS-183 (Observation; standing immediate pre-authorization requirement):** Meshy endpoint, parameters, model availability, artifact hosts, retention, and the current 20-credit estimate require re-verification immediately before separate live authorization.
- **MBS-184 (Observation; blocks nothing):** Offline evidence uses synthetic DNS placeholder values under `dnsResults`, which could be mistaken for observed `assets.meshy.ai` resolution. In the next evidence generation, use `stubDnsResults` or `resolutionSource: offline_stub_not_observed`.
- **MBS-193 (Observation; blocks nothing):** The pilot constructs a `requests.Session()` when the application is created. Construction opens no socket, and all provider operations remain guarded before transport. Lazy construction remains optional.
- **MBS-195:** The inconsistent human-approved TOP/FRONT/RIGHT authority bundle remains rejected evidence. It must not be used for provider preauthorization. If the multiview route is abandoned rather than repaired, its future disposition may be `SUPERSEDED BY SCOPE`, not CLOSED.
- **MBS-198 — CLOSED by MBS-CR-0035:** Track S has a valid `ABORT_MESHY` experiment-level null-result branch that does not create a provider lifecycle state or automatic provider action.
- **MBS-199:** The cost model and failed-task charging remain unresolved.
- **MBS-200 (OPEN / PARTIALLY REMEDIATED):** Measurement specification, IoU alignment, and gameplay measurements exist, but the independently reloaded-GLB Blender/topology measurement engine is not yet complete.
- **MBS-201:** Track S preregistration remains required before the first paid task.
- **MBS-202 — CLOSED by MBS-CR-0035:** Rejected MBS-195 FRONT/RIGHT hashes are quarantined at reconstruction-input/provider boundaries while historical evidence remains inspectable.
- **MBS-207 (Observation):** The asymmetric ppm normalization remains unchanged.
- **MBS-208 (Minor, non-blocking):** Near-full-canvas silhouettes can still pass because the degenerate guard rejects only exact canvas-equal bounding boxes. A deliberately crafted one-pixel-border construction can yield approximately 99.6% coverage and still pass. Schedule deterministic maximum foreground-coverage and/or minimum-background-margin policy with a regression fixture; do not modify implementation in this documentation branch.
- **MBS-209 (Minor, non-blocking):** Filename tokenization can miss ALL-CAPS role tokens immediately followed by lowercase text, such as `TOPview.png`. Schedule regression cases for `TOPview.png`, `FRONTview.png`, and `RIGHTside.png`; this does not reopen MBS-197 or MBS-205, and implementation is unchanged here.
- **MBS-210 (Major):** Resolved failed-task charging currently accepts evidence that is insufficiently bound to a verified fresh contract artifact.
- **MBS-211 (Minor):** The Track S gameplay-camera convention requires stronger cross-binding to the established gameplay pipeline.
- **MBS-212 (Observation):** The contract-age evidence generator used date-only arithmetic rather than the implementation's full timestamp.

The accepted v0.7.1 baseline contains no geometry fix for MBS-150 through MBS-154.

MBS-165 through MBS-173 are closed by MBS-CR-0025. MBS-181 is closed by the MBS-CR-0026 focused re-review. MBS-185 through MBS-191 are closed by MBS-CR-0029. MBS-192 is closed by MBS-CR-0030. MBS-194 is closed after its required evidentiary qualification was applied to the immutable release-control evidence.

MBS-196 is CLOSED: MBS-CR-0034 accepted the measured deterministic cross-view consistency gate after MBS-203 closure, including its integer scale-invariant W/L/H comparison, deterministic six-threshold measurement, centring and spread measurements, derived and digest-bound camera declaration, reload-time pixel remeasurement, and forged-record resistance.

MBS-197 is CLOSED: MBS-CR-0034 accepted filename/role provenance conflict handling after MBS-205 remediation.

MBS-203 is CLOSED: the uniform/degenerate authority-image fail-open path was remediated and independently verified. MBS-204 is CLOSED: the Shared Authority Geometry Scaffold document is corrected to `LATER / CONTINGENCY`, with Track S restored as the preferred next empirical route. MBS-205 is CLOSED: the required role-token boundary cases were independently verified. MBS-206 is CLOSED: the headline six-threshold metric and fixed-threshold exemplar evidence are unambiguous and independently reproducible.

MBS-198 and MBS-202 are CLOSED by MBS-CR-0035. MBS-213 is CLOSED by MBS-CR-0036 because historical multiview workspace and new Track S sessions are isolated; Track S does not inherit historical TaskLog, approval, or provider state. MBS-214 and MBS-215 are CLOSED by MBS-CR-0037: legacy `/bundle/import` is transactionally refused for active Track S sessions before upload parsing or mutation, and historical `/artifact/preflight` is refused before `PilotRuntime.preflight()`, DNS, transport, or credential access.

MBS-136 remains OPEN against a real provider; mocked and local evidence does not close it. MBS-195 remains OPEN as preserved negative evidence; if Track M is eventually abandoned, its future disposition may be `SUPERSEDED BY SCOPE`, not CLOSED. MBS-199, MBS-201, and MBS-210 remain OPEN. MBS-200 remains OPEN / PARTIALLY REMEDIATED. MBS-183 remains the standing immediate preauthorization contract-reverification requirement. MBS-207 and MBS-212 remain Observations. MBS-208, MBS-209, and MBS-211 remain OPEN MINOR findings. All other standing findings remain unchanged. Finding numbering continues from **MBS-216**.
