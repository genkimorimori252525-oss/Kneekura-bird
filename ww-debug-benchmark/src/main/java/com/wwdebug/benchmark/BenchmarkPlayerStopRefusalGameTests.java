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
import net.minecraft.world.entity.decoration.ArmorStand;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.storage.LevelResource;
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
import java.util.stream.Collectors;

/** Destructive probe: a separately verified disposable world and dedicated JVM are mandatory. */
@GameTestHolder("wwdebug_benchmark_stop_refusal_probe")
@PrefixGameTestTemplate(false)
public final class BenchmarkPlayerStopRefusalGameTests {
    private static final String NS = "wwdebug_benchmark_stop_refusal_probe";
    private static final ResourceLocation AIRCRAFT = new ResourceLocation("warfare_wings", "d4y");
    private BenchmarkPlayerStopRefusalGameTests() { }

    @GameTest(template = "empty", timeoutTicks = 40, batch = "benchmark_player_stop_refusal_probe_only")
    public static void benchmarkStopRefusalSuspendsPlayer(GameTestHelper helper) throws Exception {
        ServerLevel level = helper.getLevel();
        MinecraftServer server = level.getServer();
        check(server instanceof GameTestServer, "inconclusive: requires GameTestServer");
        check("fresh-disposable-world-single-jvm".equals(System.getProperty("wwdebug.benchmarkStopRefusalProbe")),
                "inconclusive: requires externally verified fresh disposable world and dedicated JVM");
        check(NS.equals(System.getProperty("forge.enabledGameTestNamespaces")), "inconclusive: wrong namespace");
        var selected = GameTestRegistry.getAllTestFunctions().stream().map(f ->
                new BenchmarkStopRefusalProbePolicy.TestId(f.getTestName(), f.getBatchName(), f.getStructureName())).toList();
        WWDebugBenchmarkMod.LOGGER.info("benchmark_stop_refusal_probe selected_test_count={} tests={}", selected.size(), selected);
        check(BenchmarkStopRefusalProbePolicy.isExpected(selected), "inconclusive: test registration differs");
        Map<Object, Object> sessions = map("SESSIONS"), controls = map("CONTROLS");
        Set<?> heartbeats = (Set<?>) staticField(BenchmarkManager.class, "CONTROL_HEARTBEATS");
        check(sessions.isEmpty() && controls.isEmpty() && heartbeats.isEmpty(), "inconclusive: benchmark state not empty");
        Set<Long> forcedBefore = Set.copyOf(level.getForcedChunks());
        BlockPos structurePos = helper.absolutePos(BlockPos.ZERO);
        ChunkPos center = new ChunkPos(structurePos);
        Set<BenchmarkProbeForcedChunks.Chunk> chunks = forcedBefore.stream().map(p -> {
            ChunkPos c = new ChunkPos(p);
            return new BenchmarkProbeForcedChunks.Chunk(c.x, c.z);
        }).collect(Collectors.toUnmodifiableSet());
        WWDebugBenchmarkMod.LOGGER.info("benchmark_stop_refusal_probe world={} structure={} expected={} actual={}",
                server.getWorldPath(LevelResource.ROOT), structurePos,
                BenchmarkProbeForcedChunks.expected(center.x, center.z).stream().sorted().toList(),
                chunks.stream().sorted().toList());
        check(BenchmarkProbeForcedChunks.matches(center.x, center.z, chunks), "inconclusive: unexpected forced chunks");
        CommandSourceStack source = server.createCommandSourceStack().withLevel(level).withPosition(new Vec3(0, 80, 0));
        Lease positive = new Lease(), playerCase = new Lease();
        FakePlayer player = null;
        Throwable failure = null;
        try {
            Object candidate = candidate(level);
            create(positive, candidate, source, sessions);
            verifyLease(positive, level, sessions);
            check(positive.aircraft.getControllingPassenger() == positive.pilot, "inconclusive: positive pilot not controlling");
            check(controls.containsKey(positive.aircraft.getUUID()), "inconclusive: positive control missing");
            check(!hasPlayerPassenger(positive.aircraft), "inconclusive: unexpected player");
            // Exercise refusal against a distinct identity while a real owned session exists.
            Lease foreignIdentity = new Lease();
            foreignIdentity.session = new Object();
            boolean refused = false;
            try {
                stopOwned(foreignIdentity, source, sessions);
            } catch (IllegalStateException expected) {
                if (!"inconclusive: refusing public stop on non-owned session".equals(expected.getMessage())) throw expected;
                refused = true;
            }
            check(refused && sessions.get(server) == positive.session && !positive.aircraft.isRemoved()
                            && !positive.pilot.isRemoved() && positive.aircraft.getControllingPassenger() == positive.pilot
                            && controls.containsKey(positive.aircraft.getUUID()),
                    "inconclusive: foreign identity refusal changed the active session");
            WWDebugBenchmarkMod.LOGGER.info("benchmark_stop_refusal_probe foreign_identity_refused");
            int positiveResult = stopOwned(positive, source, sessions);
            WWDebugBenchmarkMod.LOGGER.info("benchmark_stop_refusal_probe positive result={} aircraft_removed={} pilot_removed={}",
                    positiveResult, positive.aircraft.isRemoved(), positive.pilot.isRemoved());
            check(positiveResult == 1 && positive.aircraft.isRemoved() && positive.pilot.isRemoved(),
                    "inconclusive: positive stop did not remove its test entities");
            check(sessions.isEmpty() && controls.isEmpty() && heartbeats.isEmpty(), "inconclusive: positive state remains");
            check(Set.copyOf(level.getForcedChunks()).equals(forcedBefore), "inconclusive: positive forced chunks changed");
            WWDebugBenchmarkMod.LOGGER.info("benchmark_stop_refusal_probe positive_pass");

            create(playerCase, candidate, source, sessions);
            verifyLease(playerCase, level, sessions);
            check(!positive.aircraft.getUUID().equals(playerCase.aircraft.getUUID()), "inconclusive: duplicate aircraft identity");
            check(ReflectiveAircraft.passengerSpace(playerCase.aircraft) >= 2, "inconclusive: D4Y needs two seats");
            check(playerCase.aircraft.getControllingPassenger() == playerCase.pilot, "inconclusive: player-case pilot not controlling");
            check(controls.containsKey(playerCase.aircraft.getUUID()), "inconclusive: player-case control missing");
            check(!hasPlayerPassenger(playerCase.aircraft), "inconclusive: unexpected player");
            // Like the reset probe, prepare fuel before seeding. The utilization getter may
            // update synchronized entity data, so these observations are player-free only.
            double fuelBefore = ReflectiveAircraft.fuelUtilization(playerCase.aircraft);
            WWDebugBenchmarkMod.LOGGER.info("benchmark_stop_refusal_probe fuel_before_tick={}", fuelBefore);
            check(Double.isFinite(fuelBefore), "inconclusive: pre-tick fuel value is not finite");
            playerCase.aircraft.tick();
            double fuelAfter = ReflectiveAircraft.fuelUtilization(playerCase.aircraft);
            WWDebugBenchmarkMod.LOGGER.info("benchmark_stop_refusal_probe fuel_after_tick={}", fuelAfter);
            check(Double.isFinite(fuelAfter) && fuelAfter > 0.0,
                    "inconclusive: aircraft fuel not available after native tick");
            verifyLease(playerCase, level, sessions);
            check(sessions.get(server) == playerCase.session && !playerCase.aircraft.isRemoved()
                            && !playerCase.pilot.isRemoved() && controls.containsKey(playerCase.aircraft.getUUID())
                            && playerCase.aircraft.getControllingPassenger() == playerCase.pilot
                            && !hasPlayerPassenger(playerCase.aircraft),
                    "inconclusive: native tick changed session, aircraft, or pilot state");
            // Seed a real stale heartbeat before mounting, while the ArmorStand controls the plane.
            BenchmarkManager.applyControl(playerCase.aircraft);
            UUID aircraftId = playerCase.aircraft.getUUID();
            check(controls.containsKey(aircraftId) && heartbeats.contains(aircraftId),
                    "inconclusive: benchmark controls and heartbeat must exist before takeover");
            List<?> active = (List<?>) field(playerCase.session, "active");
            check(active.size() == 1, "inconclusive: active test disappeared");
            Object aircraftTest = active.get(0);
            seedEnd(aircraftTest);
            PhaseSnapshot preStopPhase = phaseSnapshot(aircraftTest);
            check(preStopPhase.phase().equals("STRAIGHT_ACCELERATION") && preStopPhase.tick() == 599,
                    "inconclusive: END phase baseline not established");
            // Seed before mounting: the test never injects control into a player-piloted aircraft.
            Vec3 initialPosition = playerCase.aircraft.position();
            playerCase.aircraft.setPos(initialPosition.x + 1.0, initialPosition.y + 3.0, initialPosition.z + 1.0);
            playerCase.aircraft.setDeltaMovement(new Vec3(0.11, 0.07, 0.13));
            ReflectiveAircraft.applyControl(playerCase.aircraft, 0.31f, -0.42f, 0.53f, 0.24f);
            Snapshot sentinel = snapshot(playerCase.aircraft);
            Vec3 expectedPosition = initialPosition.add(1.0, 3.0, 1.0);
            Vec3 expectedVelocity = new Vec3(0.11, 0.07, 0.13);
            WWDebugBenchmarkMod.LOGGER.info(
                    "benchmark_stop_refusal_probe sentinel actual={} expected_x={} expected_y={} expected_z={} expected_engine={} expected_position={} expected_velocity={} delta_x={} delta_y={} delta_z={} delta_engine={} delta_position={} delta_velocity={}",
                    sentinel, 0.31, -0.42, 0.53, 0.24, expectedPosition, expectedVelocity,
                    sentinel.x() - 0.31, sentinel.y() + 0.42, sentinel.z() - 0.53, sentinel.engine() - 0.24,
                    sentinel.position().subtract(expectedPosition), sentinel.velocity().subtract(expectedVelocity));
            check(Math.abs(sentinel.x() - 0.31) < 0.001 && Math.abs(sentinel.y() + 0.42) < 0.001
                            && Math.abs(sentinel.z() - 0.53) < 0.001 && Math.abs(sentinel.engine() - 0.24) < 0.001
                            && sentinel.position().distanceToSqr(initialPosition.add(1.0, 3.0, 1.0)) < 1.0e-8
                            && sentinel.velocity().distanceToSqr(new Vec3(0.11, 0.07, 0.13)) < 1.0e-8,
                    "inconclusive: nonzero sentinels did not read back");
            player = new FakePlayer(level, new GameProfile(UUID.randomUUID(), "WWRefusalProbe"));
            check(player.startRiding(playerCase.aircraft), "inconclusive: normal player mounting failed");
            check(playerCase.aircraft.getControllingPassenger() == player && playerCase.pilot.isPassengerOfSameVehicle(playerCase.aircraft),
                    "inconclusive: player control and ArmorStand must both be present");
            Snapshot before = snapshot(playerCase.aircraft);
            check(sentinel.equals(before), "inconclusive: mounting changed sentinels");
            WWDebugBenchmarkMod.LOGGER.info("benchmark_stop_refusal_probe player_before aircraft={} player={} pilot={} passengers={} snapshot={}",
                    playerCase.aircraft.getUUID(), player.getUUID(), playerCase.pilot.getUUID(),
                    playerCase.aircraft.getPassengers().stream().map(Entity::getUUID).toList(), before);
            Set<Long> forcedActive = Set.copyOf(level.getForcedChunks());
            WWDebugBenchmarkMod.LOGGER.info("benchmark_stop_refusal_probe pre_stop_phase={} forced_active={} controls={} heartbeat={}",
                    preStopPhase, forcedActive, controls.containsKey(aircraftId), heartbeats.contains(aircraftId));
            check(controls.containsKey(aircraftId) && heartbeats.contains(aircraftId),
                    "inconclusive: stale controls and heartbeat not present before stop");
            int result = stopOwned(playerCase, source, sessions);
            WWDebugBenchmarkMod.LOGGER.info("benchmark_stop_refusal_probe stop_result={} aircraft_removed={} player_removed={} player_vehicle={} controlling={} same_session={}",
                    result, playerCase.aircraft.isRemoved(), player.isRemoved(), player.getVehicle(),
                    playerCase.aircraft.getControllingPassenger(), sessions.get(server) == playerCase.session);
            check(result == 0, "unsafe: stop must refuse the occupied session");
            checkRetained(playerCase, player, level, sessions, controls, heartbeats, forcedActive, before, aircraftTest,
                    preStopPhase, true, "stop_refused");
            WWDebugBenchmarkMod.LOGGER.info("benchmark_stop_refusal_probe stop_refusal_pass");
            // Record the original phase BEFORE the very first END tick; never reseed it afterwards.
            WWDebugBenchmarkMod.LOGGER.info("benchmark_stop_refusal_probe pre_first_sync_tick_phase={}", phaseSnapshot(aircraftTest));
            check(preStopPhase.equals(phaseSnapshot(aircraftTest)), "unsafe: phase advanced before first END");
            for (int i = 1; i <= 2; i++) {
                BenchmarkManager.tick(server);
                checkRetained(playerCase, player, level, sessions, controls, heartbeats, forcedActive, before,
                        aircraftTest, preStopPhase, true, "occupied_sync_tick_" + i);
                WWDebugBenchmarkMod.LOGGER.info("benchmark_stop_refusal_probe occupied_sync_tick_pass step={}", i);
            }
            player.stopRiding();
            check(player.getVehicle() == null, "inconclusive: FakePlayer could not dismount");
            checkRetained(playerCase, player, level, sessions, controls, heartbeats, forcedActive, before,
                    aircraftTest, preStopPhase, false, "after_dismount");
            WWDebugBenchmarkMod.LOGGER.info("benchmark_stop_refusal_probe dismount_pass");
            for (int i = 1; i <= 2; i++) {
                BenchmarkManager.tick(server);
                checkRetained(playerCase, player, level, sessions, controls, heartbeats, forcedActive, before,
                        aircraftTest, preStopPhase, false, "dismounted_sync_tick_" + i);
                WWDebugBenchmarkMod.LOGGER.info("benchmark_stop_refusal_probe dismounted_sync_tick_pass step={}", i);
            }
            WWDebugBenchmarkMod.LOGGER.info("benchmark_stop_refusal_probe player_pass");
        } catch (Throwable t) {
            failure = t;
            throw t;
        } finally {
            FakePlayer ownedPlayer = player;
            Throwable original = failure;
            AtomicReference<Set<Long>> forcedAfter = new AtomicReference<>();
            BenchmarkProbeCleanup cleanup = new BenchmarkProbeCleanup();
            cleanup.run("dismount_own_fake_player", () -> { if (ownedPlayer != null) ownedPlayer.stopRiding(); });
            cleanup.run("abort_owned_player_session", () -> abortOwned(playerCase, server, sessions));
            cleanup.run("abort_owned_positive_session", () -> abortOwned(positive, server, sessions));
            cleanup.run("state_check", () -> check(sessions.isEmpty() && controls.isEmpty() && heartbeats.isEmpty(),
                    "benchmark state remains; preserve world"));
            cleanup.run("forced_snapshot", () -> forcedAfter.set(Set.copyOf(level.getForcedChunks())));
            cleanup.run("forced_compare", () -> check(forcedAfter.get() != null && forcedBefore.equals(forcedAfter.get()),
                    "forced chunk state unknown or differs; preserve world"));
            cleanup.run("status_log", () -> WWDebugBenchmarkMod.LOGGER.info(
                    "benchmark_stop_refusal_probe cleanup forced_before={} forced_after={} sessions={} controls={} heartbeats={} failure={}",
                    forcedBefore, forcedAfter.get() == null ? "unknown" : forcedAfter.get(), sessions.size(), controls.size(),
                    heartbeats.size(), original == null ? "none" : original.toString()));
            if (original != null) cleanup.run("failure_log", () -> WWDebugBenchmarkMod.LOGGER.error(
                    "benchmark_stop_refusal_probe failed; preserve world", original));
            for (BenchmarkProbeCleanup.Failure item : cleanup.failures()) {
                WWDebugBenchmarkMod.LOGGER.error("benchmark_stop_refusal_probe cleanup step={} failed; preserve world", item.step(), item.error());
            }
            Throwable combined = cleanup.combine(original);
            if (original == null && combined != null) throw new IllegalStateException("cleanup failed; preserve world", combined);
        }
        helper.succeed();
    }

    private static final class Lease {
        Object session;
        Entity aircraft;
        ArmorStand pilot;
        boolean registered;
    }
    private static void create(Lease lease, Object candidate, CommandSourceStack source, Map<Object, Object> sessions) throws Exception {
        check(sessions.isEmpty(), "inconclusive: another session appeared before construction");
        Class<?> cls = Class.forName(BenchmarkManager.class.getName() + "$BenchmarkSession");
        Constructor<?> ctor = cls.getDeclaredConstructor(CommandSourceStack.class, BenchmarkCategory.class, boolean.class, List.class);
        ctor.setAccessible(true);
        // Constructor can fail after partial spawn or force; unknown ownership must not be guessed.
        lease.session = ctor.newInstance(source, BenchmarkCategory.ALL, true, List.of(candidate));
        check(sessions.putIfAbsent(source.getServer(), lease.session) == null, "inconclusive: concurrent session; preserve world");
        lease.registered = true;
        List<?> active = (List<?>) field(lease.session, "active");
        check(active.size() == 1, "inconclusive: expected one spawned test");
        lease.aircraft = (Entity) field(active.get(0), "aircraft");
        lease.pilot = (ArmorStand) field(active.get(0), "pilot");
    }
    private static void verifyLease(Lease lease, ServerLevel level, Map<Object, Object> sessions) {
        check(BenchmarkStopRefusalProbePolicy.mayStop(lease.session, sessions.get(level.getServer())), "inconclusive: session ownership changed");
        check(lease.aircraft != null && lease.pilot != null &&
                lease.aircraft.getType() == net.minecraft.core.registries.BuiltInRegistries.ENTITY_TYPE.get(AIRCRAFT), "inconclusive: wrong aircraft");
        check(level.getEntity(lease.aircraft.getUUID()) == lease.aircraft && level.getEntity(lease.pilot.getUUID()) == lease.pilot,
                "inconclusive: aircraft or pilot not visible by UUID");
        check(lease.pilot.isPassengerOfSameVehicle(lease.aircraft), "inconclusive: pilot not mounted");
    }
    private static int stopOwned(Lease lease, CommandSourceStack source, Map<Object, Object> sessions) {
        check(BenchmarkStopRefusalProbePolicy.mayStop(lease.session, sessions.get(source.getServer())),
                "inconclusive: refusing public stop on non-owned session");
        return BenchmarkManager.stop(source);
    }
    private static void abortOwned(Lease lease, MinecraftServer server, Map<Object, Object> sessions) throws Exception {
        if (!lease.registered) return;
        Object current = sessions.get(server);
        check(current == null || current == lease.session, "session ownership changed; refusing cleanup");
        if (lease.aircraft != null) check(!hasPlayerPassenger(lease.aircraft),
                "player still aboard; refusing cleanup");
        else check(false, "aircraft unknown; refusing cleanup");
        Method abort = lease.session.getClass().getDeclaredMethod("abort");
        abort.setAccessible(true);
        abort.invoke(lease.session);
        sessions.remove(server, lease.session);
    }
    private static boolean hasPlayerPassenger(Entity entity) {
        for (Entity passenger : entity.getPassengers()) {
            if (passenger instanceof Player || hasPlayerPassenger(passenger)) return true;
        }
        return false;
    }
    @SuppressWarnings({"unchecked", "rawtypes"})
    private static void seedEnd(Object test) throws Exception {
        Class<? extends Enum> phase = (Class<? extends Enum>) Class.forName(BenchmarkManager.class.getName() + "$Phase");
        findField(test.getClass(), "phase").set(test, Enum.valueOf(phase, "STRAIGHT_ACCELERATION"));
        findField(test.getClass(), "phaseTick").set(test, 599);
    }
    private record PhaseSnapshot(String phase, int tick) { }
    private static PhaseSnapshot phaseSnapshot(Object test) throws Exception {
        return new PhaseSnapshot(field(test, "phase").toString(), ((Number) field(test, "phaseTick")).intValue());
    }
    private static void checkRetained(Lease lease, FakePlayer player, ServerLevel level,
                                      Map<Object, Object> sessions, Map<Object, Object> controls, Set<?> heartbeats,
                                      Set<Long> forcedActive, Snapshot before, Object test, PhaseSnapshot phase,
                                      boolean occupied, String stage) throws Exception {
        MinecraftServer server = level.getServer();
        UUID id = lease.aircraft.getUUID();
        WWDebugBenchmarkMod.LOGGER.info("benchmark_stop_refusal_probe stage={} same_session={} aircraft_removed={} pilot_removed={} player_removed={} player_vehicle={} pilot_vehicle={} control={} heartbeat={}",
                stage, sessions.get(server) == lease.session, lease.aircraft.isRemoved(), lease.pilot.isRemoved(),
                player.isRemoved(), player.getVehicle(), lease.pilot.getVehicle(), controls.containsKey(id), heartbeats.contains(id));
        check(sessions.get(server) == lease.session && !lease.aircraft.isRemoved() && !lease.pilot.isRemoved()
                        && !player.isRemoved() && level.getEntity(id) == lease.aircraft
                        && level.getEntity(lease.pilot.getUUID()) == lease.pilot
                        && lease.pilot.isPassengerOfSameVehicle(lease.aircraft),
                "unsafe: " + stage + " lost session, aircraft or pilot");
        check(occupied ? player.getVehicle() == lease.aircraft && lease.aircraft.getControllingPassenger() == player
                        : player.getVehicle() == null && lease.aircraft.getControllingPassenger() == lease.pilot,
                "unsafe: " + stage + " changed passenger control");
        List<?> active = (List<?>) field(lease.session, "active");
        check(active.size() == 1 && active.get(0) == test, "unsafe: " + stage + " changed active test identity");
        check(!controls.containsKey(id) && !heartbeats.contains(id), "unsafe: " + stage + " restored controls or heartbeat");
        Set<Long> observedForced = Set.copyOf(level.getForcedChunks());
        PhaseSnapshot observedPhase = phaseSnapshot(test);
        Snapshot observed = snapshot(lease.aircraft);
        WWDebugBenchmarkMod.LOGGER.info("benchmark_stop_refusal_probe stage_values={} phase={} snapshot={} forced={}",
                stage, observedPhase, observed, observedForced);
        check(forcedActive.equals(observedForced), "unsafe: " + stage + " changed forced chunks");
        check(phase.equals(observedPhase), "unsafe: " + stage + " advanced phase or phase tick");
        check(before.equals(observed), "unsafe: " + stage + " changed engine, inputs, position or velocity");
    }
    private static Object candidate(ServerLevel level) throws Exception {
        Method discover = BenchmarkManager.class.getDeclaredMethod("discover", ServerLevel.class, BenchmarkCategory.class, boolean.class);
        discover.setAccessible(true);
        for (Object c : (List<?>) discover.invoke(null, level, BenchmarkCategory.ALL, true)) if (AIRCRAFT.equals(field(c, "id"))) return c;
        throw new IllegalStateException("inconclusive: D4Y candidate absent");
    }
    private record Snapshot(double x, double y, double z, double engine, Vec3 position, Vec3 velocity) { }
    private static Snapshot snapshot(Entity e) throws Exception {
        return new Snapshot(((Number) field(e, "movementX")).doubleValue(), ((Number) field(e, "movementY")).doubleValue(),
                ((Number) field(e, "movementZ")).doubleValue(), ReflectiveAircraft.engineTarget(e), e.position(), e.getDeltaMovement());
    }
    private static Field findField(Class<?> type, String name) throws NoSuchFieldException {
        for (Class<?> c = type; c != null; c = c.getSuperclass()) {
            try { Field f = c.getDeclaredField(name); f.setAccessible(true); return f; }
            catch (NoSuchFieldException ignored) { }
        }
        throw new NoSuchFieldException(type.getName() + "." + name);
    }
    private static Object field(Object o, String n) throws Exception { return findField(o.getClass(), n).get(o); }
    private static Object staticField(Class<?> c, String n) throws Exception { return findField(c, n).get(null); }
    @SuppressWarnings("unchecked") private static Map<Object, Object> map(String name) throws Exception {
        return (Map<Object, Object>) staticField(BenchmarkManager.class, name);
    }
    private static void check(boolean ok, String message) { if (!ok) throw new IllegalStateException(message); }
}
