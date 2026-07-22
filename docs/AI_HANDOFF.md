# AI development handoff

Last updated: 2026-07-22 (Asia/Tokyo)

## Read first

Follow `/AGENTS.md` before changing code. GitHub-hosted Actions minutes are exhausted. Do not rerun hosted workflows, create no-op commits, mark an unvalidated PR ready, or merge behavior changes without the required build and GameTest evidence.

## Current combat-AI state

- The remaining qualification is `dogfight_mutual`.
- A6M has fired legitimately in preserved runs.
- P-47N has not yet fired legitimately in the same safe passing run.
- PR #8 remains evidence only and must not be merged yet.
- The last inspected PR #8 head was `f5f96130d2dbc5dcaf5a5950c8135dd5e2bb61ec`.
- That head passed the normal benchmark build, but its targeted GameTest failed verification.

## Validation-harness fault found after PR #8

The reciprocal combat window was increased from 1,000 to 2,000 ticks while the ordinary validation mission continued advancing underneath combat control.

Observed consequences:

- A6M advanced through unrelated turn and stall-test phases and later aborted.
- P-47N entered the ordinary stall sequence, reached stall recovery, contacted the ground, and aborted.
- The reciprocal scene stopped before its own 2,000-tick completion.
- Periodic telemetry contained real tracking and combat activity, while aggregate values were reported as zero because the completion event never occurred.

Treat this as validation-harness self-interference, not evidence for another combat threshold change. Apply the repository-wide `Validation-harness integrity` rules in `/AGENTS.md` before selecting any new behavior hypothesis.

## Parked harness correction

Non-PR branch:

- `agent/mutual-dogfight-mission-hold`
- current recorded head: `c85b0bd53a8c8f3fb8b2633f15b43c857471dea4`

The test-only `MutualDogfightMissionHoldAdapter` holds the background validation session in neutral cruise while reciprocal combat tags are present. It does not alter combat control, firing gates, terrain avoidance, collision avoidance, player exclusion, or opening geometry.

Completed without GitHub-hosted Actions:

- reflected field names were checked against repository source;
- Java 17 stubbed syntax/type-shape validation passed;
- no pull request was opened;
- no workflow was triggered.

This branch still requires the real Forge build and one targeted `dogfight_mutual` GameTest before it can be judged.

## Google Cloud validation runner preparation

Infrastructure branch:

- `agent/gcp-self-hosted-validation`
- workflow commit: `205fea914922f4c5fc2c2163b425667a225dae05`
- setup guide commit: `7a355ff6f68720feb1d5af8e4ebdafc1acab001f`

Files:

- `.github/workflows/ww-gcp-self-hosted-validation.yml`
- `docs/GCP_SELF_HOSTED_VALIDATION.md`

The workflow is deliberately manual-only and restricted to GitHub actor `genkimorimori252525-oss`. It targets a runner with labels:

- `self-hosted`
- `linux`
- `x64`
- `ww-gcp`

The workflow:

1. checks out a requested same-repository ref with credentials disabled;
2. runs the normal benchmark build and deterministic simulation;
3. preserves build diagnostics;
4. optionally downloads the exact runtime aircraft mods;
5. runs and verifies `dogfight_mutual` using real Forge physics;
6. uploads JSONL, logs, verifier JSON, HTML diagnostics, reports, and jars;
7. schedules the Google Cloud VM to shut down after artifact upload.

The workflow currently exists only on the infrastructure branch. GitHub shows the `Run workflow` button only after the workflow is present on the default branch. Do not merge it until the Google Cloud VM and self-hosted runner registration are ready for review.

## Recommended initial Google Cloud machine

- Compute Engine standard VM for the first stable runs
- Osaka region, preferably an available `asia-northeast2` zone
- `e2-standard-4`: 4 vCPU and 16 GB RAM
- Debian 12 x86_64
- 60 GB `pd-balanced` or larger
- no GPU
- no broad Google Cloud service account
- no HTTP, HTTPS, or Minecraft server firewall exposure
- GitHub runner service label `ww-gcp`

Begin with a standard VM. Consider Spot only after interrupted-job handling and artifact preservation are proven.

## Required next actions

1. Create the Google Cloud project and enable billing and Compute Engine.
2. Create the VM using the settings in `docs/GCP_SELF_HOSTED_VALIDATION.md`.
3. Install Java 17, Git, Python 3, and the GitHub self-hosted runner.
4. Register the runner with label `ww-gcp` and install it as a system service.
5. Confirm the runner appears Online in repository settings.
6. Review and merge only the GCP workflow and setup documentation to `main`.
7. Dispatch the workflow for ref `agent/mutual-dogfight-mission-hold`.
8. Start the VM if it is offline.
9. Confirm the normal build succeeds.
10. Run exactly one targeted `dogfight_mutual` test and inspect whether the harness now starts, owns, completes, cleans up, releases, and returns the A6M to `PARKED`.
11. Only after the harness is valid, evaluate the remaining P-47N behavior from the new telemetry.

## Safety and acceptance criteria

Do not complete or merge the combat work until one run satisfies all of the following and the targeted result is repeated:

- neutral opposed opening and no initial rear free shot;
- A6M fires through the real weapon manager;
- P-47N fires through the real weapon manager;
- no fixed-gun firing at a target behind the aircraft;
- both aircraft perform autonomous attack and defensive behavior;
- no ground contact or aircraft collision;
- minimum separation at least 8 blocks;
- maximum separation at most 480 blocks;
- P-47N remains inside the useful simulation area;
- the reciprocal scene emits completion and cleanup events;
- the primary aircraft resumes the ordinary mission, returns, lands, brakes, and reaches `PARKED`.

## Research history

- PR #5 is oversized research only. Do not append experiments.
- PR #6 is superseded research history.
- PR #8 remains the current combat-controller evidence branch, not a merge candidate.
