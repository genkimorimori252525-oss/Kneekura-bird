# Recorded formation turn: stand-in observations

These test-only tools investigate the #214 formation run at commit
`80eab064420c217df66c2d42c3f8772ff4216add`. They do not start Minecraft,
modify a world, simulate aircraft motion, or verify native setter success.
The recorded-input tool compiles the actual session, manager, arbiter,
formation and safety-probe sources against fixture world, snapshots, terrain
planner, checkpoint, logger and setter. Combat and benchmark writers are also
stand-ins. The separate clock tool uses the actual session and fixture manager.

The two aircraft JSONL files for run `20261104-141751` had SHA-256:

- Wingman 2: `064dcea64372d8eb6f8ada6697549a379026e43252fc0659d44e7b9606e94e42`
- Leader: `8181ccb3d2228d9d7fbd8dd82385f51668a3e23720b014c024fdce2ce733a070`

The recorded-input runner embeds selected position, velocity, heading, pitch,
AGL, engine and profile values from server ticks 1549 and 1589. Its fake
checkpoint injects TURN_RIGHT with pre-tick phase clocks 399 and 439, a
derived target yaw of 44.555055 degrees, and a synthetic mission clock of
1000. Group slot is 2. The leader and wingman frames have the same server tick,
but their sampling is not proved simultaneous; all other fixture state is
synthetic. The timeout case changes only the injected phase clock to 440.

In the original stand-in run, the final fixture setter call had native x /
engine `0.0012139524 / 0.08` at tick 1549 and `0.0005601887 / 0.9` at tick
1589, following the base speed-recovery call `-0.35099998 / 1.0`. Without a
group, only the base call was recorded. A fake player produced no calls;
synthetic terrain and collision cases reached their respective fixture
setter calls. These observations do not show that formation caused the real
timeout. Recorded proposal versus fixture values differ: logical x at tick
1549 was -0.0012166143 versus -0.0012139524, and at tick 1589 was
-0.0005640182 versus -0.0005601887. At tick 1589 target speed was
14.5668622591 versus 14.2993737666. The cause of the differences is unknown.

The clock tool tests five injected states around the heading and timeout
boundaries. A completed heading takes precedence over timeout at pre-tick 440;
the transitioning invocation still returns the turn output. It does not
establish that real aircraft naturally reach any injected state.

Both tools require Java 17 and `--dependencies-json`, a JSON array of
existing absolute classpath entries containing Forge/Minecraft dependencies
and Gson. Use a classpath prepared for the fixed environment, review its
origins, and inspect the class-load logs: these tools record hashes but do not
prove classpath provenance. Each output path must be new; no world is needed.
For example:

```sh
python3 -I -B tools/test_formation_recorded_turn_observation.py \
  --java-home /path/to/jdk17 --dependencies-json /path/to/dependencies.json \
  --output /path/to/new-recorded-output
python3 -I -B tools/test_formation_turn_clock_observation.py \
  --java-home /path/to/jdk17 --dependencies-json /path/to/dependencies.json \
  --output /path/to/new-clock-output
```

The resulting reports contain the named source and fixture hashes before and
after compilation, classpath hashes, commands, exits, and class-load logs.
Review the actual source identities and per-case outputs; an unreachable case
or missing assertion is inconclusive rather than a successful test. The
historical report and real MOD execution evidence remain separate artifacts.
