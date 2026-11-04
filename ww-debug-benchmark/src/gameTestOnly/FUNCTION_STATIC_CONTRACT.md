# Static GameTest function inspection

`tools/verify_gametest_function_bytecode.py` inspects caller-supplied mapped
`GameTestRegistry.class` and `TestFunction.class` with JDK 17 `javap`. It
checks exact reference opcodes, owners, descriptors, occurrence counts and
bytecode order in the selected methods: conversion of a Method to a Consumer
followed by a TestFunction constructor call, the full constructor's Consumer
field assignment, and `run`'s field read followed by Consumer invocation.
Both inspected class snapshots are hashed and their SHA-256 values reported.

For the fixed Forge 1.20.1-47.4.20 development artifact, extract both class
files locally from a trusted mapped jar and use a trusted JDK 17 `javap`:

```text
python3 tools/verify_gametest_function_bytecode.py --registry-class /local/GameTestRegistry.class --function-class /local/TestFunction.class --javap /local/jdk-17/bin/javap
python3 tests/test_verify_gametest_function_bytecode.py
```

The output depends on the normal textual format produced by `javap -c -p -s`.
Check the reported hashes against independent records. The tool does not
authenticate the classes, jar or `javap`; fabricated tool output can mislead
it. Linux with JDK 17 was used for these checks; Windows is untested. It does
not redistribute any Forge class or jar.

This is a static reference count and ordering check, not a control-flow or
data-flow proof. It does not show that arguments or receivers have a particular
value, that instructions are reached, that any function was registered, or
that the classes are the ones loaded after runtime transformation. It does not
verify Mixin discovery, hook application, selected tests, callbacks, world
isolation, player takeover, or cleanup. Passing does not authorize a server
or GameTest run.
