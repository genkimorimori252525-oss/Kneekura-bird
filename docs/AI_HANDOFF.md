# AI development handoff

Last updated: 2026-07-23 (Asia/Tokyo)

## Read first

Follow `/AGENTS.md` except that the repository owner explicitly waived its session-time and validation-run caps for the current large implementation task. Continue to preserve the rules that still protect correctness: one commit per behavioral hypothesis, no oversized all-in-one pull request, inspect the harness before retuning aircraft behavior, and never weaken the air-combat safety invariants.

## Current objective

Finish the reciprocal `dogfight_mutual` qualification for the A6M and P-47N before expanding fighter AI to the remaining aircraft.

A passing candidate must satisfy all of the following in one run and then repeat:

- neutral opposed opening;
- A6M fires at least once through the real weapon manager;
- P-47N fires at least once through the real weapon manager;
- no rear-target fixed-gun firing;
- no terrain contact or aircraft collision;
- minimum separation at least 8 blocks;
- maximum separation at most 480 blocks;
- the P-47N remains inside the useful simulation area;
- after combat cleanup, the A6M resumes the ordinary mission, lands, stops, and reaches `PARKED`.

## Repository and validation state

- Active experiment branch: `agent/p47-coupled-climb-selfhosted`.
- Current experiment head: `b4a03d2772ae43c3985eb5a3cb346b07ab216c0e`.
- Current validation request on `main`: `d95aa45d5011493cfed48a867284933184e23d54`.
- Self-hosted runner labels: `self-hosted`, `Windows`, `X64`.
- Validation execution log: Issue #15.
- Latest completed-run index: `.github/local-validation-status.json`.
- The index is maintained by `.github/workflows/ww-local-validation-status-index.yml`.
- The current request is waiting for the self-hosted runner to begin; Issue #15 has not yet emitted its start record for `b4a03d27`.

The reciprocal test harness is now internally valid. `MutualDogfightMissionHoldAdapter` prevents the ordinary mission from advancing into unrelated turn or stall phases while the reciprocal scene owns the aircraft, then releases the A6M to complete its normal return and landing sequence.

## Experiment structure

The main coupled controller is `EnergyFighterApexYawAdapter`.

Most maneuver experiments remain isolated in the compile-time harness:

- `ww-debug-benchmark/coupled-handoff-validation.gradle`

The current PIVOT-duration hypothesis is additionally applied by a checked source replacement in `ww-debug-benchmark/build.gradle`. It changes only the experiment workspace before Java compilation; the Java source constant remains unchanged in the repository until the behavior is validated and consolidated.

## Findings established this session

### 1. Opposite-turn local-minimum crossing was falsified

Commit: `f75d1066c1eb1a8c1386f95056ec9c4b1b148d81`.

The controller detected the horizontal local minimum correctly, but reversing the turn moved the target rapidly behind the P-47N and ended in `capture_reversal_timeout`. It did not produce legitimate P-47N fire. Do not repeat this geometry.

### 2. A delayed powered same-turn lag climb removes closure but loses bearing

Commit: `1fc17d2afcae94a4226fa64d2babb12f16508b4f`.

Runs:

- `29938099173`: A6M fire 8, P-47N fire 0, minimum separation 9.40, no ground frames, A6M parked.
- `29938400816`: A6M fire 6, P-47N fire 0, minimum separation 11.75, no ground frames.

Measured effect:

- closure improved from 19.47 to 2.56 blocks/s in the first run;
- closure improved from 18.09 to 3.87 blocks/s in the repeated run;
- horizontal error nevertheless degraded from roughly 51–52 degrees to well beyond 100 degrees.

The climb itself can trade closure for altitude, but starting it only after CAPTURE angular progress stalls is too late. By then the target-bearing rotation has caught and overtaken the P-47N nose rate.

### 3. CAPTURE-entry lag climb has not yet been exercised

Commit: `b968462c8750f1909bc41d0d310447009c770431`.

Runs:

- `29938906137`: A6M fire 7, P-47N fire 0, minimum separation 12.35, no ground frames.
- `29939584355`: A6M fire 1, P-47N fire 0, minimum separation 10.85, no ground frames.

Both runs remained safe, but every completed coupled attempt ended in `pivot_timeout` before CAPTURE. Therefore these runs do not falsify the CAPTURE-entry lag hypothesis.

The measured PIVOT endpoint explains the blockage:

- completed attempts usually timed out with horizontal lead error between approximately 74.7 and 80.3 degrees;
- the required CAPTURE criterion is still 65 degrees;
- a final unfinished attempt reached approximately 68.8 degrees before reciprocal-scene cleanup;
- the 65-degree criterion itself has not been weakened.

## Current single hypothesis

The PIVOT controller has enough turn authority and speed, but its 96-tick ownership window expires shortly before measured lead capture. Extend only `MAX_PIVOT_TICKS` from 96 to 140 so the existing 65-degree criterion can be reached naturally.

Current experiment commit:

- `b4a03d2772ae43c3985eb5a3cb346b07ab216c0e`

Preserved behavior:

- 65-degree PIVOT completion criterion unchanged;
- 3-degree real firing gate unchanged;
- rear-target rejection unchanged;
- terrain, collision, line-of-sight, range, and friendly-fire checks unchanged;
- CAPTURE-entry lag-climb logic unchanged;
- no scripted firing or initial rear free shot.

## Next checks

1. Complete exactly one self-hosted `dogfight_mutual` run for `b4a03d27`.
2. Confirm the extended PIVOT actually reaches `Stage.CAPTURE`.
3. Confirm `energy_coupled_capture_entry_lag_start` is emitted at CAPTURE entry when its measured geometry qualifies.
4. Compare closure, horizontal error, altitude, and speed from entry-lag start through release or timeout.
5. Check both real fire counts, minimum/maximum separation, ground frames, and final A6M mission state.
6. If PIVOT still cannot reach 65 degrees, inspect whether horizontal error reaches a repeatable local minimum before changing any threshold.
7. If the P-47N fires while all safety conditions pass, repeat the exact commit before any cleanup or merge.

## Broader roadmap state

- The 24-base-aircraft, 66-livery-variant, 90-Entity-registration, and historical 26-benchmark-count mapping has already been documented; do not redo that inventory unless registrations change.
- PR #5, PR #6, and PR #8 are research history. Do not append new experiments to them.
- Do not begin the 14-fighter matrix, mission-order foundation, bombers, attackers, or torpedo behavior until reciprocal fighter combat is stable and the current experimental controls are consolidated behind a clear control-authority boundary.
