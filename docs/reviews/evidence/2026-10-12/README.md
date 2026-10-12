# Review evidence — 12 October 2026

These files preserve observations from the reviewed commit, not current runtime state.

`reproduced: true` in the probe results means the undesired behavior was reproduced. It is not a passing application-readiness check. Backend probes ran against an isolated temporary database that was removed afterward; external notification delivery was stubbed. AI probes exercised validator/config-sync functions, not trained model inference.

Package audit data can contain duplicate advisory entries. The review distinguishes affected packages, returned entries and unique package/advisory pairs; actual exploitability was not established. The AI audit covers declared direct requirements, not the full heavy inference dependency tree.

Schema drift data came from schema-aware reflection after fresh migrations through revision 0016. Equivalent PostgreSQL FLOAT/DOUBLE PRECISION spellings were excluded. No missing model columns were found; differences cover integer width and nullability.

No credentials, process-environment dumps, raw request tokens or database dumps are included. Source paths are repository-relative.
