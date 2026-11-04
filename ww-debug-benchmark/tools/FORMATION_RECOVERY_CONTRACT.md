# Formation recovery contract probe

This is a test-only, stand-alone candidate contract. It compiles the checkout's
actual autonomous manager, session, formation manager, authority arbiter,
collision probe and related types alongside synthetic entities, world,
checkpoint, terrain planner, logging and setter. It does not start Minecraft,
run a GameTest, use a world or prove native setter success. The fake checkpoint
sets a newly created session to a fixed turn state; the fake level ignores the
query AABB and its raycast always misses. See
`FORMATION_REAL_MANAGER_OBSERVATION.md` for the inherited runner and evidence
constraints. The generated `production/` directory contains both actual and
stand-in classes; `fixture/` is empty.

The candidate contract is that, for the tested same-tick grouped recovery
without higher-priority claims, the arbiter retains base authority and makes
only the base setter call. On the unmodified #201 source, `grouped` reports
FORMATION and two setter calls and fails at the **authority assertion first**;
the second setter assertion is therefore not reached in that red run. Stdout
still records both actual fake-setter calls. This is an observed synthetic red,
not proof of a live flight fault or of the safety of a proposed fix.

The other cases run in their own JVMs. `recovered` uses two successive calls on
one synthetic entity and session in its own JVM: the first observes recovery,
then the fixture changes only its speed before the second call, which expects
formation to resume. The fixture checks manager-owned aircraft and session object
identity, a single checkpoint call, and successive phase and mission ticks. It
is not a physical trajectory replay. Ungrouped,
collision, injected terrain, collision plus injected terrain, terminal
collision-risk-only, and player/empty/client controls exercise the respective
fixed fixtures. Client uses a fake ServerLevel with its client flag set. The
combat cases use a fake facade for claimed-without-proposal and already-written
controls; they do not exercise a pending combat proposal or real combat AI.
The fake terrain and collision cases do not prove safe separation or real
terrain planning. The collision-risk-only labels are retained as observations,
not proof that a collision avoidance setter was written.

`stale`, `same-uuid`, and `hold-change` print
`classification=INCONCLUSIVE_OBSERVATION`; their zero exits establish only that
the observation completed. They do not specify the correct result or validate
freshness, entity identity, phase changes, or real hold behavior. In particular,
the hold case manually changes a real session's phase and transition fields
through a fake adapter after base control. Additional safety contracts require
independent design and tests. Setter calls are to a stand-in; the production
reflective setter can fail without reporting success, so a suppression policy
must not assume its invocation means controls were applied.

## Run

Use JDK 17 and a trusted JSON array of absolute paths to existing mapped
Minecraft/Forge and library dependencies. From `ww-debug-benchmark`, supply a
new output directory outside the checkout and all Minecraft/world directories:

```sh
python3 tools/test_formation_recovery_contract.py \
  --java-home /path/to/jdk-17 \
  --dependencies-json /path/to/explicit-classpath.json \
  --output /path/to/new-observation-directory
```

The runner is not a sandbox. It writes per-command exits, stdout/stderr, class
load logs, compiled class and input hashes, classpath hashes before and after,
and a runner snapshot. Inspect every case, the actual class origins and hashes,
and capture the outer process exit separately. A missing report/case, changed
input, unexpected class origin or unrelated failure is inconclusive. On the
unmodified base the expected red makes the outer process exit nonzero; a green
result requires the grouped case and all specified controls to pass, with the
three observational cases still inconclusive. Hashes do not authenticate inputs
or rule out transient changes while running.

The recorded cloud run used JDK 17 and Forge 1.20.1-47.4.20 mapped with
`official_1.20.1`. Its ordered classpath manifest is a **local evidence file**
(`/workspace/issue7-evidence-20261104/postphysics-standin-repo-v2/dependencies.json`),
not a file supplied by GitHub. It included the existing main classes, the mapped
Forge JAR, `client-extra.jar`, and the resolved runtime libraries. In a different
environment, first build and resolve the matching development dependencies and
export their ordered absolute paths to a JSON array; this probe does not export
or download that array. Verify the mapped JAR and the per-case class-load logs.
For example, the manifest is a JSON array such as
`["/absolute/path/to/main-classes", "/absolute/path/to/mapped-forge.jar", "..."]`;
replace the ellipsis with every required resolved path, never as a literal entry.
Exact binary reproducibility requires matching the recorded dependency hashes;
the repository does not contain the local classpath artifacts or those records.

The saved red v2 runner SHA-256 is
`ff62697f043f1292938351f61dc6f9cfda6d4ff1397299bdcff7afca34710969`.
The saved red v3 runner SHA-256 is
`5ee595848e2d8867c6621cafa7f44ac8a8d5cef51b5e689a2acc5dc24421da24`.
The local red record had compile exit 0, grouped exit 1 at the authority
assertion, and outer runner exit 1. Treat other results as described above;
they do not by themselves establish that the single-setter candidate is safe.
