# AI development handoff

Last updated: 2026-07-25 (Asia/Tokyo)

Follow `/AGENTS.md` before changing code. Live GitHub state overrides older notes.

## Current production baseline

PR #53 is merged and provides live owned-route guidance below terrain, collision, combat, emergency, and player-control authority.

Windows self-hosted run `30106085402` passed the A6M exact-physics proof:

- ordered waypoint progression `3,2,1,0`;
- route proposal followed by terrain override in the same tick;
- no ordinary mission phase advancement during route ownership;
- no ground contact during route guidance;
- release to ordinary mission;
- return, landing, braking, and final `PARKED`;
- no crash reports.

## Representative-matrix research history

Experimental Draft PR #57 was closed without merge after reaching its 8-run limit.

Useful evidence retained there:

- A6M run `30110401857`: generalized route proof passed and ended `PARKED`;
- B-17 runs `30111253908` and `30112101949`: base mission ended `PARKED`, but a flat artificial wall was not a valid heavy-aircraft terrain-proof design;
- G4M run `30112520940`: legacy metadata recovered `role=torpedo_bomber`, common-flight admission worked, route progressed `3,2,1,0`, and ordinary mission resumed, but the long representative route caused `return_to_pattern_timeout` about 175 blocks from the runway;
- IL-2 representative proof was not run.

Do not reopen or merge PR #57. Treat it only as telemetry evidence.

## Active focused work

Draft PR #58, branch `agent/g4m-compact-owned-route`, head `7b5471b1cd4b9402a18d3fa1ec4321a0110f87b9`.

Focused hypothesis:

> Keeping all production timeouts and safety thresholds unchanged, shortening only the G4M test route to `leg=145` should preserve `torpedo_bomber` role admission, ordered four-waypoint execution, ordinary mission release, return, landing, and final `PARKED`.

PR #58 changes six files:

- normalizes and admits `torpedo_bomber` to common noncombat autonomous flight;
- applies the existing heavy-aircraft turn-floor bound;
- restores G4M's torpedo-bomber role when legacy public runtime data lacks the optional `ai` block;
- adds a compact G4M-only route from live `CRUISE_OUTBOUND` position;
- keeps A6M's existing terrain-precedence proof unchanged;
- adds deterministic role-admission and unknown-role exclusion GameTests;
- requires G4M role evidence, waypoint sequence `3,2,1,0`, release, and a passed terminal mission.

Validation request commit on `main`: `61310e57a4315c8fd11837ae69bc800987dc5836`.
Requested exact head: `7b5471b1cd4b9402a18d3fa1ec4321a0110f87b9`, aircraft `warfare_wings:g4m`, scenario `full`, GameTests enabled.

At this handoff update, the status file still showed completed run `30112520940`; no new run-start record had appeared. Do not issue a duplicate request. First reread `.github/local-flight-validation-status.json` and recent Actions/start commits.

## Preserved invariants

- player-controlled aircraft receive no AI input;
- terrain, collision, combat, and emergency control remain above route guidance;
- there is still one final aircraft-input write;
- noncombat route orders do not grant weapon authority;
- fixed-gun, line-of-sight, range, friendly-fire, and minimum 8-block separation rules are unchanged;
- no return timeout or safety threshold was relaxed.

## Next exact action

1. Check whether the Windows runner accepted PR #58 exact head.
2. If a run exists, inspect build and exact-physics artifacts once.
3. Merge only if G4M profile is `torpedo_bomber`, waypoint progression is `3,2,1,0`, ordinary mission resumes, final state is `PARKED`, and crash reports are absent.
4. If it fails, record the exact remaining distance/phase without changing the return timeout.
5. After G4M is isolated and merged, create separate focused work for B-17 open-gate terrain qualification, then IL-2 representative route proof.
