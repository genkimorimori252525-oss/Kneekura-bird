# Aircraft benchmark validation — 2026-07-20

Two representative-mode, all-category in-game benchmark runs were supplied after merging the first benchmark implementation.

## Environment

- Minecraft: 1.20.1
- Forge: 47.4.10
- Immersive Aircraft: 1.3.3+1.20.1
- Warfare Wings: 1.1.4
- Benchmark module: 1.0.0
- Dimension: minecraft:overworld
- Weather: clear (`raining=false`, `thundering=false`)

## Run outcomes

| Run | Aircraft | OK | Failed | Elapsed ticks |
|---|---:|---:|---:|---:|
| `20260720-130938-all-representatives` | 26 | 4 | 22 | 2354 |
| `20260720-131824-all-representatives` | 26 | 26 | 0 | 10237 |

The first run was not a valid performance baseline. Most failures reported either `VehicleEntity.tickPilot control hook was not observed` or removal of the aircraft/dummy pilot. The spatial pattern and later successful rerun are consistent with benchmark aircraft leaving ticking chunks.

## Valid second-run findings

- All 26 representative aircraft completed every benchmark phase.
- Stall-proxy speed was produced for all 26 aircraft.
- `brake_time_10_s` was absent for 16 aircraft because the 260-tick brake phase ended before they reached 10% of initial speed.
- P-51D acceleration timing is implausibly short: 50% in 0.90 s, 90% in 1.25 s, 95% in 1.30 s despite a measured top speed of 44.00 blocks/s.
- P-40E is also unusually fast to the acceleration thresholds: 3.80 / 6.75 / 7.05 s.
- Four heavy bombers reported turn-speed retention above 1.0 (B-17, B-29, G10N1, G10N2), so future output should record vertical speed/altitude drift during the turn before treating the value as energy gain.

## Required benchmark hardening

1. Force-load chunks around every active benchmark aircraft and release only chunks owned by the benchmark.
2. Do not begin acceleration sampling until the control hook is alive, aircraft speed is near zero, and engine power has settled near zero.
3. Record acceleration initial speed and engine power so contaminated starts are visible.
4. Use the last fully successful run as the comparison baseline; failed runs must not replace it.
5. Extend braking and explicitly record whether the 10% threshold was reached.
6. Avoid generating autonomous-flight profiles from runs with contaminated acceleration starts.
