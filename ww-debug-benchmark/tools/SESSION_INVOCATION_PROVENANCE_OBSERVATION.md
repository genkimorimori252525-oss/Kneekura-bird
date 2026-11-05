# Session invocation provenance: private source-copy counterexample

This is a **test-only experiment**, built on #235 and #237; it changes no
production code, starts no Minecraft/Forge, and is not connected to the arbiter,
Mixin, route guidance, player gate, or native setter. It examines whether a fake
per-invocation scope could distinguish a normally returned session output from
other values. The scope is **unsafe as a control mechanism**: the cross-thread
counterexample below produces a false `PRESENT` under the stated contract.

The uninstrumented baseline has no provenance scope support: nine positive
binding checks intentionally fail. They demonstrate that this artificial test
can report a missing mechanism, not nine existing production bugs. The candidate
uses a private source copy of `AutopilotSession` with fake trace calls at entry,
plan dispatch/return, emergency override and terminal/normal return. It keeps
the original `tick` descriptor and does not alter `AutonomousFlightManager`,
but this static source shape is not evidence of actual transformed Mixin
compatibility. The fake logger, entity and dynamically reading snapshot are not
the real server, logger or immutable runtime `FlightSnapshot`.

The fake `ThreadLocal` scope binds a session object and a completed `tick`
return object by reference. It rejects a different session, an equal-valued
new output, a prior output, an exception, a closed scope, and selected nested
same-thread or foreign-session calls. A trace entry from a different session or
a second entry invalidates the active fake frame. This is not a usable control
interface: output is inspected only while the fake scope is open; a reference
match cannot rule out same-reference transformation, concurrent mutation, ABA,
or arbitrary callbacks. The fake equal-valued output is only an analogue of a
route replacement, not the route Mixin.

## Expected results and counterexamples

In v3, each mode compiled and ran 15 cases in fresh JVMs. Baseline outer exit 1
contains the nine intentional positive-contract reds; the other six baseline
cases exit 0. Candidate outer exit 1 contains **one intentional red** for the
cross-thread counterexample; the other fourteen cases match their limited fake
expectations. A separate checker recorded 98 selected checks with no unexpected
result. Checker exit 0 means the expected reds and controls were observed; it
does not mean the candidate passed a safety contract.

* Selected fake same-session normal, heading transition, pre-plan stall,
  post-plan emergency and terminal-return paths preserve phase/output summaries
  relative to the uninstrumented source and expose the synthetic origin inside
  an open scope. A fake exception is `UNKNOWN`; other-session, previous-output,
  equal-valued copied-output, after-close and selected same-thread nested cases
  are rejected. A direct nested call has no inner scope to query; only the
  outer scope's invalidation is asserted. #237 already shows an earlier session
  output can remain after a fake exception.
* In the **cross-thread case**, the main thread opens a scope, a worker calls
  the same session's `tick`, the worker is joined, and the main thread calls
  `tick` and completes its scope. This is a controlled interleaving, not two
  simultaneous ticks. The worker has a separate `ThreadLocal` and is invisible
  to the main scope, which reports `PRESENT` despite the intervening same-session
  call. The fixture expects `UNKNOWN`, so this case exits 1. Actual execution of
  this interleaving in the MOD has not been established.
* Static review also found that closing an outer scope while an inner scope is
  current can leave the closed outer frame to be restored by inner close;
  closing from another thread cannot remove the owner thread's `ThreadLocal`.
  Those misuse cases were **not executed**. Reference retention, visibility and
  effect on later calls remain unverified; do not infer a real-runtime leak.

No real player/collision/terrain/firing gates, prior manager/benchmark writes,
route transform, native setter or partial failure is tested. No inference is made
about actual control selection, flight completion, or all 24 aircraft. Unknown
provenance or fallback to existing formation behavior is not itself a safety
guarantee. #230–#232 and #235–#237 record separate constraints and observations.

## Reproduce and retain evidence

Use trusted, explicitly supplied JDK 17 and dependency jar inputs and **new**
directories outside any world. These tools are not a sandbox. Run baseline and
candidate separately; each returns exit 1 when its expected red is observed,
and exit 2 for an unexpected setup/result. Then run the checker into a new file:

```sh
python3 -I -B tools/observe_session_invocation_provenance.py --mode baseline \
  --java-home /path/to/jdk17 --dependencies-json /path/to/dependencies.json \
  --output /path/to/new-baseline
python3 -I -B tools/observe_session_invocation_provenance.py --mode candidate \
  --java-home /path/to/jdk17 --dependencies-json /path/to/dependencies.json \
  --output /path/to/new-candidate
python3 -I -B tools/check_session_invocation_provenance.py \
  --baseline /path/to/new-baseline --candidate /path/to/new-candidate \
  --output /path/to/new-check.json
```

Earlier v1/v2 artifacts and failures are retained. Source, fixture, runner and
dependency hashes are sampled before/after; JDK launcher hashes are before
only. The checker asserts four named class origins for `normal` only and
compares selected state, output, event and frame strings, not all side effects.
Per-case logs/classes are not immediately hashed, provenance is caller supplied,
and snapshots do not prove uninterrupted integrity. Timeout, missing inputs,
unreached paths or output errors are incomplete, not safety passes.
