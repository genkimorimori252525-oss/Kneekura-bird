# Apex-yaw re-engagement handoff

Draft PR #9 is preserved as research history. Its full-pitch vertical reversal creates separation but rotates the P-47N through approximately -180 degrees, then spends excessive altitude recovering from a steep descent. Pullout bridges preserved ground safety but did not create a firing solution.

The exact Immersive Aircraft 1.20.1 source establishes the aircraft input semantics:

- X directly changes yaw and drives visual roll;
- Y changes engine target and braking;
- Z directly changes pitch.

The next clean implementation must therefore use an apex-yaw wingover rather than a full vertical loop:

1. climb with negative Z only to roughly -75 to -85 degrees pitch;
2. hold near the apex and use X to reverse horizontal heading while retaining altitude;
3. use positive Z to return toward level flight instead of crossing -180 degrees;
4. recover toward measured lead and hand back to ordinary doctrine;
5. preserve terrain, collision, threat, LOS, range, friendly-fire, fixed-gun cone, and rear-target gates.

Carry only the test-only deterministic UUID ordering from PR #9. Do not carry `EnergyFighterPulloutAdapter`, full-loop thresholds, or marker files.

Validation order: compile/deterministic simulation, one `dogfight_mutual`, inspect apex pitch/yaw/AGL/shot counts/separation/ground contact, then repeat only after a safe reciprocal-firing pass.
