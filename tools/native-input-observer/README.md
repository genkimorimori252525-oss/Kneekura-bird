# Isolated native input observer (experimental, offline build only)

This separate test-only MOD source is **not** a benchmark source set, dependency,
configuration, manifest entry, or normal artifact. It targets only the fixed
Minecraft 1.20.1 / Forge 47.4.20 / Immersive Aircraft 1.3.3+1.20.1 Forge mapped
classes used in this investigation. It supplies no game or third-party code.
Its artifact is not suitable for distribution, ordinary worlds, ordinary play,
or other versions; remapping, refmaps and production-runtime compatibility
have not been demonstrated. `remap=false` applies to the target IA names only.

Build without network, writing to a **new directory outside the worktree**:

```sh
JAVA_HOME=/workspace/.cloud-setup/jdk-17.0.17+10 \
GRADLE_USER_HOME=/workspace/.cloud-setup/gradle-home \
tools/native-input-observer/build.sh /tmp/observer-build-NEW
```

The build requires exactly one cached mapped Forge jar and IA jar with the
specified names, compiles with Java 17 and annotation processing disabled,
runs the JDK-only buffer test, and checks the standalone JAR contents. It does
not establish dependency hashes, transform/load order, interoperability with
other mixins, normal artifact contents, or actual hook execution. Cache jars
must be matched to the preserved fixed MOD hashes and dependencies before any
runtime experiment. No normal project build configuration is modified.

The callbacks are non-cancellable and never deliberately write aircraft state.
Only an explicit `-Dwwdebug.nativeInputObserver=enabled`, GameTestServer, server
thread, and exact D4Y object/UUID/world can be armed. One scope binds the entity
reference, UUID, server, world and unique run token; a boundary shares the
monotonic event sequence. Disarm returns these identifiers and a bounded trace.
Axis/engine floats are raw bits. Each setter records arguments and axes at
HEAD/RETURN, a short caller classification/stack, server/game/entity ticks,
side, pilot kind and local-player flag. `tickCount` is not proof of an actual
entity tick. `native_tick_pilot` is a stack classification, not proof of origin
if another mixin modifies that method. `FakePlayer` is not a real client.

`ready()` only indicates minimum evidence for the **whole closed trace**:
HEAD/TAIL and setter HEAD/RETURN, a completed same-value setter, a boundary,
no overflow, unmatched calls, unknown caller, clipped stack or observer error.
It does not prove a specified observation window contains any hook. The later
fixture must validate start/end boundary identities and order, requested ticks,
positive and non-target/unarmed negative controls, expected same-value setter,
all hook sequences and target identity. Missing, wrong-thread, truncated,
overflow, class-load, missing report or undischarged arm are inconclusive, not a
pass. Exceptions, unexpected termination and final cleanup need external checks.

Do not add this JAR to the normal runtime. Even with no scope armed, injected
callbacks, argument boxing and synchronization can affect timing; linkage or
initialization errors can prevent the target from running. Positive hooks alone
cannot prove absent hooks in a particular window. Future work must use an
isolated fresh world and separate JVM, no parallel experiment, verify the
explicit opt-in, exact selected test count, addon discovery/configuration and
transformed classes before relying on observations. Save complete logs, input
hashes and the closed report. This commit contains **no** fixture wiring or
runtime test. Runtime observers may change scheduling; causal conclusions need
separate controls. Preserve failed worlds and logs; remove only the disposable
addon/output after evidence is saved. Reverting this commit restores source state.
