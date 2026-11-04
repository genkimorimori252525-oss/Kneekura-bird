# GameTest startup call-site inspection

`tools/verify_gametest_main_bytecode.py` inspects one supplied mapped
`net.minecraft.server.Main` class using JDK 17 `javap`. It checks that the
private static `lambda$main$4` method has the expected descriptor and exactly
one occurrence, in bytecode order, of Forge registration, registry retrieval,
batch grouping and the GameTestServer constructor calls with their expected
owners, opcodes and descriptors. It reports the SHA-256 of the same class
bytes passed to `javap`. Missing or ambiguous calls and tool errors fail.

The caller supplies a local `Main.class` extracted from a trusted mapped Forge
1.20.1-47.4.20 jar and the local JDK 17 `javap` path:

```text
python3 tools/verify_gametest_main_bytecode.py --class-file /local/path/Main.class --javap /local/path/jdk-17/bin/javap
python3 tests/test_verify_gametest_main_bytecode.py
```

Compare the reported class hash with the independently recorded expected hash;
the tool does not authenticate the jar, class, `javap`, or environment. The
development check was performed on Linux; Windows has not been verified. The
class and jar are not redistributed with this verifier. The temporary class
snapshot exists solely for inspection and is removed on normal completion.

This is a static check of instruction presence and order in one method, not a
control-flow, reachability or data-flow proof. It does not inspect other Main
paths, prove which object is passed to the constructor, identify the registered
test or callbacks, or establish a server's selection. Runtime transformers,
Mixin discovery and application, world isolation, player takeover, forced
chunks and cleanup are outside its scope. Passing does not authorize a GameTest
run; the #159 batch inspector has separate, unmet prerequisites.
