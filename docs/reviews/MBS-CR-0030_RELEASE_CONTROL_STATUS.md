# MBS-CR-0030 release-control status

- Governing review: `MBS-CR-0030_MBS-192_FOCUSED_REREVIEW.md`
- Reviewer-authored source SHA-256: `d131c86238b06b95688933fec4d6a3795d3ca93637e7c1ce0ee761e7cc121f58`
- Exact reviewed candidate: `4a959e202fd2c839e3d1f016591750fe938e55ea`
- Candidate parent: `87f04a875355c6ed1202f0f6eddfa055d26d29b1`
- Review disposition: `ACCEPT WITH REQUIRED CHANGES`
- MBS-185 through MBS-191: CLOSED
- MBS-192: CLOSED
- MBS-193: OPEN Observation, non-blocking
- MBS-194: CLOSED after the required evidence-only wording correction
- Release-control evidence SHA-256: `dfb94b004d9e9124127610d26cef86af5c42ba7f4fee4f6a00f6274640c14372`
- Implementation merge commit: `b1a46d03607fe97725646bedcd1caa8b034d5715`
- Merge first parent: `81acdec3e7e935b53eac5748c6b41007c878639f`
- Merge second parent: `4a959e202fd2c839e3d1f016591750fe938e55ea`
- Accepted fallback baseline: `v0.7.1-accepted-baseline` at `d38dd5d1638eae0942929a4ed568edb048220894`
- Accepted fallback baseline status: unchanged
- Release artefact status: no new Git tag or GitHub Release was created

The MBS-194 qualification was applied to a new immutable evidence archive without modifying the reviewed source candidate. The reviewer-authored MBS-CR-0030 text is not reconstructed in this status record; the SHA-256 above identifies the supplied original.

Local no-spend pilot UI testing may proceed after the documentation record passes CI. Live provider authorization remains separate. No Meshy task, API-key use, provider polling or download, paid operation, or credit consumption is authorized by this record.

MBS-136 remains OPEN against a real provider. Mocked, injected-spy, disabled-transport, and local pilot tests do not close MBS-136: the successful v0.8.1 no-spend validation proves local governance and fail-closed behavior only. Real Meshy/provider behavior remains unproven until a separately authorized live smoke test.
