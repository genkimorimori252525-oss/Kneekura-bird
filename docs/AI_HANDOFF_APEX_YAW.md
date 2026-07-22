# P-47N coupled-climb re-engagement handoff

Draft PRs #9 and #13 are preserved as research history. The full vertical reversal in #9 spent excessive altitude recovering from a steep descent. The near-vertical apex-yaw plan in #13 also waits too long before yaw authority becomes useful because Immersive Aircraft smooths X/Z input over ten ticks.

The exact Immersive Aircraft 1.20.1 update order is now represented by deterministic tools on branch `agent/p47-coupled-climb-replay`:

- `tools/analyze_apex_yaw_replay.py` models orientation and 10-tick input smoothing;
- `tools/batch_apex_yaw_replay.py` evaluates multiple preserved sessions;
- `tools/analyze_coupled_climb_trajectory.py` advances P-47N position, velocity, thrust, drag, glide and gravity;
- `tools/test_coupled_climb_trajectory.py` calibrates one modeled tick against preserved Forge telemetry;
- `tools/p47_coupled_climb_candidate.json` is the machine-readable candidate source of truth;
- `docs/P47_COUPLED_CLIMB_REPLAY.md` records the evidence and limitations.

The selected pre-flight candidate is:

1. climb only to about `-22 deg`;
2. after the minimum eight-tick commitment, begin yaw by `-2 deg` pitch instead of waiting for an apex;
3. hand to lead capture when horizontal lead error reaches `65 deg`;
4. use pivot divisor `22`, capture pitch divisor `10`, pitch damping `0.10`, yaw damping `0.05` and lead horizon `8 ticks`;
5. preserve terrain, collision, credible-threat, LOS, range, friendly-fire, fixed-gun cone and rear-target gates unchanged.

After removing one duplicate artifact, the calibrated trajectory model reaches the normal angle/range/closure attack sector in all nine unique preserved mutual-dogfight trajectories. Modeled minimum speed is about `17.5 bps`, minimum separation about `17.2`, and maximum separation about `149.7`.

This is not a qualification pass. The A6M reaction, line of sight, terrain, collision and threat arbitration still require a real Forge server. GitHub-hosted Actions minutes are exhausted, so do not open another benchmark PR or trigger another hosted run until execution capacity returns.

Next validation order: Python calibration test, ordinary build and deterministic mission simulation, apply the selected constants to the production adapter, one targeted `dogfight_mutual`, inspect legitimate reciprocal fire and safety metrics, repeat only after a safe pass, then full regression before merge.
