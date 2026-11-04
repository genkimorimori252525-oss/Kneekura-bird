# Energy built-class synthetic comparison

This test-only tool checks locally built energy, offensive, facade and arbiter
classes using the saved actual-source stand-in fixture. It is separate from
production behavior, a Forge GameTest, a native setter check and real weapon or
friendly-fire validation. The fixture deliberately seeds state and injects fake
getter/logger callbacks; their natural occurrence is unproved.

For the local `075dd54b36b3de45622f446d342a4b28341fb9e9` build, the initial
`energy-doctrine-built-fixture-v1/` run failed: 23 scenarios encountered a
`NoSuchMethodError` because the fake `FlightSnapshot.rollDeg()` returned float
while the built class expects double. Its runner source was edited during the
run, so the executed runner's exact byte identity is also unconfirmed. Preserve
that failure. In a fresh v2, two **artificial fake** sources were copied and
adjusted: armament's `Gun` type renamed `MountedWeapon`, and snapshot's
`rollDeg` return type changed float to double. Their source hashes, unified
diff, javac output and snapshot descriptor comparison are saved. These fake
objects do not reproduce the real armament or aircraft physics.

The v2 run on that fixed local commit compared 26 cases with the prior
actual-source fixture: 24 synthetic control outcomes and two caught injected
exceptions, each asserting sentinel object identity. All selected exits and
stdout matched after removing the terminal-feature warning and replacing only
fake `Entity` object identity strings by per-run ordered labels; equality and
inequality of those labels are retained within a case. Stderr is saved and
hashed but is **not** compared with the source run. Nineteen target build class
files were copied to a new staged fixture and checked by hash before/after;
their actual observed class-load origins were checked against that stage. All
19 appeared in the suite union, while the checker explicitly requires only the
four top-level classes. Dynamic lambda origins are not asserted. URI decoding
and path resolution are not a guarantee against symlink races. Hash samples do
not prove continuous integrity, input authenticity or full Gradle provenance.

The normal Gradle offline build and its deterministic simulator provide their
own narrower evidence. The latter is a fast pre-flight model, not the real MOD;
the Gradle `test` task was `NO-SOURCE`. Prior GameTest results on other trees do
not qualify this change. The internal records' equality, reflection and external
hooks/Mixins remain unresolved; native setters, ABA, earlier state and input
side effects, and real player takeover remain unverified.

## Run

Use a trusted checkout at the exact expected commit, trusted saved actual-source
fixture, trusted JDK 17 and ordered JSON list of existing trusted dependency
paths. The program executes fixture and dependency bytecode, is not a sandbox,
and its hashes do not authenticate any input. Choose a new output directory
outside the checkout and any world:

```sh
python3 ww-debug-benchmark/tools/inspect_energy_built_fixture.py \
  --repo /path/to/checkout --expected-commit REPLACE_WITH_40_CHARACTER_GIT_SHA \
  --actual /path/to/actual-source/run --java-home /path/to/jdk17 \
  --dependencies-json /path/to/dependencies.json --output /path/to/new-evidence
```

Replace the example commit with a literal full Git SHA. The script constructs
its own command from explicit inputs and a fixed case list; it does not execute
saved report argv. It strips four Java option environment variables from the
child JVM and compiler, but otherwise trusts the environment. A timeout or
missing/inconsistent input is incomplete, not a pass. Inspect the report,
stdout/stderr, class-load logs, fake adjustments and input hashes before using
or sharing results. The saved inventory does not prove classpath order and can
contain local paths.
