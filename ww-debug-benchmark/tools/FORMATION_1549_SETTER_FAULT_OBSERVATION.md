# Reconstructed formation setter failure observation

This standalone fixture uses the checkout's actual `ReflectiveAircraft` source
and the synthetic setters from the #203/#206 observations. It compares two
scripted two-call sequences using values from #226's tick-1549 **stand-in
reconstruction**: base `(-0.35099998, 0, -0.15, 1)` followed by either formation
`(0.0012139524, 0, -2.341649E-4, 0.08)` or the same base values again.

Run with Python 3, JDK 17, and a new output path outside the checkout:

```text
python3 -I -B tools/observe_formation_1549_setter_faults.py \
  --java-home /path/to/jdk17 --output /path/to/new-output
```

The runner refuses an existing output path, compiles using an empty classpath
and sourcepath, and saves source/JDK/runner and class hashes, exact commands,
case exits, stdout/stderr, class-load logs and the independent matrix oracle.
Eight artificial setter conditions are paired with both sequences: success,
first input or engine failure before or after mutation, second input or engine
failure before mutation, and both methods returning without changing state.
The no-op case does not cover each method independently. An incomplete report,
nonzero exit, changed hash or unexpected class origin is inconclusive.

These fixed calls are not the actual arbiter and do not test Minecraft, Forge,
terrain, collision, player takeover or flight physics. #226's two sampled
aircraft need not represent the same instant. A fake exception after mutation
is not evidence that a real setter behaved that way; this fixture does not
establish setter failure frequency or whether suppressing or repeating a write
is safe. Preserve any output and use a new directory for a later run.
