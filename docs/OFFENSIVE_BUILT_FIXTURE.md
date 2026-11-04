# Inspecting the offensive built classes in a synthetic fixture

After an offline build and a saved `actual` source run from
`OFFENSIVE_PILOT_CANDIDATE.md`, a separate optional check stages 12 Gradle-built
classes over the synthetic fixture's corresponding classes:

```sh
python3 ww-debug-benchmark/tools/inspect_offensive_built_fixture.py \
  --repo /path/to/checkout --actual /path/to/saved-actual-run \
  --expected-commit /replace-with-current-commit-id \
  --java-home /path/to/jdk17 --dependencies-json /path/to/classpath.json \
  --output /path/to/new-built-check
```

The output directory must not exist. The expected commit is an exact Git object
ID, not a revision expression. The checker compares the three production source
hashes to the actual run and checks for tracked worktree changes; it does not
inspect untracked files. It inventories each staged class before and after each
case, checks observed target-class origins in class-load logs, requires the three
top-level target classes to load, compares the saved
actual exit codes and stdout excluding the terminal-feature warning, and stores
stderr and class-load hashes. Recorded input hashes and local Git state are not
authentication and snapshots do not exclude intermediate mutations.

The original artificial armament stub's `Gun` type differs from the built
production class's `MountedWeapon` generic type. The checker compiles a copy
of the same artificial stub with only that type renamed and records both source
hashes and compiler output. It does not exercise a real armament or prove
firing, friendly-fire prevention, Minecraft runtime behavior or setter success.
Dynamic lambda classes are not included in the physical target-file origin
assertions. Origin checks URL-decode and resolve paths, including symlinks;
they are not a strict textual-canonical-path or filesystem identity guarantee. A prior check without this adjustment failed with a synthetic
`ClassCastException`; preserve that failure when reporting later results.

The source-run exception cases intentionally exit 42. Their matching exits and
stdout are comparisons, not passing flight or weapon tests. This check does not
compare stderr content with the source run; it records each stderr hash. It
also does not establish record reflection or binary compatibility, determine
jar contents, or prove the identity and completeness of Gradle inputs.

The checker constructs its own Java and compiler commands from the explicit
JDK, an explicit JSON array of absolute dependency paths, and a fixed main class
and case list. Dependency paths must be existing directories or JAR/ZIP files;
their contents are hashed and compared with the saved run. The classpath uses
the JSON order, but the saved path-to-hash inventory cannot prove that order.
Extra or missing
case names are rejected. Commands saved inside the report are data and are not
executed. Java option environment variables are removed from child Java and
compiler invocations; the rest of the execution environment is still trusted. The report, fixture classes, JDK and dependencies still must be
trusted: their contents and recorded hashes are not authenticated, fixture or
dependency classes can execute code, and this tool is not a sandbox. Output
reports include local paths and command arguments; inspect them before sharing.
