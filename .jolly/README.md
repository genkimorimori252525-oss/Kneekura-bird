# Jolly Research Mailbox

This directory is a low-token research handoff between Codex and Jolly (ChatGPT) using GitHub as the shared mailbox. It is designed for use without the OpenAI API and without Computer Use.

## Purpose

Codex should keep repository inspection, code reasoning, edits, tests, and small factual lookups local to the coding task. When a task needs broad external research that would otherwise consume a large amount of Codex context, Codex can write a compact request into `.jolly/inbox/` and stop. The repository owner can then tell Jolly `ジョリー、郵便箱`. Jolly reads pending requests, performs the external research, and writes compressed results into `.jolly/outbox/`.

This is a manual-trigger mailbox. A GitHub commit does not automatically wake Jolly.

## Directory layout

- `.jolly/inbox/` — Codex research requests.
- `.jolly/outbox/` — Jolly research results.
- `.jolly/archive/` — optional storage for completed old request/result pairs.
- `.jolly/templates/REQUEST.md` — request template for Codex.
- `.jolly/templates/RESULT.md` — result template for Jolly.

## Job naming

Use a collision-resistant filename:

`JOB-YYYYMMDD-HHMM-short-slug.md`

Example:

`JOB-20260827-0310-forge-headless-gametest.md`

The `id:` inside the file must match the filename without `.md`.

## Request lifecycle

1. Codex decides broad external research is worthwhile.
2. Codex creates one request in `.jolly/inbox/` with `status: pending`.
3. Codex reports the exact request path to the owner and stops broad web research for that question.
4. The owner tells Jolly `ジョリー、郵便箱` in ChatGPT.
5. Jolly reads all `status: pending` requests, researches them, and writes one matching result per request into `.jolly/outbox/`.
6. Jolly updates the original request to `status: completed` only after the corresponding outbox result exists.
7. When Codex resumes, it reads only the matching outbox file first. It may inspect cited sources itself only when implementation safety or ambiguity requires it.
8. Old pairs may later be copied or moved into `.jolly/archive/` for housekeeping.

## Status values

Request status:

- `pending` — waiting for Jolly.
- `researching` — optional transient marker while Jolly is working.
- `completed` — matching outbox result exists.
- `failed` — Jolly could not produce a reliable answer.
- `needs_context` — Jolly needs additional project-specific context before researching.

Result status:

- `completed`
- `partial`
- `failed`
- `needs_context`

## When Codex should delegate

Delegate when at least one of these is true:

- the answer likely requires comparing several external sources;
- the task asks for ecosystem-wide GitHub/project discovery;
- current versions, compatibility, recent issues, community experience, or changing documentation matter;
- the research would require reading several long pages, issue threads, papers, or repositories;
- the purpose of the research is to choose among multiple technical approaches.

Do not delegate merely to avoid normal coding work. Codex should directly handle:

- this repository's code, tests, diffs, logs, and documentation;
- questions answerable from files already in the repository;
- small single-source lookups when the answer is obvious and cheap to obtain;
- implementation and validation after the research result is returned.

## Token discipline

The mailbox exists to reduce Codex context use.

- A request should normally be under about 500 words.
- Do not paste large source files or logs into a request. Point to repository paths, commits, PRs, issues, or concise excerpts instead.
- `max_output_tokens` is a soft compression target for Jolly, not a correctness limit. Default: `2500`.
- Jolly should front-load the conclusion and implementation-relevant facts.
- Jolly should avoid repeating the request or providing tutorial-style background unless it changes the decision.

## Source discipline

Jolly results should distinguish verified facts from inference. For external claims that matter to implementation, include a source URL and enough context for Codex to verify the claim later. Prefer official documentation, primary repositories, maintainers' issue comments, standards, and first-party release notes. Community sources are useful for observed behavior but should not silently override primary sources.

## Safety and secrets

Never put passwords, API keys, cookies, tokens, private credentials, personal secrets, or machine secrets in mailbox files. Requests should contain only information appropriate to commit to this repository.

## Human trigger

The intended manual command is simply:

`ジョリー、郵便箱`

When that phrase is used, Jolly should inspect `.jolly/inbox/` in this repository, process every pending request that can be answered, write compressed results to `.jolly/outbox/`, and mark each successfully answered request completed.
