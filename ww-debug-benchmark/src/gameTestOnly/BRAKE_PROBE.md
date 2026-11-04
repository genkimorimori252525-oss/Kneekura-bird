# Brake pilot ownership probe: preparation only

This is an experimental GameTest fixture based on main `2585f44`. It has **not** been compiled,
registered, or run. It does not fix the production writers and is not a qualification result.
Keep this source and its dedicated `wwdebug_brake_probe:empty` structure out of a production jar.

## Hypothesis and observations

On main, `applyPostPhysics` and `AutopilotWheelLockAdapter.apply` look up a BRAKE session but do
not ask whether a mob currently controls the aircraft. The probe creates one real A6M and a mob,
starts an autonomous session, and seeds its phase to BRAKE by reflection. It seeds the entity's
ground flag rather than demonstrating an actual landing. While holding that exact session and
server tick constant, it tests the two writers separately with a positive mob control and
nonzero velocities, then repeats each call with an empty seat and a mounted FakePlayer. Finally,
it establishes the post-physics lock while the mob controls the aircraft and repeats that writer
with an empty seat and a FakePlayer. All assertions run synchronously; no native tick is invoked
between dismount, takeover, and writer calls.

A failure establishes only the direct-call fixture result. A pass does not establish natural
BRAKE entry, actual ground contact, the ordering of `tickPilot` and the server END event,
same-value writes, the behaviour of a network player, client/server interactions, or other
control writers. It also does not prove uninterrupted control during unobserved ticks. The
exception-abort investigation is separate and is not used by this fixture.

## Isolation prerequisites, not yet established

1. Main's Gradle configuration does not register `src/gameTestOnly`; draft #156 supplies a
   candidate source-set mechanism, but Forge GameTest and resource discovery have not been
   established. Use a separately reviewed test-only wiring/launcher; do not move this fixture
   into the production source set or assume it is discovered.
2. Before any Gradle task that prepares the run, independently verify a new, canonical,
   disposable checkout and run directory, a single JVM, and the fixed Java, Forge, Minecraft,
   profile and MOD hashes. Preserve prior worlds and logs. A property value is an attestation,
   not evidence that a directory is safe. Existing preparation tasks can delete/replace files.
3. Select only namespace `wwdebug_brake_probe`, the single test
   `stalebrakepreservespilotauthority`, batch `brake_pilot_ownership_probe_only`, and structure
   `wwdebug_brake_probe:empty`. An external pre-run gate must verify exactly those values and
   the captured before/after callbacks for the actual `GameTestBatch`: the check inside the
   fixture runs too late to prevent another registered test or batch callback from executing.
   Forge GameTest generators and MOD startup may also have side effects before that gate;
   verify the exact classpath and a new isolated world independently. The supplied NBT is the
   repository-generated 1×1×1 empty
   template copied into the test-only resource directory; its SHA-256 is
   `c75915fdc27b42c6b88f422082dcae3a1e477e1395b15bf2052d569b965a81e6`.
4. The spawn coordinates `(1, 2, 1)` are outside the 1×1×1 template. Do not rely on GameTest
   structure cleanup to remove these entities. Confirm no existing entities, autonomous state, or logs are at risk, and externally observe
   the world and GameTest-managed chunks. The fixture never forces or releases chunks. Set
   `wwdebug.brakeProbeIsolation=fresh-disposable-world-single-jvm` only after independent
   isolation verification. The exact property injection and runtime discovery remain to be
   verified; do not infer them from this document.
5. Capture the process exit, selected registry, all per-case failures, cleanup and log evidence.
   The GameTest must have truly run; an empty selection, a failed precondition, or a log API
   call alone is not proof. No MOD jars, raw personal data, or unrelated world data should be
   published. Keep a failed disposable world rather than clearing unidentified entities/chunks.

Before cleanup, the fixture requires the server thread, unchanged tick and world, successful
registration of both fixture entities, the captured session/aircraft object identities, and no
unidentified aircraft passenger, pilot passenger, or other vehicle. Any partial creation,
unidentified session or occupant, or unexpected observation aborts cleanup and preserves the
remaining state. It dismounts only its FakePlayer and mob, stops only the captured session, and
discards only its own entities. It rechecks observed identity and expected changes after each
operation and never retries an unknown outcome. Earlier successful operations cannot be undone.

`forceStop(UUID)` re-fetches the session internally; checking the entry before calling it is
not atomic with that lookup. Server-thread execution and the single-JVM attestation do not prove
that no other thread or callback can mutate these maps between observations. External exclusion
of concurrent mutation and proof of fixture ownership are prerequisites for a real run, not
established by this fixture. Its checks also do not prove chunk ownership, complete log closure,
or absence of effects elsewhere in the world. The separately maintained `cleanup_model` tests
are a pure contract model and do not prove this Java fixture or actual Forge cleanup; they are
not included in this fixture-only branch.
