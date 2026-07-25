# Repository instructions for AI coding agents

These instructions apply to every AI-assisted GitHub session in this repository.

## Working relationship

- The repository owner expects the assistant to work directly through GitHub when access is available: inspect code and CI, create branches, commit focused changes, open pull requests, and merge only after the requested checks pass.
- Do not ask the owner to perform routine GitHub operations manually unless permissions or tooling genuinely block the action.
- Read this file and `docs/AI_HANDOFF.md` before changing code. Update the handoff at the end of every substantial session.

## Operating modes and scope limits

### Default bounded mode

- Stop an implementation loop after **60 minutes or 8 remote CI runs**, whichever happens first.
- At **30 minutes or 4 remote CI runs**, pause for an internal checkpoint: compare against the best known commit, confirm that the current hypothesis is still materially different, and report progress to the owner before continuing.
- At the final limit, report the current result, the exact failing acceptance condition, the best known commit, and the next single hypothesis. Do not keep tuning silently.

### Jolly Endurance Mode (`ジョリー長航続モード`)

- This mode is activated only when the repository owner explicitly asks for `長時間モード`, `長航続モード`, or `Jolly Endurance Mode`. Record activation and the exact starting checkpoint in `docs/AI_HANDOFF.md` and, when useful, the parent roadmap issue.
- While active, the default **60-minute / 8-run stop** and the requirement to pause for owner approval at **30 minutes / 4 runs** are suspended. Work may continue through multiple aircraft qualifications and multiple focused hypothesis cycles without waiting for another approval message.
- Keep evidence checkpoints at least every **4 remote CI runs** or at each major merge, qualification milestone, terminal failure, or change of hypothesis. Update the handoff and leave a human-readable Issue/PR marker, then continue automatically when the next action is already determined.
- There is no fixed total remote-run ceiling in this mode, but runs remain strictly serial: one immutable request, one active run, one recorded result. Never overlap self-hosted qualifications or create duplicate/no-op triggers.
- A repeated failure does not force the whole mode to stop. After the same meaningful failure occurs twice, stop threshold tuning, return to the best known commit, reconstruct the evidence, and continue only with a materially different design or determinism hypothesis.
- This mode removes duration and run-count limits only. It does **not** waive safety invariants, validation evidence, one-hypothesis-per-commit discipline, branch/PR discipline, or the 10-file / 800-line patch ceiling.
- This mode applies to the current interactive work and resumable GitHub checkpoints; it does not imply background or asynchronous assistant execution. Before an interaction ends, record the exact commit, run, result, and next action so the mode can resume safely on the next turn.
- Leave this mode when the owner explicitly stops it, the roadmap target is reached, access or runner capacity prevents meaningful progress, no materially different hypothesis remains, or a platform/tool boundary ends the current interaction.

### Rules shared by both modes

- One commit should test one behavioral hypothesis.
- If a proposed change is likely to exceed **10 files or 800 added/changed lines**, stop and split the design before implementation.
- Treat 10 files and 800 lines as hard ceilings, not targets. Prefer the smallest patch that can test the hypothesis.
- If the same failure occurs twice in default mode, stop changing thresholds and revisit the design or test determinism.
- If a previously passing metric regresses, return to the known-good commit before trying another behavior change.

## Branch and pull-request discipline

- Start work from the current `main` unless the handoff explicitly names another clean baseline.
- Use a new `agent/<focused-description>` branch for each focused fix.
- Do not keep adding experiments to an oversized draft pull request. Preserve it for evidence, then rebuild the smallest viable fix on a clean branch.
- Keep experimental/test-only adapters clearly separated from production behavior.
- Default to draft pull requests until focused validation succeeds.
- PR descriptions must state: root cause, exact behavior changed, safety invariants preserved, checks run, and remaining risks.

## Validation strategy

Run checks in this order:

1. Static inspection and local/deterministic checks available in the repository.
2. Normal build/compile.
3. One targeted headless scenario.
4. Repeat the targeted scenario only after a materially different hypothesis.
5. Full regression matrix only after the target scenario passes.

Do not use the expensive headless GameTest as the first diagnostic tool for every small threshold change. Add telemetry or deterministic assertions first when the cause is unclear.

## Validation-harness integrity

- Before attributing a targeted-scenario failure to aircraft control or combat behavior, prove that the harness reached its intended start, retained scenario ownership, emitted its completion event, performed cleanup, and released the surviving aircraft back to the base mission.
- Whenever a combat window, retry allowance, or scenario duration is increased, audit every enclosing limit: GameTest timeout, global mission timeout, phase-specific timeout, opponent lifetime, cleanup time, and the return/landing/parking budget. The scenario window must leave enough time for all acceptance-tail work.
- Check whether the ordinary validation mission continues advancing underneath scenario-specific control. If the scenario owns flight inputs, unrelated base phases such as turns, stall tests, return, or landing must be paused or shown to be explicitly compatible.
- Treat missing completion events, zero aggregate counters despite nonzero periodic status telemetry, premature cleanup, or aborts in unrelated base-mission phases as validation-harness failures first—not as evidence for retuning behavior thresholds.
- Reconstruct the exact tick order of scenario start, phase transitions, safety events, completion, cleanup, and terminal state before selecting the next behavioral hypothesis.
- Add explicit telemetry or deterministic assertions for scenario start, ownership, completion, release, and remaining mission-time budget whenever those facts are not already observable.
- Keep harness corrections isolated to test-only code. They must not weaken production firing gates, terrain avoidance, collision avoidance, player-control exclusion, or any acceptance criterion.

## Windows self-hosted runner operation

- The repository has a Windows self-hosted runner named `ジョリー`, normally rooted at `C:\actions-runner` and managed on the owner's PC through the desktop application `JollyRunnerHub.exe`.
- Route validation jobs require the labels `[self-hosted, Windows, X64]` and are defined in `.github/workflows/ww-local-route-validation.yml`.
- `JollyRunnerHub.exe` showing `Runner: 接続中` proves the local runner process is connected, but GitHub assignment is confirmed only when `.github/local-route-validation-status.json` records a new `run_id`, `status: in_progress`, the expected `event_sha`, requested ref, and aircraft.
- Before touching a validation request, read `.github/local-route-validation-status.json`, `.github/local-route-validation-request.txt`, recent commits, and the current handoff. Never assume an earlier request is still queued merely because the request file exists.
- Trigger one route qualification by changing `.github/local-route-validation-request.txt` exactly once to the immutable behavior commit and aircraft under test. Do not create no-op commits, duplicate requests, or edit the request while its run is in progress.
- The request file format is:

  ```text
  # human-readable purpose
  ref=<40-character behavior commit>
  aircraft=warfare_wings:<entity_id>
  ```

- A newly pushed request may take a short time before the start-status commit appears. Do not call the runner offline merely because the previous completed status remains visible during this assignment delay.
- `gradle/actions/setup-gradle@v4` may remain `in_progress` for several minutes on this runner. If the job is still alive, do not cancel or duplicate it solely because this setup step is slow.
- Follow one run through build, exact-physics GameTest, diagnostics upload, and finish-status persistence. A route qualification is accepted only when build and GameTest succeed, the verifier records the required route/mission/landing evidence, final state is `PARKED`, summary is 1/1, Gradle status is 0, and no crash report exists.
- On terminal failure, stop waiting immediately, fetch the job logs and artifact once, identify the first meaningful acceptance failure, record a human-readable checkpoint, and issue another run only for a materially different hypothesis or justified determinism check.
- The runner is an execution resource, not evidence by itself. Never claim a validation happened merely because the owner's PC and runner process are on.

## CI monitoring and owner reporting

- CI polling must be bounded. Check an in-progress workflow only a small number of times, then return a visible status checkpoint instead of silently repeating sleep-and-poll cycles.
- A workflow failure ends the waiting phase immediately. Switch to log and artifact analysis before starting another CI run.
- Do not push a new commit merely to escape an in-progress or failed workflow. First record the exact result of the current commit.
- Before the next behavioral hypothesis, report: current commit, build result, targeted scenario result, exact failing acceptance condition, preserved safety metrics, and the next single hypothesis.
- If CI is still running when the interaction must pause, explicitly state that it remains in progress and identify the run being watched.
- Never leave a tool call, polling message, or sleep operation as the final visible state of a work session. Close the session with a human-readable progress report.
- Assistant execution does not continue in the background after a response turn ends or the owner sends a new message. Before a long wait, record the exact branch, commit, workflow run, and next action in the PR/Issue or handoff; on resumption, read that marker and continue rather than assuming the previous tool loop is still active.
- GitHub email notifications and assistant-side CI monitoring are independent views of the same workflow. A failure email is not itself an assistant error; however, the assistant must still acknowledge and analyze that failure promptly.
- If the owner reports receiving a GitHub Actions failure email, treat it as strong evidence that the run reached a terminal failure state. Fetch that run once to confirm, stop polling immediately, and move to logs and artifacts.
- After a failure email or terminal CI result, do not issue another CI run until a human-readable checkpoint has been produced and the next materially different hypothesis has been identified.
- Distinguish a workflow failure from a GitHub connector or network failure. Retry a connector/network read at most once; if it still fails, report the access failure instead of silently polling. A workflow failure should not be retried without code or a justified determinism check.
- If new and previously runnable workflows fail before creating any steps or logs, check GitHub account usage or billing notifications before changing code. A 90% or 100% Actions-minutes email is an execution-capacity failure, not a code failure.
- Once the included Actions minutes are exhausted, stop triggering GitHub-hosted runs. Preserve the unvalidated commit and PR, record the exact last validated telemetry, and continue only with an available local or self-hosted validation path. Do not generate no-op commits or repeated reruns because they cannot start a runner.
- Never mark a PR ready or merge behavior changes while required checks are unexecuted because the Actions allowance is exhausted.

## Air-combat safety invariants

Never weaken these merely to make a qualification pass:

- no firing at a target behind the fixed forward guns;
- existing line-of-sight, range, friendly-fire, terrain, and collision checks remain authoritative;
- no initial rear free shot in the reciprocal dogfight qualification;
- both aircraft must remain valid autonomous participants, not scripted firing dummies;
- no ground contact or aircraft collision during the combat window;
- energy-fighter behavior must not escape indefinitely beyond the useful simulation area.

## Current project handoff

The detailed, updateable state is in `docs/AI_HANDOFF.md`. Treat old large draft PRs as research history, not automatically as the next coding baseline.