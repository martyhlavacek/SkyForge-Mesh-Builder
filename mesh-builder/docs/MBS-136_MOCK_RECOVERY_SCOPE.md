# MBS-136 mock recovery scope

The v0.7.0 no-charge implementation includes request-correspondence recovery only against the deterministic `mock_provider` lifecycle service.

The correlation record contains exactly:

- `requestDigest`
- `providerId`
- `providerModel`
- `resolvedProviderOptionsDigest`
- `authoritySetSha256`
- `accountIdentityDigest`
- `dispatchWindowStart`
- `dispatchWindowEnd`
- `expectedCost`

Recovery follows the frozen rules: a known task ID is authoritative; an absent ID causes a recent-task correspondence query; exactly one match may be adopted; zero or multiple uncertain matches remain unresolved; unresolved reservations remain charged against local caps and block new dispatch; manual adjudication appends an immutable event.

This mock evidence does **not** close MBS-136 against Meshy or any other real provider. Production credentials and paid dispatch remain disabled. A later exact-candidate review must prove provider-specific correspondence, account scoping, recent-task completeness, and hard local caps before any paid experiment.
