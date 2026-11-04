# Reflective setter observation

This standalone test compiles the checkout's `ReflectiveAircraft.java` with synthetic
Minecraft types and a synthetic aircraft. It observes two ordered calls to the existing
adapter; it does not start Minecraft, Forge, Gradle, or a world. The nine scenarios are
both setters returning normally, each setter throwing before mutation on the first call,
both throwing before mutation on the first call, each throwing after mutation on the
first call, each throwing before mutation on only the second call, and both returning
normally without changing state.

From the repository root, using Python 3 and a JDK 17 installation with `java` and
`javac` in its `bin` directory:

```sh
python3 ww-debug-benchmark/tools/observe_reflective_setters.py \
  --java-home /absolute/path/to/jdk-17 \
  --output /absolute/path/to/new-observation-directory
```

The output directory must not already exist. The runner compiles with annotation
processing disabled and an empty application classpath and sourcepath, and starts a
fresh JVM for each scenario. `report.json` records input hashes before and after,
generated class hashes, commands, and exit codes. Each scenario has stdout, stderr,
and a class-load log. `classes/` contains both the real adapter compiled from source
and the synthetic classes; the directory name alone does not distinguish them. The
runner snapshot and generated synthetic source files are also saved. Hashes do not
authenticate the files, and the executable hashes do not cover the complete JDK.

At the source used for the initial observation, `ReflectiveAircraft.java` had SHA-256
`1933d4443708cfa77eb1a0bf93fa1b668fd7f43b30862f37ba1fd0b508628067`.
The initial runner had SHA-256
`ebff31a31eff140a78915697a6a80ccb1b9f39b25869d73c1666cfb3b3d6fa6a`.
Compare a new report's input hashes before comparing observations across revisions.

The second call deliberately repeats the same inputs to expose possible repeated
side effects; it is not a recommendation to retry. These synthetic exceptions,
mutations and no-op methods do not establish how often actual setters fail, whether
they change real aircraft state, or whether a retry is safe. The test does not exercise
formation, the arbiter, pilot takeover, or aircraft physics.
The fixture asserts setter call and mutation counts, recorded values, and call
order. Its detailed throw-before/throw-after event strings are observations in
stdout; they are not independently asserted as exact strings. Capture the outer
runner exit separately, and treat missing output, changed hashes, an unexpected
class origin, or any nonzero case as inconclusive.
