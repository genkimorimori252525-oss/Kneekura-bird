# Offensive pending pilot: standalone fixture

This is a synthetic baseline investigation for Issue #7, not a production change,
Minecraft/Forge GameTest or aircraft qualification. Its baseline is commit
`d34594f3186b13401c3e9097685435dbfbf0f5b8` (#218). The runner compiles unmodified
copies of 18 production source files, including the offensive manager, action and
doctrine, facade, arbiter, pilot gate, defensive manager, formation and autonomous
flight managers. It uses fake world/entities, target awareness and solution, aircraft
and armament reflection, flight snapshot, terrain, logging, weapon manager and
energy provider. The mapped dependency classes and fake classes are distinguished
in the saved class-load logs. No real world or native aircraft setter is invoked.

For the two red contracts, a fake `Entity.isRemoved()` callback fires only under
the arbiter's generic pending-write guard. It checks that the real offensive manager
already produced an aim entry and adapter log while pilot A was present. The callback
then switches to a different Mob object B; a separate case uses equal UUID values
but distinct pilot objects. In this fixture the base setter has already been called
with A and the later fake setter receives B. Both cases fail the explicit contract
that no stale offensive pending input is written. The fake callback is after facade
proposal selection in this call path, but is not evidence that this callback or
pilot takeover occurs naturally in Minecraft. A return label or fake setter call
also does not prove successful native control.

The fixture reports 25 cases in the saved v4 run: the two intended contract
assertions exit 1, and 23 controls exit 0. The level-object switch is explicitly an
observation rather than an identity-safety assertion. Player, empty seat, client
and removed callbacks test the existing pending guard within the fake fixture.
The source and trace place the status lookup's UUID evaluation before the pilot
getter inside offensive control; the fake trace alone does not establish native
runtime behavior or getter exception ordering.

After seeding real offensive state and aim with a successful proposal, separate
fake target-loss, missing-target and no-gun cases check state/aim removal and the
corresponding clear log. A second aircraft UUID has seeded state/aim and remains
unchanged. In the no-gun case the fake armament trace observes aim already present
before the gun lookup and confirms shots are read; it does not prove that no
intermediate state changed. A separate facade `collisionRisk=true` case checks
that the existing offensive state/aim remain present when the facade returns early.
The runner also tests fake energy proposal, claimed and direct-write paths; real
defensive proposal; an artificial defensive claimed path where a fake logger
reinstates state; and real formation collision-direct versus risk-only behavior
using fake world geometry. Fake energy is not the real DOCTRINE path, fake logger
reentry is not a natural runtime claim, and the fake weapon tick is not a firing
or friendly-fire test. Getter exceptions and `output == null` are not covered.

The local record `offensive-pilot-red-v1/` failed to reach offensive control because
the chosen target geometry activated collision avoidance; it is a fixture failure,
not the stale-input red. `offensive-pilot-red-v2/` changed only target relative
velocity for the initial contrast. `offensive-pilot-red-v3/` added the seeded
clear and risk cases, and `offensive-pilot-red-v4/` added the priority controls.
Each has a matching `-outer/` directory under `/workspace/issue7-evidence-20261104/`.
V4 records input/classpath hashes, 73 staged class hashes immediately before and
after each case, and immediate stdout/stderr/class-load hashes. A separate local
`offensive-pilot-red-validation-v4/` checks the saved records and class origin for
the swap/same-pilot cases. These observations do not establish that no changes
occurred before acquisition or between the recorded moments. Local evidence paths
are not published artifacts and can contain environment-specific paths.

The v4 runner snapshot SHA-256 is
`c4f6fe9de97b5491f02784ddb0ae201548833a729bbf45915b02960558631b0e`.
A separate local `offensive-pilot-descriptors-v3/` records the fixture-generated
public offensive, facade, arbiter and pilot-gate descriptors. It is not an actual
MOD runtime check.

To reproduce with provisioned Java 17 and mapped Minecraft/Forge dependencies,
prepare a JSON array of existing absolute classpath entries and run from the checkout:

```sh
python3 ww-debug-benchmark/tools/inspect_offensive_identity.py \
  --java-home /path/to/jdk17 --dependencies-json /path/to/dependencies.json \
  --output /path/to/new-private-evidence-directory
```

The output path must not exist. Record the outer process exit separately; exit 1
is expected because the two stale-pilot assertions deliberately fail. Verify each
case, source/copy and input hash, class origin, and stage/output hashes; a compile
failure, a different assertion or changed inputs is inconclusive. Outputs include
local paths and logs and must be reviewed before any publication. The fixture does
not prove real offensive behavior, callback timing, combat, player takeover,
weapon safety, terrain or collision avoidance, or pilot skill.
