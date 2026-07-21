# AI development handoff

Last updated: 2026-07-22 (Asia/Tokyo)

## Read first

Follow the repository-wide limits and workflow in `/AGENTS.md`. Current hard limits are 60 minutes, 8 remote CI runs, 10 changed files, and 800 added/changed lines, with a mandatory midpoint checkpoint at 30 minutes or 4 CI runs.

## Repository state

- `main` contains merged PR #4 at commit `8a91e7e44d8050505cd3ec948a2ed3c263ec342c`.
- PR #4 established doctrine-specific fighter combat, a neutral opposed opening, stale rear-threat release, fixed-gun rear-target rejection, and initial P-47N re-engagement safeguards.
- The remaining acceptance gap is still `dogfight_mutual`: the A6M fires legitimately, but the P-47N has not yet produced a firing event in the same passing run.

## Active focused PR

- PR #6: `Add bounded P-47N re-engagement`
- Draft branch: `agent/mutual-p47-counterattack-minimal`
- Current head: `ba7e14a3fc25e4ccda84fd9e849b37f8de6ea34c`
- Current scope: 3 changed files and fewer than 800 added lines.
- Normal benchmark build and deterministic simulation pass.
- The latest targeted `dogfight_mutual` run completed physically and preserved all safety/mission requirements, but failed only because the P-47N did not fire.
- Keep PR #6 Draft. Do not merge until reciprocal firing passes and is repeated for stability.

### Current PR #6 files

- `EnergyFighterReengagementAdapter.java`
- `EnergyFighterForwardAlignmentAdapter.java`
- `VehicleEntityBenchmarkMixin.java`

## Latest run: CI attempt 8

Commit: `ba7e14a3fc25e4ccda84fd9e849b37f8de6ea34c`

- A6M fire count: 4
- P-47N fire count: 0
- minimum separation: 10.11 blocks
- maximum separation: 158.44 blocks
- A6M ground frames: 0
- P-47N ground frames: 0
- A6M combat-control ticks: 994
- P-47N combat-control ticks: 450
- primary mission returned to a passing parked result
- only verifier error: `P-47N never fired at the A6M`

The corrected control-sign mapping worked: during the main re-entry, the P-47N reduced raw target angle from `126.65°` to a best observed `83.31°`, while closing from about 88 blocks to about 62 blocks. It then continued the fixed crossing turn, passed the best geometry, and the angle worsened again. The controller never reached its fixed `60°` handoff threshold.

## Next single hypothesis

Do not tune the opening or weaken collision/weapon safety. The next focused change should add an **adaptive handoff from CROSSING to APPROACH** when all of the following are true:

- the raw target angle has entered approximately the `83–90°` sector;
- the angle has stopped improving for a short measured window;
- range is still useful and closure is positive;
- no credible firing threat has been restored.

The purpose is to hand control to the existing offensive manager at the measured best crossing geometry instead of forcing the P-47N to continue toward an unreachable fixed `60°` threshold. Test this as one hypothesis. Do not simultaneously change opening geometry, collision thresholds, or actual firing gates.

## Findings worth preserving

1. The P-47N failure is not a compile, armament, or target-acquisition problem. It is a control-layer and re-entry-geometry problem.
2. Starting recovery beyond roughly 155 blocks is too late; attempts around or beyond 200 blocks created useless large-radius returns.
3. The original shortest-turn/control sign (`-1` for the observed negative target roll) improves geometry. The opposite sign increased the target angle toward 175 degrees.
4. A fixed continued turn can improve the target angle into the low-80-degree sector, but it later overshoots. This supports adaptive stage handoff rather than another turn-sign flip.
5. Opening-offset experiments are closed:
   - lateral 75 produced an unsafe 6.6-block minimum separation;
   - lateral 110 avoided collision prediction but caused separation beyond 700 blocks;
   - retain the merged 55-block neutral opening.
6. Collision avoidance must remain authoritative. The standard opening predicts a close crossing and may own the first pass; do not bypass it merely to obtain a firing event.
7. PR #5 demonstrated that either aircraft can fire separately, but it mixed too many controllers. Continue with PR #6 or a clean successor, not by appending to PR #5.
8. The latest run proves simultaneous coexistence is close: A6M firing and safe P-47N re-entry occur in one run; only the P-47N final conversion remains.

## Oversized research PR

- PR #5, `Recover energy fighters from stale defensive extensions`, remains an open Draft research branch: `agent/energy-fighter-counterattack-recovery`.
- It grew to roughly 40 commits, 12 changed files, and more than 2,000 added lines.
- Do **not** continue appending experiments to PR #5. Use it only for telemetry, artifacts, and comparison history.

## Safety and acceptance criteria

A candidate fix is not complete until a single run satisfies all of the following:

- neutral opposed opening; no initial rear free shot;
- A6M fires at least once through the real weapon manager;
- P-47N fires at least once through the real weapon manager;
- no fixed-gun firing at a target behind the aircraft;
- both aircraft perform autonomous attack and defensive behavior;
- no ground contact or aircraft collision;
- minimum separation remains at least 8 blocks;
- maximum separation remains at most 480 blocks;
- P-47N does not extend indefinitely outside the useful simulation area;
- after combat cleanup, the primary aircraft resumes the normal mission and returns/lands/parks;
- targeted scenario is repeated for stability before restoring the full regression matrix.

## Useful references

- Merged baseline: `8a91e7e44d8050505cd3ec948a2ed3c263ec342c`
- Active focused PR: `#6`
- Active branch: `agent/mutual-p47-counterattack-minimal`
- Current focused head: `ba7e14a3fc25e4ccda84fd9e849b37f8de6ea34c`
- Best latest artifact run: workflow `29854004753`, results artifact `8504577377`
- Research PR: `#5`
- Research branch: `agent/energy-fighter-counterattack-recovery`
