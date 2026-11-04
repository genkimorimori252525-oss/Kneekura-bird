# Inspecting supplied build classes in fake defensive fixtures

These test-only utilities reproduce a local standalone investigation. They compile
fake fixtures, replace only the copies of three production classes and their nested
classes with caller-supplied build bytes, and check recorded cases. They do **not**
run Minecraft, exercise a world or native setters, validate weapons or friendly
fire, or prove that the supplied classes came from a particular commit. Build
provenance, callback reachability, reentrancy, ABA and changes between observation
times remain separate questions. A synthetic `null` capture is passed directly to
a private helper; it is not a claim that production can produce that capture.

Run these scripts only with trusted source, JDK, classpath, build files and evidence
paths in an isolated environment. They execute the supplied JVM and compile against
its classpath. They do not provide a network or process sandbox, authenticate input,
or defend against an adversary racing file or symlink changes. Never point them at
a real world. Output contains absolute paths, fake telemetry and logs; do not commit
or publish generated evidence, reports, caches, classes, dependencies or jars.
The class-origin verifier currently accepts canonical **Linux** `file:` URLs only;
Windows class-origin verification is unsupported and fails closed.

## Independent expected hashes

Supply a local JSON manifest from a previously fixed, trusted build record. Its
schema is the following; every `"<sha256>"` is a lowercase 64-digit SHA-256 and
all keys shown are required. `sources` must include every one of the 14 names in
`SOURCE_NAMES`, and `build_classes` every one of the 11 names in `TARGETS`, both
in `ww-debug-benchmark/tools/defensive_built_tools.py`. The three production source
hashes are additionally pinned by the existing actual-mode runners. Upgrade that
baseline deliberately; do not remove a failed hash check to make a run pass.

```json
{
  "runners": {
    "matrix": "<sha256>", "exceptions": "<sha256>", "wrappers": "<sha256>",
    "level_exceptions": "<sha256>", "null": "<sha256>"
  },
  "sources": {
    "ControlAuthorityArbiter.java": "<sha256>",
    "<each other SOURCE_NAMES entry plus .java>": "<sha256>"
  },
  "build_classes": {
    "ControlAuthorityArbiter.class": "<sha256>",
    "<each other TARGETS entry>": "<sha256>"
  },
  "classpath": {"/absolute/path/to/each/file": "<sha256>"},
  "classpath_order": ["/absolute/path/to/classes-directory", "/absolute/path/to/dependency.jar"]
}
```

`classpath_order` must equal the dependency JSON array exactly, including order.
For a directory entry, `classpath` contains the absolute path and hash of every
regular file recursively, not the directory itself; empty directories are not
represented. For a file entry, include its own absolute path and hash. Classpath
entries and discovered descendants that are symlinks are rejected. This does not
check symlinked ancestors or prevent races. Obtain these expected hashes and source
revision from an independently preserved build record; generating a manifest from
the same current files only checks internal consistency and does not authenticate
provenance. Dependency preparation and applicable reuse conditions remain the
operator's responsibility; no Minecraft/Forge files are distributed here.

## Run and verify

Provision Python 3.9+, Java 17 (`java`, `javac`, `javap`) and the mapped dependencies
required by the project. Create a dependency JSON array with existing absolute paths
in the intended classpath order. Choose a new output directory outside the checkout;
the wrapper refuses to overwrite an existing path. These example paths are
placeholders, not published artifacts:

```sh
python3 ww-debug-benchmark/tools/defensive_built_tools.py \
  --java-home /path/to/jdk17 --dependencies-json /path/to/dependencies.json \
  --build-classes /path/to/build/classes/java/main --manifest /path/to/expected.json \
  --output /path/to/new-private-evidence
python3 ww-debug-benchmark/tools/verify_defensive_built.py \
  --java-home /path/to/jdk17 --dependencies-json /path/to/dependencies.json \
  --build-classes /path/to/build/classes/java/main --manifest /path/to/expected.json \
  --evidence /path/to/new-private-evidence --report /path/to/new-private-verdict.json
```

The wrapper checks every original runner hash, requires each transform anchor to
occur exactly once, records generated runner hashes, and runs five suites serially.
It records staged class hashes before each case and after all cases, plus immediate
stdout/stderr/class-load hashes. The exceptions suite intentionally has eight exit-1
sentinel observations and four exit-0 no-sentinel observations; the wrapper's exit
0 alone does not validate them. The verifier checks fixed case names, args, recorded
hashes and class-load origins. Sentinel matching is by stderr text, not exception
object identity or type authentication. The level-swap and claimed/reentry cases
are fake observations; the latter reinstates state through a fake logger callback.
The verifier and wrapper share the generation function, so their agreement is not
an independent proof of the transform. Class hashes and output hashes constrain the
recorded observation times; they cannot establish no changes between those times.

Optionally inspect the three public descriptors and a caller-pinned jar:

```sh
python3 ww-debug-benchmark/tools/inspect_defensive_built_package.py \
  --java-home /path/to/jdk17 --build-classes /path/to/build/classes/java/main \
  --manifest /path/to/expected.json --evidence /path/to/new-private-evidence \
  --jar /path/to/project.jar --jar-sha256 '<expected-jar-sha256>' \
  --report /path/to/new-private-package-report.json
```

The jar check limits entry count and uncompressed sizes before reading entries,
checks the supplied jar hash first, and looks for target entries, the known fake
`Probe` name and exact fake class bytes. Reobfuscation can alter bytes: absence of
exact matches is not proof that semantically equivalent fake code is absent. No
jar is extracted, copied into the checkout or redistributed by these tools.
