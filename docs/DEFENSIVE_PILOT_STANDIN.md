# Defensive pending pilot: standalone red probe

This is a synthetic investigation for Issue #7, not an aircraft qualification.
The baseline is commit `80eab064420c217df66c2d42c3f8772ff4216add` (#214).
`ww-debug-benchmark/tools/inspect_defensive_identity.py` compiles copies of 14 real
source files, including the defensive manager, facade, arbiter, formation manager,
autonomous manager, proposal and pilot gate. The runner supplies fake entities,
world, awareness, snapshot, terrain, setter, energy/offensive neighbours and other
dependencies; it does not start Minecraft or use a world.

With a fake threat behind the aircraft, a fake `Entity.isRemoved()` hook is invoked
only inside the arbiter's pending-write guard. It checks that the real defensive
adapter was logged, then changes pilot A to B. Thus the hook follows production
proposal selection in this fixture. A and B are different objects; a separate case
uses different pilot objects with equal UUIDs. Both contracts expect that no pending
setter is called after the switch. The baseline fails both contracts: a fake base
setter already occurred while A was pilot, and the second fake setter sees B.
This demonstrates the fixture's observed ordering, not that the hook is reachable
in Minecraft or that the native setter succeeds.

The `defense-claimed` case is **artificial reentry**: a fake log callback restores a
previously removed defensive state into the real manager's private state map. It
checks the facade's no-proposal claimed branch; it does not establish that this
state or callback occurs naturally. Fake weapon tick calls remain zero; firing,
friendly fire and all real weapon gates are outside this probe. Existing terrain,
collision, player, empty-seat and client controls are synthetic; the real MOD,
scene ownership, cleanup, frame-to-frame behavior, ABA and getter callback timing
are unproved. A proposal or authority label is not evidence of native control.

On the development machine the unmodified runner snapshot and source both had
SHA-256 `e9faa90b54d8b91de230e60841539731a17125a1bc503816780af3a958f18fa8`.
The saved `defensive-pilot-identity-red-v2/` report and matching `-outer/` directory
under `/workspace/issue7-evidence-20261104/` contain the source and classpath hashes,
class-load logs, compile and individual case exits. Compile and 16 controls exited
0; the two swap contracts exited 1 at their explicit assertions. These workspace
paths are local evidence, not a claim that the artifacts are published in GitHub.

To reproduce in a provisioned Java 17 / mapped Forge environment, create a JSON
array containing absolute paths to the required mapped Minecraft/Forge dependencies
and any compatible project classes, then run from this checkout:

```sh
python3 ww-debug-benchmark/tools/inspect_defensive_identity.py \
  --java-home /absolute/path/to/jdk17 \
  --dependencies-json /absolute/path/to/dependencies.json \
  --output /absolute/path/to/new-evidence-directory
```

The output path must not exist. Record the command and outer process exit separately;
exit 1 is expected for this baseline because the runner runs contract assertions.
A compile failure, changed inputs, missing dependency or failure at a different
assertion is inconclusive, not confirmation of the described regression. The local
fixture uses fixed pilot UUIDs, but fake callback scheduling remains a test input.
