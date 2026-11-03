# Cloud validation and bulk simulation

## Objective and evidence boundaries

Keep the existing Issue #7 aircraft AI and safety invariants. Make iteration independent of the
owner's PC where practicable, and enable many repeatable scenarios. A browser is a presentation and
control surface; it does not establish that a model matches Minecraft physics.

There are three distinct evidence levels:

1. The existing `FlightSimulationMain` is a fast deterministic mission preflight. Its source
   explicitly says it does not reproduce Immersive Aircraft physics. A pass is not a flight
   qualification.
2. A future bulk physics model can screen many initial conditions. It must be calibrated and
   compared against versioned traces from the real mod, and report out-of-domain cases and error
   bounds. It is not yet implemented or qualified.
3. Forge GameTest with the exact Minecraft and mod versions remains the acceptance oracle for
   behavior changes. Existing scenario verifiers and safety limits remain authoritative.

## First experiment

`ww-hosted-preflight.yml` is a manual, GitHub-hosted Windows experiment for the existing Gradle
build and deterministic preflight. It uses Java 17 and Gradle 8.8 without the owner's cached
installation. The workflow has not yet been run and does not run the Forge flight GameTest. Do not
replace a required check or remove the existing runner until both hosted build and targeted
GameTest, including artifacts and verifier output, have been demonstrated on the exact commit.

## Future implementation sequence

1. Capture deterministic real-mod traces with mod version and artifact hashes, initial state,
   inputs per tick, world conditions, outputs and seed. Preserve the original run and its verifier
   result. Cover normal flight, stall, turning, terrain and aircraft-specific behavior.
2. Inspect the actual mod implementation and distribution terms before choosing source reuse,
   a compatible isolated runtime, or a separately implemented model. Do not infer physical
   equations or redistribute mod code from a binary without checking the applicable terms.
3. Compare candidate models against held-out traces by aircraft and maneuver, reporting per-tick
   and cumulative position, speed and attitude errors, divergence and validity ranges. Establish
   thresholds from observed intended use; do not invent equivalence or tune against all fixtures.
4. Add batch execution with fixed seeds, bounded resources, immutable input/version manifests,
   per-case outputs and resumable jobs. Keep all failed and unsupported cases visible.
5. Only after the core is usable independently, expose scenario selection, progress, trajectory
   comparisons and downloadable evidence in a browser. The UI must label screening versus actual
   Forge qualification and never turn an approximate-model pass into a qualification claim.

## Operational decision, 2026-11-03

The owner explicitly requested making `Kneekura-bird` public and preparing cloud work in this chat.
Before public visibility, GitHub Actions was disabled at repository level because the existing PR
workflows target the owner's Windows self-hosted runner. The repository is now public. Actions
remains disabled while the safe transition is designed: existing Windows runner/deployment
workflows and their triggers must be reviewed before enabling it again. This blocks all Actions,
including the experiment above; no hosted test is claimed. Reversal is to restore the previous
repository Actions setting (`enabled: true`, `allowed_actions: all`) only after addressing that
exposure. The previous visibility was private; changing it back cannot retract already public data.

Codex Cloud currently has no saved environment for this repository. Creating or selecting that
environment and testing repository snapshot size remains separate from GitHub Actions validation.
The older PR #101 regression checkpoint remains open; this experiment does not fix or validate it.
