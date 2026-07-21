# AI development handoff

Last updated: 2026-07-22 (Asia/Tokyo)

## Read first

Follow the repository-wide limits and workflow in `/AGENTS.md`. This file records current project state; update it whenever a substantial AI coding session ends.

## Repository state

- `main` contains merged PR #4 at commit `8a91e7e44d8050505cd3ec948a2ed3c263ec342c`.
- PR #4 established doctrine-specific fighter combat, a neutral opposed opening, stale rear-threat release, fixed-gun rear-target rejection, and initial P-47N re-engagement safeguards.
- The remaining acceptance gap after PR #4 was `dogfight_mutual`: the A6M could fire, but the P-47N did not produce a legitimate firing event.

## Oversized research PR

- PR #5, `Recover energy fighters from stale defensive extensions`, is an open Draft research branch: `agent/energy-fighter-counterattack-recovery`.
- At the time of this handoff it had grown to roughly 40 commits, 12 changed files, and more than 2,000 added lines.
- Do **not** continue appending experiments to PR #5. Use it only for telemetry, artifacts, and comparison history.
- Its latest normal build passed, while the targeted `dogfight_mutual` qualification still failed.

## Findings worth preserving

1. The original P-47N failure was not a compile or weapon-API problem. It became trapped in defensive/extension control and failed to convert recovered separation into a forward firing solution.
2. Starting counterattack too late (around or beyond 200 blocks) causes useless large-radius re-entry.
3. A bounded high-yo-yo/reversal can bring the P-47N close to a valid nose solution.
4. A short final-alignment controller can produce legitimate A6M firing without weakening the actual 3-degree weapon gate.
5. Intermediate PR #5 revisions demonstrated each side firing separately:
   - one revision produced P-47N fire while A6M remained at zero;
   - another produced multiple A6M firing events while P-47N returned to zero.
6. Therefore the next problem is simultaneous coexistence and control-layer arbitration, not proving that either aircraft can ever fire.
7. UUID-dependent maneuver-side choices and uncontrolled opening variance can make runs diverge. Determinism must be checked before threshold tuning.
8. Keep both aircraft in ticking chunks during the reciprocal qualification; otherwise a distant participant may freeze or lose useful combat time.

## Safety and acceptance criteria

A candidate fix is not complete until a single run satisfies all of the following:

- neutral opposed opening; no initial rear free shot;
- A6M fires at least once through the real weapon manager;
- P-47N fires at least once through the real weapon manager;
- no fixed-gun firing at a target behind the aircraft;
- both aircraft perform autonomous attack and defensive behavior;
- no ground contact or aircraft collision;
- P-47N does not extend indefinitely outside the useful simulation area;
- after combat cleanup, the primary aircraft resumes the normal mission and returns/lands/parks;
- targeted scenario is repeated for stability before restoring the full regression matrix.

## Recommended next session

1. Create a clean branch from current `main`, not from PR #5.
2. Inspect PR #5 only to identify the smallest independently useful changes.
3. First focused hypothesis: deterministic arbitration between energy-fighter recovery and final alignment, with only one controller allowed to own a tick.
4. Limit the first patch to at most three production/test files and one targeted CI run.
5. If both-fire coexistence is not achieved after three materially different runs, stop and report rather than extending the PR.

## Useful references

- Merged baseline: `8a91e7e44d8050505cd3ec948a2ed3c263ec342c`
- Research PR: `#5`
- Research branch: `agent/energy-fighter-counterattack-recovery`
