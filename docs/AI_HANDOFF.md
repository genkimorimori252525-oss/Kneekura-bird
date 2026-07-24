# AI development handoff

Last updated: 2026-07-24 (Asia/Tokyo)

## Read first

Follow `/AGENTS.md` before changing code. Current GitHub state, merged commits, open PRs, and terminal workflow results override older notes in this file.

## Current production baseline

- Current `main`: `07bca5c7cd8eeec6d93b0fb49de6e63999fbc788`.
- PR #21 enabled measured-profile noncombat autonomous flight for level bombers.
- PR #25 enabled the same common noncombat flight path for measured attacker profiles.
- PR #27 merged the immutable `MissionOrder` model, all 11 roadmap order types, and the UUID/revision-guarded `MissionOrderManager`.
- PR #30 merged mission-order persistence across server save/load.
- PR #33 merged immutable ordered `WaypointRoute` state and deterministic progression contracts.
- PR #35 merged mission-owned route assignment guarded by aircraft UUID, mission revision, and immutable order ID.
- PR #37 merged the strict `WaypointRouteCodec` NBT boundary.
- PR #40 merged persisted mission-owned route progress with startup reconciliation against the restored `MissionOrderManager` state.
- `ControlAuthorityArbiter` is already integrated. Do not create a second authority dispatcher.
- Reciprocal A6M/P-47N combat qualification is complete. Do not retune it unless a later change produces a measured regression.
- Fighter targeting, defensive manoeuvre, re-engagement, and weapon authority remain fighter-only.
- Bombers, attackers, and G4M currently have common noncombat flight authority only. Strike, ground-attack, dive-bomb, and torpedo execution are not implemented.

## Validated route milestones

- PR #33 source head `7b143461340b09ea5d7bb70435b4d8af91d812be` passed Windows self-hosted run `30084768763`:
  - normal build passed;
  - deterministic autonomous-flight simulation passed 12/12;
  - WaypointRoute and existing MissionOrder GameTests passed;
  - A6M real-physics `full` reached `PARKED` in 4,326 ticks;
  - scenario verifier passed 1/1;
  - crash reports none.
- PR #35 source head `ace291215d46a78883bb0b919897c7100fd130c3` passed run `30086917681`:
  - build and deterministic simulation passed;
  - all 9 required GameTests passed;
  - A6M real-physics `full` reached `PARKED` in 4,326 ticks;
  - crash reports none.
- PR #37 source head `56d162c534ae6d3a3e07413f9941d3a8b5828961` passed run `30087664398`:
  - build and deterministic simulation passed;
  - all 11 required GameTests passed;
  - A6M real-physics `full` reached `PARKED` in 4,326 ticks;
  - crash reports none.
- PR #40 source head `04bbdebfbc0f02562c90db84cf94fbc10f5fbd75` passed run `30088761510`:
  - build passed;
  - deterministic simulation passed 12/12, all final `PARKED`;
  - all 13 required GameTests passed, including persistence and reconciliation contracts;
  - A6M real-physics `full` reached `PARKED` in 4,326 ticks;
  - final mission summary passed 1/1;
  - crash reports none.

## Current open work

Draft PR #41, `Plan pure waypoint guidance from route intent`:

- head: `c6e84e53263924129d3a3c52fdaad00ad749bfab`;
- clean diff: two new files, 211 lines;
- pure calculation only;
- advances at most one reached waypoint per call;
- returns normalized horizontal bearing, waypoint altitude, caller-supplied measured-profile target speed, horizontal distance, and vertical error;
- preserves current horizontal heading for vertically aligned waypoints;
- completed routes expose no active target;
- no connection to `AutonomousFlightManager`, `AutopilotSession`, `ControlAuthorityArbiter`, weapons, terrain avoidance, collision avoidance, or live flight input.

GitHub-hosted runs `30089744004` and `30089744009` ended as zero-step failures. Treat them as hosted-capacity failures, not source failures.

The current files on `main` do not show a Windows self-hosted validation request or result for PR #41. The request/status files currently contain older data. Do not issue duplicate or speculative GameTest requests while runner availability is unconfirmed. When the runner is confirmed online, validate exact head `c6e84e53263924129d3a3c52fdaad00ad749bfab` once with normal build, deterministic simulation, all expected mission/route/guidance GameTests, and one A6M real-physics `full` regression.

## Validation capacity and runner handling

- GitHub-hosted Actions minutes are exhausted. Zero-step hosted failures are capacity failures, not code failures.
- Do not infer Windows runner availability from stale request/status files.
- While the Windows runner is offline or unconfirmed, do not create or repeat self-hosted GameTest requests.
- Prefer static inspection, deterministic contracts, documentation, and disconnected data/planning foundations during runner downtime.
- Record a pending validation head and exact restart action once in the PR or Issue; do not repeat the same checkpoint every run.

## Preserved safety invariants

Never weaken these to make a validation pass:

- player-controlled aircraft receive no AI flight input;
- fixed forward guns never fire at a target behind the aircraft;
- line-of-sight, range, friendly-fire, terrain, and collision checks remain authoritative;
- reciprocal dogfight minimum separation remains at least 8 blocks;
- no ground contact or aircraft collision during combat qualification;
- bombers and attackers do not inherit fighter targeting, defensive manoeuvre, re-engagement, or fixed-gun combat authority;
- an aircraft without an explicit attack-capable mission order does not attack by default;
- enabling a role for noncombat flight does not silently enable its weapons.

## Next exact workflow

1. Confirm Windows self-hosted runner availability without creating a new request.
2. If a PR #41 run already exists, inspect that run and artifacts rather than rerunning it.
3. Otherwise, when the runner is confirmed online, request exactly one validation for head `c6e84e53263924129d3a3c52fdaad00ad749bfab`.
4. If validation succeeds, update PR #41 with the exact run, mark Ready, and squash merge.
5. After PR #41 merges, create a separate small PR for the first live integration adapter.
6. The first adapter must be limited to one noncombat order and must route through existing control authority and terrain/collision safety layers.
7. Prefer `RETURN_TO_BASE` or `HOLD_POSITION`; do not enable weapons or strike behaviour in the same PR.
8. Add explicit telemetry proving route ownership, guidance selection, authority grant, safety override precedence, release, and return to the ordinary landing/parking tail.

## Useful references

- parent roadmap: Issue #7;
- merged mission-order foundation: PR #27;
- merged mission-order persistence: PR #30;
- merged route model: PR #33;
- merged route ownership: PR #35;
- merged route codec: PR #37;
- merged route persistence: PR #40;
- current guidance Draft: PR #41;
- passing fighter regression: run `30050199123`;
- passing G4M common-flight validation: run `30050488243`.
