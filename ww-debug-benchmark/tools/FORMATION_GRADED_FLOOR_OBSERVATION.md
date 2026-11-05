# Formation graded turn-floor target: source-copy observation

This is a **test-only experiment**, based on #233 local commit `789be2b` and
the #226 fixture/production source from #214. It makes no production change,
does not start Minecraft, and does not simulate flight, setter success, mission
completion or safety. It tests a distinct idea from #233's forced throttle:
while the ordinary formation slot is in `TURN_RIGHT`, if follower speed and
slot target are finite, raise a slot target below the measured turn floor to
that floor **before** using the existing stepwise speed-error throttle logic.
The experiment does not change formation axes, collision/terrain/player gates,
the manager method body, mission clocks, or any direct writer. It adds no
entity getter; the fake snapshot getter is not the runtime immutable record.

The script compiles temporary baseline and candidate copies of 11 actual source
files with stand-in world, snapshot, terrain planner, checkpoint, logger,
profile registry, combat and setter. #226's 1549/1589 input states are
reconstructed from same-server-tick lines not proved simultaneous; at 1589
the fake target speed 14.299 differs from the original log's 14.566. The v2
run includes 34 cases per version; the separate checker asserts 79 selected
fake observations, with non-finite inputs explicitly observation-only. This
is not a flight trajectory or a validation of the aircraft's measured profile.

## What this comparison shows

* Around the turn floor (below/equal/above by 0.001), the candidate sends 0.42
  for all three reconstructed slot states. This removes #233's particular
  1.0→0.08 switch at that floor in these samples, not all discontinuities.
  The baseline slot sends 0.08. The floor-below case is also a **counterexample
  to preserving base turn recovery**: base sends engine 1.0 first, and the
  candidate slot then sends 0.42. Their x/z targets remain different.
* For the two low-speed #226 reconstructions the candidate slot engine is 1.0
  after the base call. The slot target is 34.6441733648. A fake leader at
  60 blocks/s yields target 61.4947958905 and engine 1.0 in both versions;
  the proposal can exceed the measured top speed, so this case is not evidence
  of a realistic or safe target.
* Existing throttle steps still switch around target-speed errors +0.8, +3.5,
  -0.8 and -2.5. The ±0.001 cases reach both sides; equality samples are subject
  to floating-point representation and are not general proofs of exact equality.
  The lower-speed `stallGuardSpeedBps*1.25` branch separately adjusts pitch,
  roll and minimum throttle; this experiment does not separately exercise its
  threshold and does not reproduce the base turn-recovery axes.
* When the heading becomes complete, base returns old-turn recovery while the
  updated phase is `STALL_SETUP`; both versions then send formation engine 0.9.
  At the timeout boundary the phase becomes `ABORTED` and neither sends a
  formation proposal. The candidate does not change these transitions.
* The selected fake collision-direct, risk-only, terrain, ungrouped, leader,
  combat-claim, missing-profile and initial-player cases retained their observed
  outcomes. A late player/mob replacement prevented the pending formation call
  but the earlier base call remained. A risk-only collision label with just the
  base call remains an existing synthetic safety concern, not a passing gate.
* Artificial NaN/infinite follower speed and NaN leader speed kept the existing
  outputs in these cases. The NaN leader's reported slot target remains NaN.
  No non-finite safety policy or natural reachability has been established.

The additional floor applies on both sides of the floor while `TURN_RIGHT`
remains current; therefore it changes behavior above the floor compared with
#233, and it may change relative speed and closure while following a slow
leader. A direct collision check before a proposal does not establish that a
faster aircraft remains separated on later ticks. No hysteresis, realistic
acceleration, future collision prediction, actual profile/terrain behavior,
native partial-failure behavior, reentry/ABA, real player takeover, log-to-
setter causality, Mixin transformation or real MOD results are established.
Preserve the #150 counterexample where another wingman turned under formation.
Neither candidate should be accepted or used as a safety fix from these results.

## Reproduction and evidence

Use explicit, reviewed JDK 17 and dependency paths. This test tool is not a
sandbox; its Java/Python and classpath inputs are trusted by the caller. It
copies sources to an exclusive output and removes dependency directory entries
to avoid accidentally loading older project classes. Use new output paths
outside any world, inspect process exit, report, stderr and class-load logs.

```sh
python3 -I -B tools/observe_formation_graded_floor.py \
  --java-home /path/to/jdk17 --dependencies-json /path/to/dependencies.json \
  --output /path/to/new-observation
python3 -I -B tools/check_formation_graded_floor.py /path/to/new-observation \
  --output /path/to/new-check.json
```

The earlier v1 ran only floor-below; v2 used the fixed runner and complete
case set. Source, fixture, runner and dependency hashes are sampled before and
after; JDK executable hashes are recorded only before execution. Neither
measurement proves uninterrupted integrity or authenticates the whole JDK.
Eleven named origins are asserted for just the 1549-low case, with
unverified races and other cases; JVM stderr is retained but not semantically
compared. The fake logger reports proposals before final writer selection.
