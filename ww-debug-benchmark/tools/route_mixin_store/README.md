# Route-guidance STORE observation

This test-only fixture compares the untransformed `applyControl(Entity)V` bytecode of the fixed #214 Gradle output with a previously compiled #207 *private source-copy / stand-in* candidate. The #214 route-guidance Mixin declares `@ModifyVariable` at `STORE` with the `FlightControlOutput` type and type-based `ordinal=0`. The fixture checks that the fixed baseline calls `AutopilotSession.tick` followed immediately by ASTORE and that the #207 wrapper has no STORE while the moved body still has the tick/ASTORE pattern. This is a structural observation, not a general compatibility rule: it does not run Mixin, emulate its local discriminator, prove injection success or failure, or launch Forge, Minecraft, aircraft, or a world. The two classes were built under different conditions; the candidate is not a production Gradle class.

The separate #157 verifier examines arbiter call-site order, not this manager's STORE. This fixture pins exact source, Mixin, baseline class and candidate class SHA-256 values; it is not a generic verifier for future builds. The referenced #214 build metadata and #207 source-copy report support provenance, not an independently reconstructed build. A Gradle-built class is still untransformed bytecode and not evidence of actual Mixin runtime behavior.

Run with Python 3, JDK 17 and a trusted ASM 9 jar. Supply the existing fixed inputs from preserved evidence; neither binary nor raw logs belong in the repository. Replace the placeholders with verified absolute paths:

```sh
python3 tools/observe_route_mixin_store.py \
  --baseline-class /path/to/214/AutonomousFlightManager.class \
  --baseline-provenance /path/to/214/metadata-after.json \
  --candidate-class /path/to/207/AutonomousFlightManager.class \
  --candidate-source /path/to/207/source-copy/AutonomousFlightManager.java \
  --candidate-provenance /path/to/207/report.json \
  --asm-jar /path/to/asm.jar \
  --java-home /path/to/jdk17 \
  --output /path/to/new/evidence-directory
```

The output must not exist and must be outside the checkout. It records commands and individual exits, stdout/stderr and class-load output, fixed input snapshots, before/after input hashes, observer classes, an artifact hash inventory, and summary. ASM parses the supplied class bytes without loading the target aircraft manager. For exceptions caught in the observation block, the runner attempts to write `failure.json` alongside any captured evidence. Setup failures before that block, or failures that prevent writing the failure record, can leave only partial output; treat these as inconclusive and use a fresh path for the next attempt. The input guard can fail before any output is created. The inventory is collected after the processes finish, not atomically with raw output, and hashes of JDK launcher executables do not fingerprint the full JDK. Keep the original evidence and trusted dependency/source provenance for later reproduction.
