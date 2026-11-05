# Formation turn-floor throttle: source-copy observation

This is a **test-only experiment**, based on #226 local commit
`dca16d1486076e17fe70e19a9fba4a8832bf62d8` (production tree of #214). It
does not modify production source, run Minecraft, simulate flight or qualify a
safety change. The narrow hypothesis changes only the ordinary formation slot
proposal in a temporary source copy: for `TURN_RIGHT` with finite follower speed
below the measured turn floor, it raises slot target speed to at least that floor
and sets the proposed engine target to 1.0. It uses the existing formation
snapshot/profile and does not add entity getters, move the manager body, replay
base input, alter phase clocks, or change steering calculation or safety gates.
The changed `reason`, override and target speed describe the proposed output;
they do not prove the arbiter ultimately wrote it.

The inputs and preconditions are #226's simulated reconstruction of ticks 1549
and 1589: fixed A6M profile, synthetic phase, yaw target, clocks, fake world,
collision geometry, checkpoint, logger, combat and setter. Values logged in the
same server tick were not proved simultaneous. At 1589, reconstructed target
speed 14.299 differs from the original log's 14.566. The fixture snapshot reads
the fake entity dynamically; the actual runtime `FlightSnapshot` is an immutable
captured record, so these runs cannot establish snapshot/reentry equivalence.

## Selected observations

The v6 run compiled baseline and candidate source-copy with the same stand-ins;
22 cases ran per copy. The independent checker asserted 60 selected comparisons
with no failures; three non-finite cases were recorded **without a safety
verdict**. `exit 0` means these narrow fake conditions matched, not that flight,
avoidance or the candidate is safe. The test's proposed throttle condition is a
hypothesis; it is not an acceptance criterion already established by the game.

* At 1549 the fake base setter is followed by formation engine 0.08 on baseline
  versus 1.0 on the candidate; at 1589, 0.9 versus 1.0. Candidate target speed
  is 34.6441733648 in both. Formation x/y/z and the earlier base call match
  across these variants; base turn recovery's x/z are not the formation axes.
* Just below the floor the candidate engine is 1.0; at the floor and just above
  it retains baseline 0.08 in the fixture. This discontinuity can cause
  oscillation or abrupt acceleration, neither of which is simulated here.
  In a separate fake leader-speed=60 case, both versions retain the already
  higher slot target 61.4947958905 and engine 1.0; the proposal reason changes.
* A heading-complete tick reports updated `STALL_SETUP`, while the just-computed
  base output remains `turn_speed_recovery`; candidate leaves the slot at 0.9.
  At the 440→441 timeout transition both versions abort with only base write.
  The throttle experiment does not solve either transition or prove a timeout
  will be avoided.
* Selected no-group, leader, missing-profile, fake terrain, collision direct,
  combat-claim and initial player controls retained the observed outcome. A
  separate risk-only timeout logs `COLLISION_AVOIDANCE` with just the base call;
  this is an existing synthetic observation, not collision avoidance success.
  Late player/mob replacement blocks the pending call in these fakes but retains
  the earlier base write and proposal log; it is not takeover safety proof.
* NaN/infinite follower speed follows existing output in these artificial cases.
  With NaN leader speed, candidate reports NaN target speed while proposing
  engine 1.0. Invalid values, failure handling and runtime reachability are
  unresolved; do not infer that retaining old behavior is safe.

The checker requires 11 named class origins for the low-speed case and compares
the selected fake setter arguments and logs, including the intentionally
unsatisfied baseline throttle hypothesis. It does not prove all classes/cases
loaded from the intended location throughout execution or rule out races; the
input/classpath hashes are sampled before/after. It does not exercise native
setter partial failure (see #230), real Mixin transformation, ABA or reentry,
runtime player changes, or subsequent-tick collision predictions. Raising
engine power can increase closure with a leader; safety over the following
trajectory, including collision/terrain and energy behavior, remains unknown.
No production patch should be inferred from these observations.

## Reproduce

Use the tracked script in a worktree with #226's test fixture and 11 named
sources, a caller-reviewed JDK 17 and dependency JSON of existing absolute jar
paths. The script omits directory entries in that JSON to avoid importing old
project classes and substitutes a fake logger. Use two fresh output paths
outside any world and inspect exit, report, class-load files and raw stderr:

```sh
python3 -I -B tools/observe_formation_turn_floor.py \
  --java-home /path/to/jdk17 --dependencies-json /path/to/dependencies.json \
  --output /path/to/new-observation
python3 -I -B tools/check_formation_turn_floor.py /path/to/new-observation \
  --output /path/to/new-check.json
```

Initial v1 stopped before creating output because its parent was absent; its
terminal traceback is the available record. V2 compile failed because the
project-class directory was omitted and no logging facade stub was supplied;
its output is preserved. Later v3/v4/v5 preserve intermediate cases; v6 includes
the risk-only, NaN-leader and fast-leader observations. A single-case fake exception does not
replace meaningful real MOD verification.
