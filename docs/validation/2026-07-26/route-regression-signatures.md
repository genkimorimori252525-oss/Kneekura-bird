# Route regression signatures for all 24 base aircraft

Recorded: 2026-07-26 (Asia/Tokyo)
Behaviour ref: `4092d096f17e7aac34e19696b8a63f62f96b6c53`

## Why signatures rather than pass/fail

Route coverage reached 24 of 24 on 2026-07-25. Everything that follows — the
`ControlAuthorityArbiter` conversion, the missing doctrines, damage and pilot-loss
authorities, bombing and torpedo missions — changes the code that produces these flights.

A boolean suite only catches an aircraft that stops reaching `PARKED`. It cannot catch
**drift**: an arbiter change that shifts landing geometry by hundreds of ticks while still
technically completing the mission. Drift is the realistic failure mode of the work ahead,
so the baseline records the shape of each flight, not just its verdict.

## What is compared

`route-regression-signatures.json` holds one entry per base aircraft, taken from the
`validation-summary-*.json` produced by that aircraft's own qualification run.

Compared exactly:

- `role`
- `passed`
- `reason` — every aircraft currently records `completed_full_mission`
- `final_phase` — every aircraft currently records `PARKED`
- `last_transition_reason`

Compared within `tolerance_ticks_percent` (currently 15%):

- `elapsed_ticks`
- `mission_ticks`

## The tolerance is provisional and deliberately generous

Each signature comes from **exactly one run**, so the natural run-to-run variance of these
tick counts is not yet known. 15% is a guess chosen to avoid false alarms, not a measured
bound.

Tighten it once any aircraft has been qualified two or three times on an unchanged behaviour
ref and the real spread is visible. Until then, treat a tick delta inside tolerance as
"unmeasured", not as "verified unchanged".

## Recorded baseline

| Aircraft | Role | Doctrine | Run | elapsed | mission |
| --- | --- | --- | --- | ---: | ---: |
| a6m | fighter | turn_fighter | 30106085402 | 5360 | 4783 |
| spitfire | fighter | turn_fighter | 30120064170 | 3990 | 3821 |
| yak3 | fighter | turn_fighter | 30149217195 | 3723 | 3557 |
| bf109 | fighter | energy_fighter | 30151410943 | 3776 | 3612 |
| f4u | fighter | energy_fighter | 30151812704 | 3723 | 3567 |
| f6f | fighter | energy_fighter | 30175097134 | 3838 | 3667 |
| fw190 | fighter | energy_fighter | 30177411289 | 3701 | 3544 |
| ki61 | fighter | energy_fighter | 30175707465 | 3848 | 3678 |
| ki84 | fighter | energy_fighter | 30175848558 | 3969 | 3775 |
| mc202 | fighter | energy_fighter | 30176031935 | 4042 | 3855 |
| mig3 | fighter | energy_fighter | 30176210630 | 3927 | 3757 |
| p40e | fighter | energy_fighter | 30176388410 | 4062 | 3876 |
| p47n | fighter | energy_fighter | 30176568969 | 3786 | 3635 |
| p51d | fighter | energy_fighter | 30118532513 | 4078 | 3921 |
| b17 | bomber | unknown | 30115815404 | 6636 | 6343 |
| b29 | bomber | unknown | 30120521495 | 6042 | 5826 |
| g10n1 | bomber | unknown | 30176753857 | 5217 | 5034 |
| g10n2 | bomber | unknown | 30176938024 | 5049 | 4869 |
| he111 | bomber | unknown | 30177119529 | 4962 | 4767 |
| d4y | attacker | unknown | 30148766789 | 3938 | 3757 |
| il2 | attacker | unknown | 30115029120 | 4748 | 4477 |
| ju87 | attacker | unknown | 30147903349 | 5468 | 5158 |
| sbd | attacker | unknown | 30148395384 | 4789 | 4530 |
| g4m | torpedo_bomber | unknown | 30113770224 | 4956 | 4684 |

All 24 record `passed: true`, `final_phase: PARKED`, `reason: completed_full_mission`.
Zero anomalies.

## The baseline documents a known gap

**Every one of the 10 non-fighters resolves `doctrine: unknown`.** The 14 fighters resolve
correctly — `turn_fighter` for A6M, Spitfire and Yak-3, `energy_fighter` for the other
eleven — which is exactly the split Issue #7 specifies.

This is the doctrine gap, measured rather than asserted: `AirCombatDoctrineTuning.resolve`
implements 2 of the 6 doctrines the issue requires, and the bombers, attackers and the
torpedo bomber currently fly the generic route with no doctrine behaviour behind them.

When `level_bomber`, `dive_bomber`, `ground_attacker` and `torpedo_attack` are introduced,
the `doctrine` field in this baseline **must be updated deliberately**, as part of that
change, rather than silently drifting.

## How to use it

1. Re-run a qualification for the aircraft under test.
2. Compare its `validation-summary-*.json` result against the entry here.
3. Any mismatch in an exact field is a regression. A tick delta beyond tolerance is drift
   that needs an explanation, not an automatic failure.

Because stage-1 CI is currently blocked (see `docs/AI_HANDOFF.md`), this comparison is
manual for now. It should become an automated check once the self-hosted stage-1 workflow
lands.
