# Synthetic formation write sequences

This standalone observation uses the checkout's actual `ReflectiveAircraft` with
synthetic entity and setter classes. It compares three **fixture-defined** sequences:
base followed by different formation inputs; base alone; and base followed by the
same base inputs. These are not the real arbiter or a policy recommendation.

Run from the repository root with Python 3 and a JDK 17 installation:

```sh
python3 ww-debug-benchmark/tools/observe_formation_write_policy.py \
  --java-home /absolute/path/to/jdk-17 \
  --output /absolute/path/to/new-observation-directory
```

The output directory must not already exist. The runner uses four support stubs from
`observe_reflective_setters.py`, compiles with an empty application classpath and
sourcepath, and runs each of nine fault scenarios under all three sequences in fresh
JVMs. The scenarios cover normal setters, each setter failing before or after its
first mutation, both failing before mutation, each failing before its second mutation,
and both returning normally without changing state. It checks every saved snapshot,
setter argument, invocation order, exception event, and synthetic mutation counter
against the case matrix; discrepancies cause a nonzero exit.

The report contains the commands, source and fixture hashes before and after, class
hashes, expected and observed data, and process exits. Per-case stdout, stderr, and
class-load logs are saved; generated classes include both the actual adapter and
synthetic classes. Hashes do not authenticate the files or capture the entire JDK.

The mutation counter represents a synthetic side effect. Equal invocation counts do
not prove equal real side effects, particularly when the setter arguments differ.
The comparison does not exercise formation or the real arbiter, terrain or collision
avoidance, combat, player control, stale state, a world, real aircraft physics, or
actual failure rates. It does not establish that suppressing or repeating a write is
safe and does not recommend retries.

The suppression sequence makes no second call, so a second-call fault specified
for that sequence never fires. Case count is not the number of triggered faults.
The runner disables Python bytecode *writing* when importing the support fixture;
this does not prohibit reading an existing valid cache. For the recorded v2 run,
the four generated support stubs were independently compared with the source
fixture. Python and its imported libraries and caches are not fully pinned.

The actual adapter source used by v2 had SHA-256
`1933d4443708cfa77eb1a0bf93fa1b668fd7f43b30862f37ba1fd0b508628067`;
the runner snapshot had SHA-256
`ce38d6d07686b4d055187b75d41d2117f1c79148682d0e23661eeb63691c34b1`.
A future integration comparison must separately establish which proposal the
actual arbiter writes, preserve terrain/collision/player/combat behavior, and
correlate the adapted input with the same call, session, entity and level. It must
also test unknown/stale cases and does not follow from this standalone matrix.
