package com.wwdebug.benchmark;

import com.mojang.authlib.GameProfile;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.core.BlockPos;
import net.minecraft.gametest.framework.GameTest;
import net.minecraft.gametest.framework.GameTestHelper;
import net.minecraft.gametest.framework.GameTestRegistry;
import net.minecraft.gametest.framework.GameTestServer;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.entity.decoration.ArmorStand;
import net.minecraft.world.phys.Vec3;
import net.minecraftforge.common.util.FakePlayer;
import net.minecraftforge.gametest.GameTestHolder;
import net.minecraftforge.gametest.PrefixGameTestTemplate;

import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicReference;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.stream.Collectors;

/**
 * Disposable-world probe only. The caller must independently prove the world is new and isolate
 * this one test in a separate JVM; the properties below are attestations, not freshness proofs.
 * Reset mode seeds phase tick 599 and calls BenchmarkManager.tick synchronously. Direct mode calls
 * BenchmarkManager.applyControl synchronously. Neither exercises a networked player or command.
 * Value snapshots cannot detect same-value writes, and do not cover attitude or fall distance.
 * Matching chunk sets cannot prove exclusive ownership or detect overlapping force requests.
 */
@GameTestHolder("wwdebug_benchmark_reset_probe")
@PrefixGameTestTemplate(false)
public final class BenchmarkPlayerResetIsolationGameTests {
    private static final String NAMESPACE = "wwdebug_benchmark_reset_probe";
    private static final String ATTESTATION = "fresh-disposable-world-single-jvm";
    private static final ResourceLocation AIRCRAFT = new ResourceLocation("warfare_wings", "d4y");

    private BenchmarkPlayerResetIsolationGameTests() { }

    @GameTest(template = "empty", timeoutTicks = 40, batch = "benchmark_player_reset_probe_only")
    public static void benchmarkPhaseResetRespectsPlayer(GameTestHelper helper) throws Exception {
        ServerLevel level = helper.getLevel();
        MinecraftServer server = level.getServer();
        BenchmarkProbeMode mode = BenchmarkProbeMode.parse(System.getProperty("wwdebug.benchmarkPlayerProbeMode"));
        WWDebugBenchmarkMod.LOGGER.info("benchmark_reset_probe mode={}", mode.name().toLowerCase(java.util.Locale.ROOT));
        check(server instanceof GameTestServer, "requires GameTestServer");
        check(ATTESTATION.equals(System.getProperty("wwdebug.benchmarkResetProbe")),
                "requires independent fresh disposable-world and single-JVM attestation");
        check(NAMESPACE.equals(System.getProperty("forge.enabledGameTestNamespaces")),
                "requires the dedicated namespace alone");
        var functions = GameTestRegistry.getAllTestFunctions();
        List<BenchmarkProbeRegistration.TestId> selected = functions.stream()
                .map(f -> new BenchmarkProbeRegistration.TestId(
                        f.getTestName(), f.getBatchName(), f.getStructureName()))
                .toList();
        WWDebugBenchmarkMod.LOGGER.info("benchmark_reset_probe selected_test_count={} tests={}",
                selected.size(), selected);
        check(BenchmarkProbeRegistration.isExpected(selected),
                "requires exactly this test, batch and template to be registered");

        Map<Object, Object> sessions = map(BenchmarkManager.class, "SESSIONS");
        Map<Object, Object> controls = map(BenchmarkManager.class, "CONTROLS");
        Set<UUID> heartbeats = benchmarkHeartbeats();
        Set<Long> forcedBefore = Set.copyOf(level.getForcedChunks());
        check(sessions.isEmpty() && controls.isEmpty() && heartbeats.isEmpty(),
                "benchmark state must be empty for the entire JVM");
        // The fixed GameTestServer uses no rotation and this template is 1x1x1; absolute
        // zero is the structure position passed to StructureUtils.forceLoadChunks.
        BlockPos structurePos = helper.absolutePos(BlockPos.ZERO);
        ChunkPos center = new ChunkPos(structurePos);
        Set<BenchmarkProbeForcedChunks.Chunk> expected = BenchmarkProbeForcedChunks.expected(center.x, center.z);
        Set<BenchmarkProbeForcedChunks.Chunk> actual = forcedBefore.stream().map(packed -> {
            ChunkPos chunk = new ChunkPos(packed);
            return new BenchmarkProbeForcedChunks.Chunk(chunk.x, chunk.z);
        }).collect(Collectors.toUnmodifiableSet());
        WWDebugBenchmarkMod.LOGGER.info(
                "benchmark_reset_probe world={} structure_pos={} forced_center=({}, {}) expected={} actual={}",
                server.getWorldPath(net.minecraft.world.level.storage.LevelResource.ROOT), structurePos,
                center.x, center.z, expected.stream().sorted().toList(), actual.stream().sorted().toList());
        check(BenchmarkProbeForcedChunks.matches(center.x, center.z, actual),
                "forced chunks must match the fixed GameTest structure footprint");

        Object session = null;
        Entity aircraft = null;
        FakePlayer player = null;
        ArmorStand knownPilot = null;
        UUID markerId = null;
        Object markerControl = null;
        boolean markerHeartbeatInstalled = false;
        Throwable failure = null;
        try {
            Object candidate = candidate(level);
            Class<?> sessionClass = Class.forName(BenchmarkManager.class.getName() + "$BenchmarkSession");
            Constructor<?> constructor = sessionClass.getDeclaredConstructor(CommandSourceStack.class,
                    BenchmarkCategory.class, boolean.class, List.class);
            constructor.setAccessible(true);
            // Use a fixed source position; constructor creates only the selected candidate.
            CommandSourceStack source = server.createCommandSourceStack().withLevel(level)
                    .withPosition(new Vec3(0.0, 80.0, 0.0));
            session = constructor.newInstance(source, BenchmarkCategory.ALL, true, List.of(candidate));
            check(sessions.putIfAbsent(server, session) == null, "another benchmark session appeared");
            List<?> active = (List<?>) field(session, "active");
            check(active.size() == 1, "singleton session failed to spawn its aircraft");
            Object test = active.get(0);
            aircraft = (Entity) field(test, "aircraft");
            ArmorStand pilot = (ArmorStand) field(test, "pilot");
            knownPilot = pilot;
            Vec3 anchor = (Vec3) field(test, "anchor");
            UUID aircraftId = aircraft.getUUID();
            check(aircraft.getType() == net.minecraft.core.registries.BuiltInRegistries.ENTITY_TYPE.get(AIRCRAFT),
                    "benchmark spawned a different aircraft");
            check(ReflectiveAircraft.passengerSpace(aircraft) >= 2, "D4Y needs two real seats");
            check(pilot.isPassengerOfSameVehicle(aircraft) && aircraft.getControllingPassenger() == pilot,
                    "benchmark ArmorStand must initially control the real aircraft");
            check(sessions.get(server) == session && controls.containsKey(aircraftId),
                    "real benchmark session and stored controls must be registered");
            // Native tick consumes fuel into its internal store; setup remains player-free.
            aircraft.tick();
            check(ReflectiveAircraft.fuelUtilization(aircraft) > 0.0, "benchmark needs usable fuel");
            WWDebugBenchmarkMod.LOGGER.info("benchmark_reset_probe aircraft={} pilot={} anchor={} forced_after_spawn={}",
                    aircraftId, pilot.getUUID(), anchor, Set.copyOf(level.getForcedChunks()));

            if (mode == BenchmarkProbeMode.DIRECT) {
                // The real session supplies a distinct, initially-zero stored input. Prove that
                // it reaches all four native inputs before introducing the player.
                Object stored = controls.get(aircraftId);
                check(stored != null, "direct positive control needs a stored benchmark input");
                heartbeats.remove(aircraftId);
                Snapshot positiveBefore = seedInputs(aircraft, anchor);
                BenchmarkManager.applyControl(aircraft);
                Snapshot positiveAfter = snapshot(aircraft);
                WWDebugBenchmarkMod.LOGGER.info(
                        "benchmark_direct_probe positive_before={} positive_after={} stored={} heartbeat={}",
                        positiveBefore, positiveAfter, stored, heartbeats.contains(aircraftId));
                check(positiveAfter.hasControls(0, 0, 0, 0) && heartbeats.contains(aircraftId)
                                && controls.get(aircraftId) == stored,
                        "direct positive control must reach the real inputs and emit a heartbeat");

                // A separate synthetic UUID proves the invalidation is target-specific.
                UUID other = UUID.randomUUID();
                check(!other.equals(aircraftId) && !heartbeats.contains(other), "marker UUID is not fresh");
                check(controls.putIfAbsent(other, stored) == null, "marker control already existed");
                markerId = other;
                markerControl = stored;
                check(heartbeats.add(other), "marker heartbeat already existed");
                markerHeartbeatInstalled = true;

                player = new FakePlayer(level, new GameProfile(UUID.randomUUID(), "WWDirectProbe"));
                check(player.startRiding(aircraft), "player must enter normally without force=true");
                check(aircraft.getControllingPassenger() == player && pilot.isPassengerOfSameVehicle(aircraft),
                        "player must control while benchmark ArmorStand remains aboard");
                Snapshot before = seedInputs(aircraft, anchor);
                check(controls.get(aircraftId) == stored && heartbeats.contains(aircraftId),
                        "stale input and heartbeat must exist immediately before takeover call");
                WWDebugBenchmarkMod.LOGGER.info(
                        "benchmark_direct_probe player={} passengers={} before={} stored_before={} heartbeat_before={} marker={} marker_stored={} marker_heartbeat={}",
                        player.getUUID(), aircraft.getPassengers().stream().map(Entity::getUUID).toList(),
                        before, controls.get(aircraftId), heartbeats.contains(aircraftId), other,
                        controls.get(other), heartbeats.contains(other));
                BenchmarkManager.applyControl(aircraft);
                Snapshot after = snapshot(aircraft);
                WWDebugBenchmarkMod.LOGGER.info(
                        "benchmark_direct_probe player_after={} stored_after={} heartbeat_after={} marker_stored={} marker_heartbeat={}",
                        after, controls.get(aircraftId), heartbeats.contains(aircraftId),
                        controls.get(other), heartbeats.contains(other));
                check(aircraft.getControllingPassenger() == player && pilot.isPassengerOfSameVehicle(aircraft),
                        "player must still control after the direct call");
                check(before.sameControls(after), "benchmark direct call must preserve player controls");
                check(!controls.containsKey(aircraftId) && !heartbeats.contains(aircraftId),
                        "player takeover must invalidate its stale control and heartbeat");
                check(controls.get(other) == stored && heartbeats.contains(other),
                        "player takeover must preserve another UUID's benchmark state");

                player.stopRiding();
                check(aircraft.getControllingPassenger() == pilot, "benchmark pilot must regain the controls");
                Snapshot dismountedBefore = snapshot(aircraft);
                BenchmarkManager.applyControl(aircraft); // no benchmark END tick between calls
                Snapshot dismountedAfter = snapshot(aircraft);
                WWDebugBenchmarkMod.LOGGER.info(
                        "benchmark_direct_probe dismounted_before={} dismounted_after={} stored_after={} heartbeat_after={} marker_stored={} marker_heartbeat={}",
                        dismountedBefore, dismountedAfter, controls.get(aircraftId), heartbeats.contains(aircraftId),
                        controls.get(other), heartbeats.contains(other));
                check(dismountedBefore.sameControls(dismountedAfter)
                                && !controls.containsKey(aircraftId) && !heartbeats.contains(aircraftId),
                        "dismount must not replay stale benchmark input before END");
                check(controls.get(other) == stored && heartbeats.contains(other),
                        "dismount must preserve another UUID's benchmark state");
            } else {
                // Positive control: same real session and phase, without any player passenger.
                seedPhase(test);
                Snapshot positiveBefore = seedInputs(aircraft, anchor);
                BenchmarkManager.tick(server);
                check(sessions.get(server) == session, "benchmark swallowed an exception in positive control");
                check("TURN_WARMUP".equals(field(test, "phase").toString()), "positive phase did not advance");
                Snapshot positiveAfter = snapshot(aircraft);
                WWDebugBenchmarkMod.LOGGER.info("benchmark_reset_probe positive_before={} positive_after={}",
                        positiveBefore, positiveAfter);
                check(Math.abs(positiveAfter.engine()) < 0.001 && near(positiveAfter.position(), anchor)
                                && near(positiveAfter.velocity(), Vec3.ZERO),
                        "positive control did not execute the reset");

                player = new FakePlayer(level, new GameProfile(UUID.randomUUID(), "WWResetProbe"));
                check(player.startRiding(aircraft), "player must enter normally without force=true");
                check(aircraft.getControllingPassenger() == player && pilot.isPassengerOfSameVehicle(aircraft),
                        "player must control while benchmark ArmorStand remains aboard");
                seedPhase(test);
                Snapshot before = seedInputs(aircraft, anchor);
                WWDebugBenchmarkMod.LOGGER.info("benchmark_reset_probe player={} passengers={} phase={} before={}",
                        player.getUUID(), aircraft.getPassengers().stream().map(Entity::getUUID).toList(),
                        field(test, "phase"), before);
                BenchmarkManager.tick(server);
                check(sessions.get(server) == session,
                        "inconclusive: session ended, possibly because benchmark caught an exception");
                check(aircraft.getControllingPassenger() == player && pilot.isPassengerOfSameVehicle(aircraft),
                        "player control and benchmark pilot must remain present through the tick");
                Snapshot after = snapshot(aircraft);
                WWDebugBenchmarkMod.LOGGER.info("benchmark_reset_probe player_after={} phase={}",
                        after, field(test, "phase"));
                check(before.sameAs(after),
                        "benchmark phase reset must not change player-controlled engine, inputs, position or velocity");
            }
        } catch (Throwable throwable) {
            failure = throwable;
            throw throwable;
        } finally {
            // Run every cleanup step even if dismount, abort or observation fails. A constructor
            // failure can leave chunks without an accessible owner; never guess and unforce them.
            final FakePlayer ownedPlayer = player;
            final Object ownedSession = session;
            final Entity knownAircraft = aircraft;
            final ArmorStand ownedPilot = knownPilot;
            final UUID ownedMarker = markerId;
            final Object ownedMarkerControl = markerControl;
            final boolean ownedMarkerHeartbeat = markerHeartbeatInstalled;
            final Throwable testFailure = failure;
            AtomicReference<Set<Long>> forcedAfter = new AtomicReference<>();
            AtomicBoolean abortedOwnSession = new AtomicBoolean();
            BenchmarkProbeCleanup cleanup = new BenchmarkProbeCleanup();
            cleanup.run("dismount", () -> {
                if (ownedPlayer == null) return;
                if (mode == BenchmarkProbeMode.DIRECT && ownedPlayer.isPassenger()) {
                    check(knownAircraft != null && knownAircraft.level() == level
                                    && ownedPlayer.level() == level && ownedPlayer.getVehicle() == knownAircraft,
                            "fixture player moved elsewhere; refusing to dismount");
                }
                ownedPlayer.stopRiding();
            });
            cleanup.run("abort_own_session", () -> {
                if (ownedSession == null) return;
                Object current = sessions.get(server);
                if (current != null && current != ownedSession) {
                    throw new IllegalStateException("session ownership changed; refusing to stop another session");
                }
                if (mode == BenchmarkProbeMode.DIRECT) {
                    check(knownAircraft != null && knownAircraft.level() == level,
                            "fixture aircraft is unknown or changed world; preserving session");
                    check(ownedPilot != null && ownedPilot.level() == level && (!ownedPilot.isPassenger()
                                    || ownedPilot.getVehicle() == knownAircraft),
                            "fixture pilot ownership is unknown; preserving session");
                    check(knownAircraft.getSelfAndPassengers()
                                    .filter(passenger -> passenger != knownAircraft)
                                    .noneMatch(passenger -> passenger instanceof net.minecraft.world.entity.player.Player
                                            || passenger != ownedPilot),
                            "unexpected passenger aboard fixture aircraft; preserving session");
                }
                Method abort = ownedSession.getClass().getDeclaredMethod("abort");
                abort.setAccessible(true);
                abort.invoke(ownedSession);
                sessions.remove(server, ownedSession);
                abortedOwnSession.set(true);
            });
            if (mode == BenchmarkProbeMode.DIRECT) {
                cleanup.run("discard_preserved_fixture_entities", () -> {
                    if (knownAircraft == null || knownAircraft.isRemoved()) return;
                    check(abortedOwnSession.get() && sessions.get(server) == null,
                            "session ownership is unknown; preserving fixture aircraft");
                    check(knownAircraft.getSelfAndPassengers().filter(passenger -> passenger != knownAircraft)
                                    .noneMatch(passenger -> passenger instanceof net.minecraft.world.entity.player.Player
                                            || passenger != ownedPilot),
                            "unexpected passenger aboard preserved fixture aircraft");
                    if (ownedPilot != null && !ownedPilot.isRemoved()) {
                        check(!ownedPilot.isPassenger() || ownedPilot.getVehicle() == knownAircraft,
                                "fixture pilot moved to a different vehicle");
                        ownedPilot.stopRiding();
                        ownedPilot.discard();
                    }
                    knownAircraft.discard();
                });
                cleanup.run("remove_owned_marker", () -> {
                    if (ownedMarker == null) return;
                    check(abortedOwnSession.get() && sessions.get(server) == null,
                            "session ownership is unknown; preserving marker");
                    AtomicBoolean removed = new AtomicBoolean();
                    controls.computeIfPresent(ownedMarker, (key, current) -> {
                        if (current != ownedMarkerControl) return current;
                        removed.set(true);
                        return null;
                    });
                    check(removed.get(), "marker control ownership is unknown; refusing removal");
                    if (ownedMarkerHeartbeat) heartbeats.remove(ownedMarker);
                });
            }
            cleanup.run("benchmark_state", () -> check(
                    sessions.isEmpty() && controls.isEmpty() && heartbeats.isEmpty(),
                    "benchmark state was not restored"));
            cleanup.run("forced_chunk_snapshot", () -> forcedAfter.set(Set.copyOf(level.getForcedChunks())));
            cleanup.run("forced_chunk_comparison", () -> {
                if (forcedAfter.get() != null) {
                    check(forcedAfter.get().equals(forcedBefore),
                            "forced chunks differ after cleanup; preserve world for investigation");
                }
            });
            cleanup.run("aircraft_removed", () -> {
                if (knownAircraft != null) check(knownAircraft.isRemoved(), "benchmark aircraft survived cleanup");
            });
            cleanup.run("cleanup_status_log", () -> WWDebugBenchmarkMod.LOGGER.info(
                    "benchmark_reset_probe cleanup forced_before={} forced_after={} sessions={} controls={} heartbeats={} session_known={} aircraft_known={} failure={}",
                    forcedBefore, forcedAfter.get() == null ? "unknown" : forcedAfter.get(),
                    sessions.size(), controls.size(), heartbeats.size(), ownedSession != null,
                    knownAircraft != null, testFailure == null ? "none" : testFailure.toString()));
            if (testFailure != null) {
                cleanup.run("test_failure_log", () -> WWDebugBenchmarkMod.LOGGER.error(
                        "benchmark_reset_probe test failed; preserve the world", testFailure));
            }
            for (BenchmarkProbeCleanup.Failure item : cleanup.failures()) {
                cleanup.run("cleanup_failure_log_" + item.step(), () -> WWDebugBenchmarkMod.LOGGER.error(
                        "benchmark_reset_probe cleanup step={} failed; preserve the world", item.step(), item.error()));
            }
            Throwable result = cleanup.combine(testFailure);
            if (testFailure == null && result != null) {
                throw new IllegalStateException("benchmark reset probe cleanup failed; preserve the world", result);
            }
        }
        helper.succeed();
    }

    private static Object candidate(ServerLevel level) throws Exception {
        Method discover = BenchmarkManager.class.getDeclaredMethod("discover", ServerLevel.class,
                BenchmarkCategory.class, boolean.class);
        discover.setAccessible(true);
        List<?> found = (List<?>) discover.invoke(null, level, BenchmarkCategory.ALL, true);
        for (Object candidate : found) {
            if (AIRCRAFT.equals(field(candidate, "id"))) return candidate;
        }
        throw new IllegalStateException("fixed D4Y candidate was not discovered");
    }

    @SuppressWarnings({"unchecked", "rawtypes"})
    private static void seedPhase(Object test) throws Exception {
        Class<? extends Enum> phaseClass = (Class<? extends Enum>)
                Class.forName(BenchmarkManager.class.getName() + "$Phase");
        setField(test, "phase", Enum.valueOf(phaseClass, "STRAIGHT_ACCELERATION"));
        setField(test, "phaseTick", 599);
    }

    private static Snapshot seedInputs(Entity aircraft, Vec3 anchor) throws Exception {
        aircraft.setPos(anchor.x + 1.0, anchor.y + 3.0, anchor.z + 1.0);
        aircraft.setDeltaMovement(new Vec3(0.11, 0.07, 0.13));
        ReflectiveAircraft.applyControl(aircraft, 0.31f, -0.42f, 0.53f, 0.24f);
        Snapshot result = snapshot(aircraft);
        check(Math.abs(result.x() - 0.31) < 0.001 && Math.abs(result.y() + 0.42) < 0.001
                        && Math.abs(result.z() - 0.53) < 0.001 && Math.abs(result.engine() - 0.24) < 0.001
                        && !near(result.position(), anchor) && !near(result.velocity(), Vec3.ZERO),
                "input, engine, position and velocity sentinels must read back");
        return result;
    }

    private record Snapshot(double x, double y, double z, double engine, Vec3 position, Vec3 velocity) {
        boolean hasControls(double expectedX, double expectedY, double expectedZ, double expectedEngine) {
            return Math.abs(x - expectedX) < 0.001 && Math.abs(y - expectedY) < 0.001
                    && Math.abs(z - expectedZ) < 0.001 && Math.abs(engine - expectedEngine) < 0.001;
        }
        boolean sameControls(Snapshot other) { return hasControls(other.x, other.y, other.z, other.engine); }
        boolean sameAs(Snapshot other) {
            return Math.abs(x - other.x) < 0.001 && Math.abs(y - other.y) < 0.001
                    && Math.abs(z - other.z) < 0.001 && Math.abs(engine - other.engine) < 0.001
                    && near(position, other.position) && near(velocity, other.velocity);
        }
    }

    private static Snapshot snapshot(Entity aircraft) throws Exception {
        return new Snapshot(((Number) field(aircraft, "movementX")).doubleValue(),
                ((Number) field(aircraft, "movementY")).doubleValue(),
                ((Number) field(aircraft, "movementZ")).doubleValue(),
                ReflectiveAircraft.engineTarget(aircraft), aircraft.position(), aircraft.getDeltaMovement());
    }

    private static boolean near(Vec3 a, Vec3 b) { return a.distanceToSqr(b) < 1.0e-8; }

    private static Field findField(Class<?> type, String name) throws NoSuchFieldException {
        for (Class<?> current = type; current != null; current = current.getSuperclass()) {
            try {
                Field field = current.getDeclaredField(name);
                field.setAccessible(true);
                return field;
            } catch (NoSuchFieldException ignored) { }
        }
        throw new NoSuchFieldException(type.getName() + "." + name);
    }

    private static Object field(Object instance, String name) throws Exception {
        return findField(instance.getClass(), name).get(instance);
    }

    private static void setField(Object instance, String name, Object value) throws Exception {
        findField(instance.getClass(), name).set(instance, value);
    }

    private static Object staticField(Class<?> type, String name) throws Exception {
        return findField(type, name).get(null);
    }

    @SuppressWarnings("unchecked")
    private static Set<UUID> benchmarkHeartbeats() throws Exception {
        return (Set<UUID>) staticField(BenchmarkManager.class, "CONTROL_HEARTBEATS");
    }

    @SuppressWarnings("unchecked")
    private static Map<Object, Object> map(Class<?> type, String name) throws Exception {
        return (Map<Object, Object>) staticField(type, name);
    }

    private static void check(boolean condition, String message) {
        if (!condition) throw new IllegalStateException(message);
    }
}
