# AI development handoff

Last updated: 2026-07-22 (Asia/Tokyo)

## Read first

Follow `/AGENTS.md`. GitHub-hosted Actions minutes are currently exhausted, so do not open a new pull request, rerun workflows, or push no-op commits to an existing pull request. Preserve unvalidated work on a non-PR branch until a local, self-hosted, or restored hosted runner is available.

## Current validated baseline

- Focused Draft PR #8: `Convert P-47N crossing into an oblique lag-yoyo`.
- PR branch: `agent/p47-oblique-lag-yoyo`.
- Last inspected head: `f5f96130d2dbc5dcaf5a5950c8135dd5e2bb61ec`.
- Normal benchmark build passed for that head.
- Targeted `dogfight_mutual` physically ran and preserved telemetry, but verification failed.
- A6M fire count: 4.
- P-47N fire count: 0.
- Minimum separation: 14.46 blocks.
- Maximum separation: 192.72 blocks.
- No ground frames were reported for the primary A6M; the disposable P-47N later entered an aborted stall-recovery state.

Do not merge PR #8. Reciprocal legitimate firing has not passed or repeated.

## Newly identified validation-harness failure

Commit `f5f96130` extended the reciprocal combat window from 1,000 to 2,000 ticks. The preserved telemetry shows that the ordinary validation mission continued advancing underneath combat control:

- A6M: `CRUISE_OUTBOUND -> TURN_LEFT -> CRUISE_CROSS -> TURN_RIGHT -> STALL_SETUP`, then `STALL_SETUP -> ABORTED` at server tick 2654.
- P-47N: progressed through the same base mission into `STALL_ENTRY` and `STALL_RECOVERY`, then `STALL_RECOVERY -> ABORTED` with ground contact at server tick 2226.
- The last reciprocal-scene status was only age 1,880 ticks, so the 2,000-tick scene never completed.
- Because the completion event was absent, the verifier reported zero aggregate tracking/combat ticks and no parked return even though the JSONL status events contained substantial tracking and combat control.

This is a test-harness self-interference bug, not evidence that the combat controller should be retuned.

## Parked no-CI implementation branch

- Branch: `agent/mutual-dogfight-mission-hold`.
- Based on PR #8 head `f5f96130`.
- Adapter commit: `715cea06d08f63a53e415aeff8cb38db265d8dcc`.
- Integration commit: `a59d9dc4ce84d92845328fbd0ef78e40b360fd59`.
- No pull request was opened, so no GitHub-hosted workflow was triggered.

The new test-only `MutualDogfightMissionHoldAdapter`:

- activates only for the `dogfight_mutual` scenario;
- requires the reciprocal-test aircraft name and exact red/blue mutual faction tags;
- rejects player pilots;
- holds only the background `AutopilotSession` phase at neutral `CRUISE_OUTBOUND` while combat tags are present;
- resets phase-local turn/stall counters so base-mission timeouts cannot abort either combat participant;
- does not alter combat input, weapon gates, terrain avoidance, collision avoidance, opening geometry, or firing safety;
- releases automatically when the scene clears the mutual faction tags, allowing the primary aircraft to resume its normal validation mission.

## Validation completed without Actions

- Repository source was checked to confirm the reflected fields exist:
  - `AutonomousFlightManager.SESSIONS`;
  - `AutonomousFlightManager$SessionEntry.session`;
  - `AutopilotSession.phase`, `phaseTicks`, `stableTicks`, `fallingTicks`, and `transitionReason`.
- A Java 17 stubbed syntax/type-shape compilation of the new adapter and mixin integration passed.
- Workflow lookup for commit `a59d9dc4` returned no runs.

This is not equivalent to the real Forge build or GameTest. Treat the branch as unvalidated and do not merge it.

## Required next checks when execution capacity returns

1. Run the normal benchmark build on `agent/mutual-dogfight-mission-hold`.
2. Run exactly one targeted `dogfight_mutual` GameTest.
3. Confirm both aircraft remain in the held cruise phase throughout the combat window; no turn/stall phase transitions should occur before scene completion.
4. Confirm the scene produces `mutual_dogfight_validation_completed`, cleans up the opponent, and the A6M resumes the normal mission and reaches `PARKED`.
5. Re-evaluate the actual remaining behavioral failure from the new telemetry.
6. Only if P-47N fire remains zero after the harness is valid, continue with one materially different combat hypothesis: release the powered wingover when closure has been removed while useful speed remains, then accelerate through measured-profile recovery rather than forcing a fixed full half-loop.

## Safety and acceptance criteria

A candidate is not complete until one run satisfies all of the following and the result is repeated:

- neutral opposed opening; no initial rear free shot;
- A6M fires at least once through the real weapon manager;
- P-47N fires at least once through the real weapon manager;
- no fixed-gun firing at a target behind the aircraft;
- both aircraft perform autonomous attack and defensive behavior;
- no ground contact or aircraft collision;
- minimum separation at least 8 blocks;
- maximum separation at most 480 blocks;
- P-47N remains inside the useful simulation area;
- after combat cleanup, the primary aircraft resumes the normal mission and returns, lands, and parks.

## Research history

- PR #5 remains oversized research only. Do not append new experiments.
- PR #6 is superseded research history.
- PR #8 remains the current combat-controller evidence branch, but the no-CI harness fix is parked separately until validation capacity returns.
