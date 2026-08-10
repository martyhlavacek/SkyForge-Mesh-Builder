# Open findings

These findings remain open; this bootstrap does not claim that any are fixed.

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

The accepted v0.7.1 baseline contains no geometry fix for MBS-150 through MBS-154.

MBS-165 through MBS-173 are closed by MBS-CR-0025. MBS-181 is closed by the MBS-CR-0026 focused re-review. MBS-185 through MBS-191 are closed by MBS-CR-0029. MBS-192 is closed by MBS-CR-0030. MBS-194 is closed after its required evidentiary qualification was applied to the immutable release-control evidence. MBS-182 remains open as an Observation, MBS-183 remains the standing immediate pre-authorization re-verification requirement, MBS-193 remains an open non-blocking Observation, and MBS-136 remains open against a real provider. Finding numbering continues from **MBS-195**.
