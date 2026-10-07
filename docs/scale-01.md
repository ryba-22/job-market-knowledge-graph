# SCALE-01 — incremental large-scale acquisition

Base: CORPUS-05 with 568 offers.

First budget:
- Just Join IT +250 target / +180 minimum
- No Fluff Jobs +300 / +250
- RocketJobs +300 / +250
- Bulldogjob +120 / +75
- Pracuj secondary +50 / +20
- The Protocol +0 while the official MCP remains capped at already-covered identities

Target new total: 1020.
Minimum accepted new total: 775.

Contracts:
- load known source identities from the frozen base before discovery;
- fetch only unknown identities;
- one independent source job per acquisition slice;
- source-specific rate limit and retry policy;
- Bulldogjob stays conservative;
- Pracuj stays SECONDARY_PUBLIC_INDEX;
- deterministic corpus assembly rejects conflicting duplicate identities;
- every source batch exports full RawObservation evidence as a separate artifact;
- previous corpus versions are immutable.

The first scale pilot still uses CI artifacts for full raw payload archives. Production-scale follow-up should move raw evidence to durable object storage.
