# Aircraft benchmark validation — 2026-07-20

Four representative-mode, all-category in-game benchmark runs were supplied while developing and validating the fixed-input benchmark.

## Environment

- Minecraft: 1.20.1
- Forge: 47.4.10
- Immersive Aircraft: 1.3.3+1.20.1
- Warfare Wings: 1.1.4
- Benchmark module: 1.0.0
- Dimension: minecraft:overworld
- Weather: clear (`raining=false`, `thundering=false`)

## Run outcomes

| Run | Aircraft | OK | Failed | Elapsed ticks | Notes |
|---|---:|---:|---:|---:|---|
| `20260720-130938-all-representatives` | 26 | 4 | 22 | 2354 | Invalid baseline; control hook and entity-removal failures |
| `20260720-131824-all-representatives` | 26 | 26 | 0 | 10237 | Exposed dirty acceleration starts and short brake timeout |
| `20260720-135819-all-representatives` | 26 | 26 | 0 | 11778 | Hardened build validation run 1 |
| `20260720-140820-all-representatives` | 26 | 26 | 0 | 11778 | Hardened build validation run 2 |

The first run was not a valid performance baseline. Most failures reported either `VehicleEntity.tickPilot control hook was not observed` or removal of the aircraft/dummy pilot. The spatial pattern and later successful runs are consistent with benchmark aircraft leaving ticking chunks.

## Hardened-build repeatability

The two hardened-build runs produced byte-identical performance outputs:

- `benchmark.json`: `77cc233e4bf8b616e2f215bf314158732f7918ba8e48aa986dacb3938c58b548`
- `benchmark.csv`: `d4c7ecac67dc451957e8c5215ba3bcb1f3f9b7459a727c640c910a3b4538066d`
- `flight_profiles.json`: `d81024a94d4c2679f6eb0f34a2c9ea9509a2d338d308d69f469c330030d1459d`

This confirms deterministic repeatability for all 26 representative aircraft under the supplied environment.

## Corrected findings

- All 26 aircraft completed both hardened runs; no control-hook or entity-removal failures remained.
- P-51D acceleration normalized from the contaminated `0.90 / 1.25 / 1.30 s` result to `7.25 / 15.60 / 18.75 s`.
- P-40E acceleration normalized from `3.80 / 6.75 / 7.05 s` to `7.20 / 15.55 / 18.65 s`.
- All Warfare Wings aircraft had clean acceleration starts and were eligible for generated flight profiles.
- The stock Bamboo Hopper and Biplane were falsely marked contaminated because the first sampled engine-power step was `0.05`; acceleration baseline capture is therefore moved to the settled pre-throttle state.
- Fifteen aircraft still did not reach 10% speed within the 600-tick brake phase. Their recorded distance is a lower bound, not a completed stopping distance.
- B-17, B-29, G10N1, and G10N2 retained slightly more speed in the turn than in the straight test. Their turn altitude changes were only about `+0.07` to `+0.09` blocks, so the result was not caused by a meaningful descent.

## Final hardening decisions

1. Force-load chunks around every active benchmark aircraft and release only chunks owned by the benchmark.
2. Wait for a live control heartbeat, near-zero motion, and settled engine power before acceleration.
3. Capture acceleration initial speed and engine power before full throttle is applied.
4. Save `latest_successful.json` whenever every aircraft completed successfully; profile eligibility remains a per-aircraft filter.
5. Never compare incomplete brake distances as completed stopping distances.
6. Emit `brake_lead_blocks` only when the aircraft reached 10% speed; otherwise emit `brake_distance_lower_bound_blocks`.
7. Exclude individually contaminated measurements from generated autonomous-flight profiles.
