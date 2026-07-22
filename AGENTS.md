# Repository instructions for AI coding agents

These instructions apply to every AI-assisted GitHub session in this repository.

## Working relationship

- The repository owner expects the assistant to work directly through GitHub when access is available: inspect code and CI, create branches, commit focused changes, open pull requests, and merge only after the requested checks pass.
- Do not ask the owner to perform routine GitHub operations manually unless permissions or tooling genuinely block the action.
- Read this file and `docs/AI_HANDOFF.md` before changing code. Update the handoff at the end of every substantial session.

## Mandatory time and scope limits

- Stop an implementation loop after **60 minutes or 8 remote CI runs**, whichever happens first.
- At **30 minutes or 4 remote CI runs**, pause for an internal checkpoint: compare against the best known commit, confirm that the current hypothesis is still materially different, and report progress to the owner before continuing.
- At the final limit, report the current result, the exact failing acceptance condition, the best known commit, and the next single hypothesis. Do not keep tuning silently.
- One commit should test one behavioral hypothesis.
- If a proposed change is likely to exceed **10 files or 800 added/changed lines**, stop and split the design before implementation.
- Treat 10 files and 800 lines as hard ceilings, not targets. Prefer the smallest patch that can test the hypothesis.
- If the same failure occurs twice, stop changing thresholds and revisit the design or test determinism.
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
