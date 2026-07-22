# Windows self-hosted validation runner

This document configures the owner's Windows 11 PC as an on-demand GitHub Actions self-hosted runner for the expensive Forge build and `dogfight_mutual` GameTest. It avoids GitHub-hosted runner-minute usage while preserving the existing workflow, logs, artifacts, and verification scripts.

The runner is intentionally manual:

1. Start the runner with `run.cmd` only when validation is needed.
2. Dispatch the owner-only workflow from GitHub.
3. The PC checks out the requested same-repository ref.
4. Build, deterministic simulation, GameTest, verification, and artifact upload run locally.
5. Close the runner window after the job completes.

The workflow does not shut down, restart, sleep, or otherwise control the PC.

Do not attach this runner to automatic `push` or `pull_request` workflows. The repository is public, and untrusted pull-request code must never run on a personal machine.

## PC requirements

- Windows 11 x64
- At least 16 GB RAM; 32 GB is preferred for this repository
- Adequate free disk space for Gradle caches, Minecraft assets, Forge runs, logs, and artifacts
- Stable outbound HTTPS access to GitHub, Gradle/Maven repositories, Mojang assets, and Modrinth
- No inbound firewall port or Minecraft server port is required

The workflow installs its required Java, Python, and Gradle toolchains through GitHub setup actions. Git and PowerShell must be available on the PC.

## Create a dedicated runner directory

Use a directory that contains no personal documents, for example:

```powershell
New-Item -ItemType Directory -Force C:\ww-actions-runner | Out-Null
Set-Location C:\ww-actions-runner
```

Do not place the runner under Downloads, Documents, OneDrive, the game installation directory, or an existing development checkout.

## Register the GitHub runner

In the repository UI, open:

`Settings -> Actions -> Runners -> New self-hosted runner`

Select Windows and x64. GitHub displays current download, extraction, and registration commands containing a short-lived token. Run exactly those displayed commands from an elevated or ordinary PowerShell window as appropriate.

During `config.cmd`, use:

- Runner name: `ww-local-runner`
- Additional label: `ww-local`
- Work folder: `_work`
- Run as service: no for the first setup

The resulting runner should show the default labels `self-hosted`, `Windows`, and `X64`, plus `ww-local`.

Do not copy a registration token into the repository, an Issue, a chat message, or a script. It is short-lived and should be used only in the local registration command displayed by GitHub.

## Start the runner only when needed

Open PowerShell:

```powershell
Set-Location C:\ww-actions-runner
.\run.cmd
```

Leave that window open. The repository Runners page should show `ww-local-runner` as `Idle`.

After the workflow finishes and artifacts are uploaded, press `Ctrl+C` in the runner window. The PC remains on and the runner becomes offline.

A Windows service can be evaluated later, but the manual foreground process is safer while the workflow is new because the owner can see exactly when the personal PC is accepting jobs.

## Manual validation workflow

The workflow file is:

`.github/workflows/ww-local-self-hosted-validation.yml`

It is manual-only and restricted to the repository owner. It checks out the requested ref with persisted GitHub credentials disabled, then runs:

1. Java 17, Python, and Gradle setup;
2. normal benchmark build;
3. deterministic flight simulation included in the build;
4. exact runtime Mod download when missing;
5. real-physics `dogfight_mutual` GameTest;
6. scenario verification and HTML diagnostics;
7. artifact upload even when verification fails.

The workflow must exist on the default branch before GitHub displays its `Run workflow` button. Keep it on this infrastructure branch until the runner configuration and workflow review are complete.

Recommended first dispatch:

- ref: `agent/mutual-dogfight-mission-hold`
- aircraft: `warfare_wings:a6m`
- run_gametest: `true`

Start `run.cmd` before or after dispatching. A dispatched job may remain queued until the matching runner comes online.

## Security boundaries

- Keep `workflow_dispatch` as the only trigger.
- Keep the `github.actor == 'genkimorimori252525-oss'` job check.
- Keep the dedicated `ww-local` runner label.
- Never run fork refs or unreviewed third-party code.
- Keep `persist-credentials: false` on checkout.
- Do not store secrets, browser profiles, SSH keys, cloud credentials, university credentials, or personal files under the runner directory.
- Use a separate Windows user account later if the runner becomes persistent or automatic.
- Stop the runner immediately if an unexpected job appears.
- Remove and re-register the runner if its work directory may have executed untrusted code.

## Power and sleep settings

For a validation run, temporarily prevent Windows from sleeping while plugged in. Do not permanently disable sleep unless the runner becomes a dedicated machine.

The workflow has a 110-minute timeout, but Windows sleep, reboot, loss of network, or closing the runner window will interrupt the job. Diagnostic files already uploaded remain available; local files remain in the runner work directory until the next clean checkout.

## What this replaces

This Windows runner supersedes the experimental Google Cloud runner plan. The GCP branch is preserved only as design history. Do not merge or run its workflow, especially its VM shutdown step, on a personal PC.
