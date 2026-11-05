# Prior session output after a later fake exception

This **test-only source-copy observation** extends #235. It does not modify
production code, start Minecraft/Forge, select a control authority, or call a
native setter. It asks one question: what does the selected session state
contain if a prior direct `AutopilotSession.tick` call returned normally and a
second call raises an injected fake logger exception? Reentry is deliberately
not included. The two direct calls stand in for successive ticks; no real server
tick, elapsed time, aircraft motion, or real logger failure is reproduced.

The fixture uses the #235 source-copy runner, fake world, dynamic fake snapshot,
fake logger and trace, real `AutopilotSession` source and measured-profile-shaped
fake input. First it seeds `TURN_RIGHT`, invokes one tick and asserts that
`lastOutput` is the exact returned reference. It then clears only the **fake
observer trace**, not the session, and makes a second call. The first fake log
frame remains in the in-memory list. Each case and variant runs in a fresh JVM.
The private trace adds code to the source copy and may itself alter timing or
exception behavior; it is not a proposed implementation or a same-call token.

## Synthetic observations

Baseline and traced copies each compile and reach these three conditions; the
independent checker compares selected output summaries, phase/clocks, first
frame/event lists, sentinel identity within each JVM and trace locations:

| Second call | Session afterward | `lastOutput` afterward |
| --- | --- | --- |
| No injected failure | `TURN_RIGHT`, phase 102 / mission 1002 | New returned reference, distinct from the first |
| Fake phase-transition event throws | `STALL_SETUP`, phase 0 / mission 1002 | First call's reference remains; second call returns no output |
| Fake frame logging throws | `TURN_RIGHT`, phase 102 / mission 1002 | First call's reference remains; second call returns no output |

In the first exception the transition changes state before the fake event
throws, so no event is added and `plan` does not return. In the second, `plan`
returns but fake frame logging throws before `lastOutput` is assigned. Both
variants propagate their own fixture's exact sentinel. These are **two intentional
exceptions caught by the fixture**, not failed or successful real flight tests.
The success case confirms a normal second call replaces the prior reference.

The actual logger catches some internal failures but also performs work outside
that catch; the fixture's unconditional sentinels do not establish whether the
same exception, timing or side effects occur in Forge. No real route Mixin,
terrain planner, player transition, reentry/ABA, concurrent session access,
partial setter failure, authority ordering or cleanup is exercised. A stale
`lastOutput` reference after an exception illustrates why a later read alone is
not a safe same-invocation provenance token; it does not prove any existing
production caller uses it unsafely. No changes to recovery logic or safety gates
follow from this experiment.

## Reproduce and evidence limits

Use a caller-reviewed JDK 17, absolute dependency jar paths, and new paths
outside any world. The scripts are not a sandbox. They need the #235 runner
and its #226 fixture in the same tools directory.

```sh
python3 -I -B tools/observe_prior_output_exception.py \
  --java-home /path/to/jdk17 --dependencies-json /path/to/dependencies.json \
  --output /path/to/new-observation
python3 -I -B tools/check_prior_output_exception.py /path/to/new-observation \
  --output /path/to/new-check.json
```

V1 ran 3 cases per source-copy variant, plus two compiles, with all eight child
processes returning zero. A separate checker recorded 31 selected assertions
and zero failures; zero means the expected fake success and caught exceptions
were observed, not real-world safety. Input source, fixture, base runner,
wrapper and dependency hashes are sampled before/after; JDK launcher hashes
are recorded before only. Four named production-class origins are checked in
the success case for each variant, not every class/case. Per-case outputs and
class files are not hashed immediately; hashes do not authenticate inputs or
prove uninterrupted integrity. A compile failure, missing expected exception,
missing trace, changed input or output error is incomplete.
