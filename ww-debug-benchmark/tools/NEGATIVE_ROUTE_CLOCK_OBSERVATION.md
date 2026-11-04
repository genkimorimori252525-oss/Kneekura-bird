# Negative formation checkpoint clock: standalone observation

Run from `ww-debug-benchmark` with a JDK 17 installation and a new output
directory outside the checkout:

```text
python3 tools/observe_negative_route_clock.py --java-home /path/to/jdk17 --output /path/to/new-output
```

The runner compiles the checkout's real `FlightPhase` and
`MissionRouteClockPolicy` with an isolated classpath and directly calls the
policy. It records source/JDK/runner and generated-class SHA-256 hashes,
commands, raw stdout/stderr and exits. It refuses an existing output path and
never runs Gradle, Minecraft or a world.

`formation` checkpoint seeds the phase clock at −500. The direct −499 input
represents an ordinary next-tick increment only if no transition or other
adjustment intervenes. Its expected `IllegalArgumentException` and the
nonnegative controls characterize the helper, not whether the route bridge
actually holds a live formation at that moment. The runner does not invoke the
Mixin, route manager, actual aircraft, or a GameTest and does not establish a
production failure or offline qualification. Inspect `report.json`; a missing
case, changed input, nonzero exit or incomplete report is inconclusive.
