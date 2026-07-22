# Windows self-hosted validation runner

This repository can run the expensive Forge build and `dogfight_mutual` GameTest on the owner's Windows 11 PC without using GitHub-hosted runner minutes.

## Safety boundary

- The runner is started manually with `run.cmd` and is not installed as a service initially.
- The workflow never shuts down, restarts, sleeps, or otherwise controls the PC.
- No inbound firewall or Minecraft server port is required.
- The workflow accepts jobs only on labels `self-hosted`, `Windows`, `X64`, and `ww-local`.
- Automatic `push` and `pull_request` execution is prohibited because this is a public repository.
- Issue-command execution is accepted only from GitHub user `genkimorimori252525-oss`, only on Issue #7, and only when the comment begins with `/validate-local`.
- Checkout uses `persist-credentials: false`.

## Runner registration

In the repository UI, open:

`Settings -> Actions -> Runners -> New self-hosted runner`

Select Windows and x64. Use the current commands and short-lived registration token displayed by GitHub.

During configuration use:

- runner name: `ww-local-runner`
- additional label: `ww-local`
- work folder: `_work`
- run as a service: no

Never paste the registration token into the repository, an Issue, or a chat message.

## Start and stop

Start the runner only when validation is needed:

```powershell
Set-Location C:\Users\genki\actions-runner
.\run.cmd
```

Keep the window open until the job finishes. `Connected to GitHub` and `Listening for Jobs` indicate that the runner is ready.

After diagnostics have uploaded, press `Ctrl+C` to take the runner offline. This does not shut down the PC.

## Validation commands

The workflow can be started from the Actions page through `workflow_dispatch`, or through an owner-only command on Issue #7.

Default targeted run:

```text
/validate-local ref=agent/mutual-dogfight-mission-hold aircraft=warfare_wings:a6m gametest=true
```

Build and deterministic simulation only:

```text
/validate-local ref=agent/mutual-dogfight-mission-hold aircraft=warfare_wings:a6m gametest=false
```

Accepted arguments:

- `ref=`: same-repository branch, tag, or commit
- `aircraft=`: namespaced aircraft entity id
- `gametest=`: `true` or `false`

Unknown arguments and unsafe characters fail before checkout.

## What the workflow runs

1. Resolve and validate the request.
2. Checkout the requested same-repository ref without persisted credentials.
3. Set up Java 17, Python 3.12, and Gradle 8.8.
4. Run the normal benchmark build and deterministic flight simulation.
5. Download the exact runtime aircraft mods when missing.
6. Run the real-physics `dogfight_mutual` GameTest when requested.
7. Verify the scenario and render HTML diagnostics.
8. Upload build logs, JSON/JSONL telemetry, crash reports, flight profiles, and diagnostics even when the verifier fails.

Workflow file:

`.github/workflows/ww-local-self-hosted-validation.yml`
