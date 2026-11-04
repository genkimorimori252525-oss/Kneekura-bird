# Batch selection inspection (preparation only)

This test-only code inspects an already constructed, **trusted** Forge 47.4.20 development
`GameTestBatch` selection at one instant. It does not register, launch, stop, or authorize a test,
and it is not yet connected to a Mixin or other execution hook. Minecraft and GameTest servers,
worlds, entities and chunks are not started or touched by the standalone checks.

The inspector requires exactly one actual `GameTestBatch` and one exact expected `TestFunction`
object, with the brake probe's expected batch, test, structure and required flag. Expected before
and after callbacks must each be explicitly supplied as known absent or as an exact known object.
An unknown expected test/callback, a mismatched identity, unreadable selection or inaccessible /
changed private callback field yields an error. It does not invoke the test or batch callbacks.
The mapped Forge fields `beforeBatchFunction` and `afterBatchFunction` are read reflectively;
the inspection rejects non-private, non-final, static or non-Consumer fields. Production or
obfuscated field names and module accessibility are not established; reflection failing is a
rejection, not proof that callbacks are absent.

A caller **must independently authenticate** the expected `TestFunction` and callbacks; deriving
expectations from an untrusted selected collection would make the identity comparison meaningless.
The `GameTestBatch` constructor retains its test collection: a successful inspection does not stop
later changes. A trusted immutable snapshot and an independently evidenced handoff to the actual
runner are needed before using any check as a pre-execution gate. The inspector assumes its
collection implementation is trusted: `List.copyOf` can run its `toArray`/iteration code.
Linkage errors, failures outside the call, and an outer process's exit status are not guaranteed.
It does not inspect the `TestFunction` body, rotation, retry policy or executable validity.
Generators and MOD initialization can have effects before the batch is built. None of the checks
proves Mixin application, registration provenance, a server's selection, world isolation,
cleanup, chunk ownership, or player/flight safety. Do not run the brake fixture on this evidence.

## Local verification

From `ww-debug-benchmark`, use JDK 17 and Gradle 8.8 with the existing network/proxy policy:

```text
gradle --offline --no-daemon --no-configuration-cache -I tools/verify-gametest-isolation.gradle verifyExternalGameTestIsolation
```

That task compiles `gameTestOnly` and checks the current test-only outputs against the normal jar;
it exercises the separate classpath marker, not this standalone driver. To run the driver's tests,
use the **actual mapped** Forge 1.20.1-47.4.20 development jar and JDK 17. On POSIX with
`FORGE_MAPPED_JAR` set to that local jar's absolute path:

```text
java -cp "build/classes/java/gameTestOnly:$FORGE_MAPPED_JAR" com.wwdebug.gametestprobe.GameTestBatchGateChecks
```

The driver constructs synthetic real `GameTestBatch` / `TestFunction` objects with a null rotation;
it deliberately does not initialize the full Minecraft runtime. Its cases cover cardinality,
identity, names, required status, callback matching, exceptions, field shape and reinspection after
mutation. A red always-allow stub showed a missing expected identity was incorrectly accepted. A
first green Java command used a mistyped classpath and failed with `ClassNotFoundException`; that
failed attempt and the corrected result are preserved separately. These are local class-level
checks, not an actual registered TestFunction or real GameTest result. Windows is untested.

Rollback is to revert this commit; no world, cache, aircraft jar, runner or network policy needs
changing. Keep logs and previous failed evidence rather than deleting them.
