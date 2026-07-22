# Google Cloud self-hosted validation runner

This document provisions a manually started Google Compute Engine VM that executes the expensive Forge build and `dogfight_mutual` GameTest without using GitHub-hosted runner minutes.

The first version is deliberately simple:

1. Dispatch the manual GitHub workflow.
2. Start the VM from Google Cloud Console.
3. The self-hosted runner accepts the queued job.
4. Build, GameTest, verification, and artifact upload run on the VM.
5. The workflow schedules the VM to shut down after the job.

Do not attach this runner to automatic `push` or `pull_request` workflows. The repository is public, and untrusted pull-request code must never run on this machine.

## Recommended initial VM

- Product: Compute Engine
- Region/zone: Osaka `asia-northeast2-a` or another available `asia-northeast2` zone
- Provisioning: standard VM for the first validation runs
- Machine: `e2-standard-4` (4 vCPU, 16 GB RAM)
- OS: Debian 12 x86_64
- Boot disk: 60 GB `pd-balanced` or larger
- GPU: none
- Service account: none, or a dedicated account with no project-management permissions
- Firewall: do not allow HTTP or HTTPS; do not expose a Minecraft server port
- SSH: use Google Cloud Console SSH or OS Login
- Metadata: enable OS Login when practical

After stable runs and resumable artifact handling are proven, a Spot VM can be evaluated. Do not begin with Spot because it can be preempted during a long GameTest.

## Install VM dependencies

Connect through the Google Cloud Console SSH button and run:

```bash
sudo apt-get update
sudo apt-get install -y \
  ca-certificates curl git jq python3 python3-venv unzip zip \
  openjdk-17-jdk

java -version
git --version
python3 --version
```

Create a dedicated runner account:

```bash
sudo useradd --create-home --shell /bin/bash github-runner || true
sudo mkdir -p /opt/actions-runner
sudo chown -R github-runner:github-runner /opt/actions-runner
```

Permit only the final shutdown command without a password:

```bash
echo 'github-runner ALL=(root) NOPASSWD: /sbin/shutdown' \
  | sudo tee /etc/sudoers.d/github-runner-shutdown
sudo chmod 440 /etc/sudoers.d/github-runner-shutdown
sudo visudo -cf /etc/sudoers.d/github-runner-shutdown
```

## Register the GitHub runner

In the repository UI, open:

`Settings -> Actions -> Runners -> New self-hosted runner`

Select Linux and x64. GitHub displays commands containing a short-lived registration token. Run those commands as `github-runner`, but configure these values:

- Runner name: `ww-gcp-runner`
- Additional label: `ww-gcp`
- Work folder: `_work`

Example shape only; use the current download URL and token shown by GitHub:

```bash
sudo -iu github-runner
cd /opt/actions-runner

# Run the download and extraction commands displayed by GitHub.

./config.sh \
  --url https://github.com/genkimorimori252525-oss/warfare_wings-1.1.4-1.20.1-forge \
  --token '<ONE-HOUR-REGISTRATION-TOKEN>' \
  --name ww-gcp-runner \
  --labels ww-gcp \
  --work _work \
  --unattended
exit
```

Install it as a system service so it reconnects whenever the VM starts:

```bash
cd /opt/actions-runner
sudo ./svc.sh install github-runner
sudo ./svc.sh start
sudo ./svc.sh status
```

The runner must appear as `Online` in the repository's Runners page.

## Manual validation workflow

The workflow file is:

`.github/workflows/ww-gcp-self-hosted-validation.yml`

It is manual-only and restricted to the repository owner. It checks out the requested same-repository ref, runs the normal benchmark build and deterministic simulation, optionally runs the real-physics `dogfight_mutual` GameTest, uploads all diagnostics, and then schedules a VM shutdown.

The workflow must exist on the default branch before GitHub displays its `Run workflow` button. Keep it on a review branch until the VM and runner are ready; then merge only this infrastructure change.

Recommended first dispatch:

- ref: `agent/mutual-dogfight-mission-hold`
- aircraft: `warfare_wings:a6m`
- run_gametest: `true`

Start the VM after dispatching. The job can remain queued while the runner is offline, then starts when the runner reconnects.

## Cost and shutdown discipline

Compute charges stop when the VM is terminated, but the persistent boot disk continues to incur storage charges. The workflow schedules `shutdown -h +1` after artifact upload. Confirm in Google Cloud Console that the VM reaches `TERMINATED` after every run.

Also configure a defensive instance stop schedule, for example every night at 03:00 Asia/Tokyo, so a failed workflow cannot leave the VM running indefinitely.

## Security boundaries

- Never run this workflow automatically for pull requests or forks.
- Keep `workflow_dispatch` as the only trigger.
- Keep the owner-actor check in the job.
- Do not store Google Cloud credentials in the repository or runner work directory.
- Do not attach a broad Compute Engine service account.
- Keep `persist-credentials: false` on checkout.
- Use a dedicated VM containing no personal files.
- Review workflow changes before merging them to the default branch.
- Stop and recreate the runner if its VM image or work directory might have been exposed to untrusted code.

## Later automation

After the manual path is stable, a small authenticated Cloud Run service can receive an owner-only request and start the VM through the Compute Engine API. That adds the web dashboard/start button without changing the Forge validation environment.
