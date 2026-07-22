# AI development handoff

Last updated: 2026-07-22 (Asia/Tokyo)

## Read first

Follow `/AGENTS.md` before changing code. GitHub-hosted Actions minutes are currently exhausted. Do not rerun hosted workflows, create no-op commits, mark unvalidated behavior ready, or merge required-check changes without an available execution path.

The selected replacement execution path is the owner's Windows 11 PC running an on-demand self-hosted GitHub Actions runner. The earlier Google Cloud plan is superseded and retained only as design history.

## Current validated combat baseline

- Focused Draft PR #8: `Convert P-47N crossing into an oblique lag-yoyo`.
- PR branch: `agent/p47-oblique-lag-yoyo`.
- Last inspected head: `f5f96130d2dbc5dcaf5a5950c8135dd5e2bb61ec`.
- Normal benchmark build passed for that head.
- Targeted `dogfight_mutual` physically ran and preserved telemetry, but verification failed.
- A6M fire count: 4.
- P-47N fire count: 0.
- Minimum separation: 14.46 blocks.
- Maximum separation: 192.72 blocks.
- The disposable P-47N later entered an aborted stall-recovery state.

Do not merge PR #8. Reciprocal legitimate firing has not passed or repeated.

## Validation-harness failure discovered after PR #8

Commit `f5f96130` extended the reciprocal combat window from 1,000 to 2,000 ticks. Preserved telemetry proved that the ordinary validation mission continued advancing underneath combat control:

- A6M advanced through normal turn phases into `STALL_SETUP`, then aborted before scene completion.
- P-47N advanced into `STALL_ENTRY` and `STALL_RECOVERY`, then aborted with ground contact.
- The reciprocal scene reached only age 1,880 ticks and never emitted its completion event.
- The verifier therefore reported zero aggregate tracking/combat counters despite nonzero periodic telemetry.

This is a validation-harness self-interference bug, not evidence for further combat-threshold tuning.

Repository-wide `/AGENTS.md` now requires harness start, ownership, completion, cleanup, release, and complete time-budget validation before aircraft behavior is retuned.

## Parked harness-fix branch

- Branch: `agent/mutual-dogfight-mission-hold`.
- Based on PR #8 head `f5f96130`.
- Adapter commit: `715cea06d08f63a53e415aeff8cb38db265d8dcc`.
- Integration commit: `a59d9dc4ce84d92845328fbd0ef78e40b360fd59`.
- Repository-rule sync commit: `09ee7cf3a276a21d7a4c3d4b2d26ba5c4c2b851d`.
- Handoff commit: `c85b0bd53a8c8f3fb8b2633f15b43c857471dea4`.
- No pull request was opened and no GitHub-hosted workflow was triggered.

The test-only `MutualDogfightMissionHoldAdapter` activates only for `dogfight_mutual`, exact reciprocal test tags, and mob pilots. It holds the background `AutopilotSession` in neutral cruise while combat owns flight input, then releases automatically when combat tags are cleared. It does not weaken combat input, weapon gates, terrain avoidance, collision avoidance, player-control exclusion, opening geometry, or acceptance criteria.

Static field inspection and a Java 17 stubbed syntax/type-shape compilation passed. This is not equivalent to the real Forge build or GameTest; the branch remains unvalidated.

## Windows self-hosted validation infrastructure

- Infrastructure branch: `agent/windows-self-hosted-validation`.
- Workflow: `.github/workflows/ww-local-self-hosted-validation.yml`.
- Setup guide: `docs/WINDOWS_SELF_HOSTED_VALIDATION.md`.
- Workflow commit: `edb8b2686f12be6d303cab99123a1ab4858e4bc5`.
- Guide commit: `a0cd6c61ac11ee293855bc5ea92cef4ec20b670b`.

The workflow is manual-only and restricted to GitHub actor `genkimorimori252525-oss`. It requires a Windows x64 self-hosted runner with the dedicated label `ww-local`. It checks out a requested same-repository ref with persisted credentials disabled, sets up Java 17, Python, and Gradle 8.8, runs the normal build and deterministic simulation, optionally runs `dogfight_mutual`, verifies the result, renders diagnostics, and uploads artifacts.

The Windows workflow does not shut down, restart, sleep, or otherwise control the owner's PC. The runner should initially be started manually with `run.cmd` only for a requested validation and stopped with `Ctrl+C` afterward.

The workflow exists only on a non-PR infrastructure branch. It will not be visible for normal dispatch until this reviewed infrastructure change reaches the default branch. Do not open a PR or merge it until the local runner is registered and the workflow has been reviewed for personal-PC safety.

## Superseded Google Cloud plan

- Historical branch: `agent/gcp-self-hosted-validation`.
- Do not merge or run its GCP-specific workflow on the owner's PC.
- In particular, its final VM-shutdown command is appropriate only to a disposable cloud VM, never a personal machine.

## Required next steps

1. On the owner's Windows PC, create a dedicated runner directory containing no personal files.
2. In repository settings, register a Windows x64 self-hosted runner named `ww-local-runner` with additional label `ww-local`.
3. Do not install it as a Windows service initially; run it manually in the foreground with `run.cmd`.
4. Review and merge only the Windows infrastructure workflow to the default branch.
5. Start the runner and dispatch one build-only validation first with `run_gametest=false`.
6. If the build and deterministic simulation pass, dispatch exactly one `dogfight_mutual` run against `agent/mutual-dogfight-mission-hold`.
7. Confirm both aircraft remain out of unrelated turn/stall phases, the scene emits completion and cleanup, and the A6M resumes the normal mission and reaches `PARKED`.
8. Only after the harness is proven valid may the actual remaining P-47N firing behavior be changed.

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
- PR #8 remains the current combat-controller evidence branch but must not be merged.
