# Standalone protected-corridor geometry check

The Java harness exercises Minecraft's `AABB`/`Vec3` and the production geometry
predicate. It tests the existing center-radius protection together with a tall narrow
body, tangencies, endpoints, zero-length segments, separated controls and invalid or
overflowing numeric inputs. A fixed-seed Python `Fraction` oracle separately compares
15,000 synthetic segment/box cases against the Java predicate, including near-corner and
widely scaled inputs. Conservative blocks outside the exact box can also be caused by the
pre-existing center-radius guard; this sample is not an operational false-positive rate.
For seed 42507 in this environment, the initial naive double-slab candidate missed 220 of
12,971 exact intersections; the outward-rounded candidate missed none. The naive candidate
blocked 771 exact nonintersections and the outward-rounded candidate blocked 1,029; these
figures include the existing center-radius guard and reflect the deliberately boundary-heavy
synthetic sample. All 1,000 ordinary separated controls remained unblocked. The oracle
records its generated input and decision checksums and Python version.
It does not create a world, run Forge GameTests, classify
real entities as friendly, verify line-of-sight, or prove actual projectile trajectories.
The production helper checks finite coordinates for candidates it receives; it does not
establish that invalid input cannot be omitted by the earlier world-entity broad-phase query.
Runtime performance, projectile motion and actual MOD behavior have not been measured.

First compile the project by the approved build path. Obtain an existing newline-delimited
list of the exact dependency jars separately; do not run a GameTest preparation task merely
to obtain this list, as it can modify a run directory. Then run from this directory:

```text
python3 tests/run_protected_corridor_check.py \
  --classes /path/to/build/classes/java/main \
  --classpath-file /path/to/dependency-jars.txt \
  --java /path/to/jdk-17/bin/java --javac /path/to/jdk-17/bin/javac \
  --evidence /path/to/new-evidence-directory
```

The runner refuses an existing evidence directory, records subprocess arguments, exit
codes and dependency/class hashes before and after, and fails if these inputs change.
The hashes identify the observed compiled classes and jars; they do not prove that the
classes were built from the source checkout. Keep evidence private until paths are reviewed.
Subprocesses use the new evidence directory as their working directory so any JVM logs stay
with that run rather than appearing in the checkout.
The runner does not alter the production jar or its build tasks. JDK 17 is required;
Windows and alternate JVM distributions have not been validated.
