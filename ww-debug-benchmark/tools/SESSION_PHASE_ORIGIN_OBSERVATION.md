# Session phase origin: private source-copy observation

This is a test-only observation on the #226 local base `dca16d1`, whose
production source corresponds to #214. It does not change production source,
start Minecraft, exercise a native setter or choose a control authority. It
compares unchanged `AutopilotSession` source with a private source copy that
records a fake trace at tick entry, immediately before/after `plan`, the
terminal early-return path and the post-plan low-AGL override. Trace calls
themselves can affect timing or exceptions; this is not a production design or
evidence that instrumentation is harmless.

The actual tick performs mission-timeout, unexpected-stall and approach
guards before `plan`. The `plan` switch chooses its branch from the phase at
dispatch; that branch can transition `phase` before returning its output. A
low-AGL guard can then replace that returned output. Therefore neither tick
entry phase nor the phase written to the current frame alone necessarily names
the branch that produced the returned session output.

## Results and scope

The v2 observation compiled both variants and ran eight artificial cases in
fresh JVMs. A separate checker asserted 37 selected conditions with zero
failures: source/fixture/runner/dependency hashes before/after, four named class
origins for one representative case per mode, selected state/output/lastOutput/
events/frame and fake-exception agreement, and expected trace positions.
These are synthetic comparisons, not a runtime safety verdict.

| Artificial condition | Entry | Plan dispatch | Phase after plan | Returned session result |
| --- | --- | --- | --- | --- |
| No transition | TURN_RIGHT | TURN_RIGHT | TURN_RIGHT | turn speed recovery |
| Heading reached | TURN_RIGHT | TURN_RIGHT | STALL_SETUP | old turn speed recovery |
| Turn timeout | TURN_RIGHT | TURN_RIGHT | ABORTED | old turn speed recovery |
| Mission timeout | TURN_RIGHT | no dispatch | not applicable | terminal `aborted` output |
| Unexpected stall before plan | TURN_RIGHT | STALL_RECOVERY | STALL_RECOVERY | stall recovery acceleration |
| Low AGL after plan | TURN_RIGHT | TURN_RIGHT | TURN_RIGHT | emergency terrain output replacing plan |

Two fake logger sentinel exceptions were also compared. A fake event failure
after transition left the updated phase but no returned/last output; a fake
frame failure happened after plan but before `lastOutput` assignment. Both
variants propagated the same fixture sentinel within their own JVM. The actual
logger catches some failures internally and accesses real server/entity state;
these injected exceptions do not reproduce its complete runtime behavior. Both
cases start with a new session whose `lastOutput` is null; behavior with an
existing last output from a prior tick was not exercised. The other six cases
are normal outcomes, not exception tests.

The fake trace is local to this single synthetic session invocation. It is not
a durable session ID, epoch, freshness token or proof against concurrent changes
or nested reentry. The real `FlightSnapshot` is an immutable record, while the
fixture reads its fake entity dynamically. Session output may be modified after
return by the route Mixin, terrain planner and native-flight adapter. Formation
proposals may be logged before final selection; a collision authority label or
an attempted setter does not establish native write success. Earlier direct base
or benchmark writes are not undone; actual player takeover, terrain/collision,
weapons, runtime Mixin transformation and all-aircraft behavior remain outside
this fixture.

In particular, do not turn this trace into an arbiter selector or assume a
matching phase proves output ownership. A future control mechanism must define
same-invocation/session/pilot/level identity, reentry/ABA, transition ordering,
route transformation, partial setter failures and truthful proposal/write
telemetry while preserving the actual safety gates. An added public record or a
new `FlightControlOutput` STORE inside `AutonomousFlightManager.applyControl`
could alter compatibility or the `require=1` route Mixin target; neither is
tested here.

## Reproduction and evidence

Call with a reviewed JDK 17 and dependency JSON of existing absolute jar paths;
these tools are not a sandbox. Use new output paths outside any world and
inspect process exit, reports, per-case stderr and class-load logs:

```sh
python3 -I -B tools/observe_session_phase_origin.py \
  --java-home /path/to/jdk17 --dependencies-json /path/to/dependencies.json \
  --output /path/to/new-observation
python3 -I -B tools/check_session_phase_origin.py /path/to/new-observation \
  --output /path/to/new-check.json
```

The v1 source copy had the same six non-exception paths but printed no trace on
the two exception cases; it is retained. V2 prints trace state before handling
those exceptions. Source, fixture, runner and dependency hashes are sampled
before/after; the JDK launcher hashes are recorded before only. Logs and classes
are not hashed immediately per case, other origins are not automatically
asserted, and no measurement authenticates inputs or proves uninterrupted
integrity. Missing dependencies, compile failure, missing trace or output
failure is incomplete, not a pass.
