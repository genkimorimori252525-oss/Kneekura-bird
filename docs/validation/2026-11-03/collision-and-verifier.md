# Collision and telemetry identity evidence — 2026-11-03

Scope: Issue #7, starting main `2585f44fa02b84ed7f593bf9a65798a2b4f056ea`.
These are controlled tests, not qualification of all aircraft, roles, or combat scenarios.

## Fixed environment and inputs

- Minecraft 1.20.1, Forge 47.4.20, Java 17.0.17+10, Gradle 8.8; Cloud Linux.
- Immersive Aircraft 1.3.3 Modrinth version `GsVmbbkj`, SHA-256
  `d1f7cfeed3ac2cf69472ae756eb9189dad04ab21b8afbd443c82f40e51bbf065`.
- Warfare Wings 1.1.4 Modrinth version `q94LN7dV`, SHA-256
  `3b6b245e703862517fe7aae6acd95ccafc865e1e81ba7a26e2b9abcfe1120187`.
  Downloaded files matched Modrinth's SHA-512 metadata. The jars are not included here.
- The measured profile fixture was the one tracked in the relevant checkout. The target was
  `warfare_wings:a6m`, scenario `full`. Test source at #123 head `7269efb3` SHA-256
  `580032efbe469a61574a6a8a0cd2f6d22cf7e74a0c93b68462d08640b783576a`.

## Results and scope

| Run | Outcome | Meaning |
| --- | --- | --- |
| Main plus first test, local `d443066` | Build 0, deterministic simulator 12/12 | Simulator is a preflight, not mod physics. |
| Main plus first test, initial fixture | GameTest 60/61, Gradle 1 | Nonzero engine sentinel was rejected before the assertion: no usable fuel. |
| Main plus first test, fuel attempt | GameTest 60/61, Gradle 1 | Fuel was not loaded because refuelling requires an occupant. |
| Main plus corrected first test, local `9d7180a` | GameTest 61/61, Gradle 0 | In STARTUP with collision risk but no avoidance write, base engine input was applied. |
| #101 head `9c21ca34` plus same corrected first test | GameTest 60/61, Gradle 1 | The startup engine-input assertion failed under the same conditions. |
| Main plus both tests, local `ee4e970` / #123 head `7269efb3` | GameTest 62/62, Gradle 0; A6M summary 1/1 `PARKED`, no crash report | Actual collision-avoidance engine input survived; its event recorded risk, planned 0.35 and applied/actual 0.28. |
| Deliberately unsafe local mutation `e6fc949` on #101 plus both tests | GameTest 61/62, Gradle 1 | Always applying autonomy at collision risk made the avoidance-input assertion fail. This mutation is not proposed for integration. |

The first corrected main run exposed a verifier defect: `verify_flight_scenario.py` selected the
newer test aircraft's two-frame log while reading a different aircraft's successful summary and
returned pass. Draft #124 matches summary UUIDs to logs; its revised verifier reprocessed the
last main run, selected the summary aircraft's 4,838 frames, and passed with Gradle status 0. Its
multi-aircraft logic has synthetic tests, not a new multi-aircraft GameTest. The #101 run remained
failed when reprocessed with its actual Gradle status 1. Terrain precedence, player exclusion,
all control axes, combat suppression, flight safety and other aircraft still need separate tests.

## Integrity and availability

SHA-256 of selected raw evidence:

| Artifact | SHA-256 |
| --- | --- |
| Main 62-test console log | `434aee8d60743bda822a28e4a67566bec961f633eecb0f9d426e76a9efbe1695` |
| Main summary | `3df09cac9aa7ec91acf927f22cb019db0d118010f4efb3fa47d1b971119a9917` |
| Main summary-aircraft JSONL | `4c52a2dc443863317387a2af9b1bd5d12ca2277d1afbd0d7231e174506188290` |
| Main revised verifier result | `17c97be5b0bffb63f0125ef096a7440560dec681fa0f7f18e56643ed16a471a0` |
| #101 reproduction console log | `47b6cbfc2869cd8801a738fbe38bbe8b0863f6dfd47983920bbcedf563e443d3` |
| Unsafe mutation console log | `636db2587909323a81823993e6526f6abfeac01119103ce8d306304c4e09b34f` |
| Initial failed fixture console logs | `914d234d6682cae25f05326d851d3d08018afcaa369d7d1a31cdd67afc65147f`; `7506de9cbc581fde5baa41cff58a7f8540aec238ef039f8de3ba523961844284` |

Raw logs, full telemetry, and verifier JSON are retained in the Cloud workspace under
`/workspace/issue7-evidence-20261103/` and the relevant worktrees. The workspace is ephemeral;
the hashes above do not themselves preserve those files. Transfer or publish raw artifacts only
after reviewing their contents and repository storage policy. No GitHub Actions or runner changes
were made.
