# Successful route qualification signatures

Date: 2026-07-25

This document extracts comparable telemetry signatures from seven successful exact-physics artifacts. It is intended to accelerate diagnosis of the remaining route qualifications. Server-tick durations are observational and must not be confused with phase-tick timeout counters.

## Sources

- P-51D — Run `30118532513`, artifact `ww-local-route-30118532513`;
- Spitfire — Run `30120064170`, artifact `ww-local-route-30120064170`;
- B-29 — Run `30120521495`, artifact `ww-local-route-30120521495`;
- Ju 87 — Run `30147903349`, artifact `ww-local-route-30147903349`;
- SBD — Run `30148395384`, artifact `ww-local-route-30148395384`;
- D4Y — Run `30148766789`, artifact `ww-local-route-30148766789`;
- Yak-3 — Run `30149217195`, artifact `ww-local-route-30149217195`.

Every listed verifier passed with Gradle status 0, summary 1/1, and crash count 0.

## Signature table

| Aircraft | Route waypoint ticks, remaining 3/2/1/0 | Route complete | Ordinary turn release | Release delay | Return start | Downwind | Return server ticks | Start-to-downwind displacement | Base | Final | Go-arounds / flare extensions | Touchdown | Parked | Session elapsed |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| P-51D | 672 / 717 / 769 / 791 | 791 | 1,031 | 240 | 1,937 | 3,249 | 1,312 | 1,895.2 | 3,363 | 3,442 | 1 / 1 | 4,023 | 4,085 | 4,077 |
| Spitfire | 696 / 744 / 797 / 825 | 825 | 1,065 | 240 | 1,847 | 3,126 | 1,279 | 1,753.8 | 3,247 | 3,330 | 2 / 2 | 3,938 | 3,997 | 3,989 |
| B-29 | 3,806 / 3,872 / 3,938 / 3,993 | 3,993 | 4,233 | 240 | 5,482 | 7,532 | 2,050 | 1,395.6 | 7,768 | 7,925 | 2 / 2 | 8,703 | 8,759 | 6,041 |
| Ju 87 | 3,740 / 3,825 / 3,914 / 3,969 | 3,969 | 3,971 | 2 | 5,140 | 6,854 | 1,714 | 1,342.5 | 7,078 | 7,229 | 2 / 2 | 8,046 | 8,105 | 5,467 |
| SBD | 3,611 / 3,683 / 3,757 / 3,804 | 3,804 | 3,806 | 2 | 4,813 | 6,260 | 1,447 | 1,358.4 | 6,444 | 6,565 | 2 / 2 | 7,367 | 7,426 | 4,788 |
| D4Y | 3,377 / 3,429 / 3,483 / 3,515 | 3,515 | 3,574 | 59 | 4,456 | 5,629 | 1,173 | 1,517.2 | 5,761 | 5,849 | 2 / 2 | 6,515 | 6,575 | 3,937 |
| Yak-3 | 685 / 732 / 785 / 811 | 811 | 885 | 74 | 1,738 | 2,870 | 1,132 | 1,601.6 | 2,988 | 3,069 | 2 / 2 | 3,669 | 3,728 | 3,722 |

## Diagnostic interpretation

- Ordered route evidence is always `remaining=3,2,1,0`; any missing or reordered event is a route-ownership or telemetry failure before it is a control-tuning problem.
- Post-PR #70 release delay is not required to be exactly two ticks. It depends on how much of the fixed outbound sample was earned while route-owned. D4Y and Yak-3 validly released after 59 and 74 server ticks; replay from zero would be about 240.
- P-51D is the primary successful energy-fighter comparison. It covered the largest observed start-to-downwind displacement, about 1,895 blocks, and still reached `PARKED`.
- Yak-3 is the closest current-code fighter comparison for the merged route-clock/rejoin-speed behavior.
- B-29 demonstrates that large-aircraft completion can include bounded go-arounds and still be valid; a go-around is not failure unless acceptance-tail budgets or safety invariants are violated.
- Native flare extensions are expected bounded safety behavior. They must remain below their established altitude constraints and culminate in normal touchdown rather than indefinite extension.
- A new aircraft should be compared first against the same role/doctrine representative, then against the nearest measured-speed and landing-envelope signature.

## Remaining comparison map

- Bf 109, F4U, F6F, Fw 190, Ki-61, Ki-84, MC.202, MiG-3, P-40E, P-47N: compare first with P-51D, then Yak-3.
- G10N1, G10N2, He 111: compare first with B-29, then B-17 evidence if needed.

No acceptance threshold is changed by this document.