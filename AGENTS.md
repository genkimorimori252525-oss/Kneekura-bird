# Repository instructions for AI coding agents

These instructions apply to every AI-assisted GitHub session in this repository.

## Working relationship

- The repository owner expects the assistant to work directly through GitHub when access is available: inspect code and CI, create branches, commit focused changes, open pull requests, and merge only after the requested checks pass.
- Do not ask the owner to perform routine GitHub operations manually unless permissions or tooling genuinely block the action.
- Read this file and `docs/AI_HANDOFF.md` before changing code. Update the handoff at the end of every substantial session.

## Mandatory time and scope limits

- Stop an implementation loop after **20 minutes or 3 remote CI runs**, whichever happens first.
- At the limit, report the current result, the exact failing acceptance condition, the best known commit, and the next single hypothesis. Do not keep tuning silently.
- One commit should test one behavioral hypothesis.
- If a proposed change is likely to exceed **5 files or 500 added/changed lines**, stop and split the design before implementation.
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
