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

/** Direct synchronous call only, not a ServerStoppingEvent. Disposable world and JVM mandatory. */
@GameTestHolder("wwdebug_benchmark_silent_stop_probe")
@PrefixGameTestTemplate(false)
public final class BenchmarkPlayerSilentStopGameTests {
    private static final String NS = "wwdebug_benchmark_silent_stop_probe";
    private static final ResourceLocation AIRCRAFT = new ResourceLocation("warfare_wings", "d4y");
    private BenchmarkPlayerSilentStopGameTests() { }

    @GameTest(template = "empty", timeoutTicks = 40, batch = "benchmark_player_silent_stop_probe_only")
    public static void benchmarkSilentStopRespectsPlayer(GameTestHelper helper) throws Exception {
        ServerLevel level = helper.getLevel();
        MinecraftServer server = level.getServer();
        check(server instanceof GameTestServer, "inconclusive: requires GameTestServer");
        check("fresh-disposable-world-single-jvm".equals(System.getProperty("wwdebug.benchmarkSilentStopProbe")),
                "inconclusive: requires externally verified fresh disposable world and dedicated JVM");
        check(NS.equals(System.getProperty("forge.enabledGameTestNamespaces")), "inconclusive: wrong namespace");
        check("enabled".equals(System.getProperty("wwdebug.benchmarkSilentStopLatchProbe")),
                "inconclusive: dedicated latch probe opt-in missing");
        var selected = GameTestRegistry.getAllTestFunctions().stream().map(f ->
                new BenchmarkSilentStopProbePolicy.TestId(f.getTestName(), f.getBatchName(), f.getStructureName())).toList();
        WWDebugBenchmarkMod.LOGGER.info("benchmark_silent_stop_probe selected_test_count={} tests={}", selected.size(), selected);
        check(BenchmarkSilentStopProbePolicy.isExpected(selected), "inconclusive: test registration differs");
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
        WWDebugBenchmarkMod.LOGGER.info("benchmark_silent_stop_probe world={} structure={} expected={} actual={}",
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
                if (!"inconclusive: refusing silent stop on non-owned session".equals(expected.getMessage())) throw expected;
                refused = true;
            }
            check(refused && sessions.get(server) == positive.session && !positive.aircraft.isRemoved()
                            && !positive.pilot.isRemoved() && positive.aircraft.getControllingPassenger() == positive.pilot
                            && controls.containsKey(positive.aircraft.getUUID()),
                    "inconclusive: foreign identity refusal changed the active session");
            WWDebugBenchmarkMod.LOGGER.info("benchmark_silent_stop_probe foreign_identity_refused");
            stopOwned(positive, source, sessions);
            WWDebugBenchmarkMod.LOGGER.info("benchmark_silent_stop_probe positive returned=true aircraft_removed={} pilot_removed={}",
                    positive.aircraft.isRemoved(), positive.pilot.isRemoved());
            check(positive.aircraft.isRemoved() && positive.pilot.isRemoved(),
                    "inconclusive: positive stop did not remove its test entities");
            check(sessions.isEmpty() && controls.isEmpty() && heartbeats.isEmpty(), "inconclusive: positive state remains");
            check(Set.copyOf(level.getForcedChunks()).equals(forcedBefore), "inconclusive: positive forced chunks changed");
            WWDebugBenchmarkMod.LOGGER.info("benchmark_silent_stop_probe positive_pass");

            create(playerCase, candidate, source, sessions);
            verifyLease(playerCase, level, sessions);
            check(!positive.aircraft.getUUID().equals(playerCase.aircraft.getUUID()), "inconclusive: duplicate aircraft identity");
            check(ReflectiveAircraft.passengerSpace(playerCase.aircraft) >= 2, "inconclusive: D4Y needs two seats");
            check(playerCase.aircraft.getControllingPassenger() == playerCase.pilot, "inconclusive: player-case pilot not controlling");
            check(controls.containsKey(playerCase.aircraft.getUUID()), "inconclusive: player-case control missing");
            check(!hasPlayerPassenger(playerCase.aircraft), "inconclusive: unexpected player");
            // As in #145 v3, prepare fuel and tick only before any player is mounted.
            double fuelBefore = ReflectiveAircraft.fuelUtilization(playerCase.aircraft);
            check(Double.isFinite(fuelBefore), "inconclusive: pre-tick fuel not finite");
            playerCase.aircraft.tick();
            double fuelAfter = ReflectiveAircraft.fuelUtilization(playerCase.aircraft);
            WWDebugBenchmarkMod.LOGGER.info("benchmark_silent_stop_probe fuel_before_tick={} fuel_after_tick={}", fuelBefore, fuelAfter);
            check(Double.isFinite(fuelAfter) && fuelAfter > 0, "inconclusive: fuel unavailable after native tick");
            verifyLease(playerCase, level, sessions);
            check(!playerCase.aircraft.isRemoved() && !playerCase.pilot.isRemoved()
                            && controls.containsKey(playerCase.aircraft.getUUID())
                            && playerCase.aircraft.getControllingPassenger() == playerCase.pilot
                            && !hasPlayerPassenger(playerCase.aircraft), "inconclusive: native tick changed fixture preconditions");
            // Establish an actual stale heartbeat before mounting.
            BenchmarkManager.applyControl(playerCase.aircraft);
            UUID aircraftId = playerCase.aircraft.getUUID();
            check(controls.containsKey(aircraftId) && heartbeats.contains(aircraftId),
                    "inconclusive: controls and heartbeat must both exist before mounting");
            Object aircraftTest = playerCase.test;
            check(!((Boolean) field(aircraftTest, "surrenderedToPlayer")), "inconclusive: latch was already set");
            // Seed before mounting: the test never injects control into a player-piloted aircraft.
            Vec3 initialPosition = playerCase.aircraft.position();
            playerCase.aircraft.setPos(initialPosition.x + 1.0, initialPosition.y + 3.0, initialPosition.z + 1.0);
            playerCase.aircraft.setDeltaMovement(new Vec3(0.11, 0.07, 0.13));
            ReflectiveAircraft.applyControl(playerCase.aircraft, 0.31f, -0.42f, 0.53f, 0.24f);
            Snapshot sentinel = snapshot(playerCase.aircraft);
            Vec3 expectedPosition = initialPosition.add(1.0, 3.0, 1.0);
            Vec3 expectedVelocity = new Vec3(0.11, 0.07, 0.13);
            WWDebugBenchmarkMod.LOGGER.info(
                    "benchmark_silent_stop_probe sentinel actual={} expected_x={} expected_y={} expected_z={} expected_engine={} expected_position={} expected_velocity={} delta_x={} delta_y={} delta_z={} delta_engine={} delta_position={} delta_velocity={}",
                    sentinel, 0.31, -0.42, 0.53, 0.24, expectedPosition, expectedVelocity,
                    sentinel.x() - 0.31, sentinel.y() + 0.42, sentinel.z() - 0.53, sentinel.engine() - 0.24,
                    sentinel.position().subtract(expectedPosition), sentinel.velocity().subtract(expectedVelocity));
            check(Math.abs(sentinel.x() - 0.31) < 0.001 && Math.abs(sentinel.y() + 0.42) < 0.001
                            && Math.abs(sentinel.z() - 0.53) < 0.001 && Math.abs(sentinel.engine() - 0.24) < 0.001
                            && sentinel.position().distanceToSqr(initialPosition.add(1.0, 3.0, 1.0)) < 1.0e-8
                            && sentinel.velocity().distanceToSqr(new Vec3(0.11, 0.07, 0.13)) < 1.0e-8,
                    "inconclusive: nonzero sentinels did not read back");
            player = new FakePlayer(level, new GameProfile(UUID.randomUUID(), "WWStopProbe"));
            playerCase.wasPlayerOccupied = true;
            check(player.startRiding(playerCase.aircraft), "inconclusive: normal player mounting failed");
            check(playerCase.aircraft.getControllingPassenger() == player && playerCase.pilot.isPassengerOfSameVehicle(playerCase.aircraft),
                    "inconclusive: player control and ArmorStand must both be present");
            Snapshot before = snapshot(playerCase.aircraft);
            check(sentinel.equals(before), "inconclusive: mounting changed sentinels");
            WWDebugBenchmarkMod.LOGGER.info("benchmark_silent_stop_probe player_before aircraft={} player={} pilot={} passengers={} snapshot={}",
                    playerCase.aircraft.getUUID(), player.getUUID(), playerCase.pilot.getUUID(),
                    playerCase.aircraft.getPassengers().stream().map(Entity::getUUID).toList(), before);
            Set<Long> forcedPlayerBefore = Set.copyOf(level.getForcedChunks());
            check(controls.containsKey(aircraftId) && heartbeats.contains(aircraftId),
                    "inconclusive: stale controls or heartbeat missing before latch tick");
            verifyLease(playerCase, level, sessions);
            List<?> activeBeforeTick = (List<?>) field(playerCase.session, "active");
            check(activeBeforeTick.size() == 1 && activeBeforeTick.get(0) == aircraftTest
                            && field(aircraftTest, "aircraft") == playerCase.aircraft && field(aircraftTest, "pilot") == playerCase.pilot
                            && !((Boolean) field(aircraftTest, "surrenderedToPlayer")),
                    "inconclusive: session/test/aircraft identity or initial latch changed");
            int elapsedBefore = ((Number) field(playerCase.session, "elapsedTicks")).intValue();
            check(elapsedBefore >= 0 && elapsedBefore < Integer.MAX_VALUE, "inconclusive: invalid elapsed tick");
            Object phaseBefore = field(aircraftTest, "phase");
            int phaseTickBefore = ((Number) field(aircraftTest, "phaseTick")).intValue();
            WWDebugBenchmarkMod.LOGGER.info("benchmark_silent_stop_latch_probe before_tick aircraft={} elapsed={} phase={} phase_tick={} forced={} controls=true heartbeat=true",
                    aircraftId, elapsedBefore, phaseBefore, phaseTickBefore, forcedPlayerBefore.stream().sorted().toList());
            BenchmarkManager.tick(server);
            WWDebugBenchmarkMod.LOGGER.info("benchmark_silent_stop_latch_probe tick_returned same_session={} aircraft_removed={} player_removed={} pilot_removed={} player_vehicle={} controlling={} controls={} heartbeat={}",
                    sessions.get(server) == playerCase.session, playerCase.aircraft.isRemoved(), player.isRemoved(), playerCase.pilot.isRemoved(),
                    player.getVehicle(), playerCase.aircraft.getControllingPassenger(), controls.containsKey(aircraftId), heartbeats.contains(aircraftId));
            check(!playerCase.aircraft.isRemoved() && !player.isRemoved() && !playerCase.pilot.isRemoved()
                            && player.getVehicle() == playerCase.aircraft && playerCase.aircraft.getControllingPassenger() == player
                            && playerCase.pilot.isPassengerOfSameVehicle(playerCase.aircraft),
                    "unsafe: latch tick changed aircraft or passenger survival/control");
            verifyLease(playerCase, level, sessions);
            List<?> activeAfterTick = (List<?>) field(playerCase.session, "active");
            check(activeAfterTick.size() == 1 && activeAfterTick.get(0) == aircraftTest
                            && field(aircraftTest, "aircraft") == playerCase.aircraft && field(aircraftTest, "pilot") == playerCase.pilot,
                    "inconclusive: session/test/entity identity changed after latch tick");
            check(((Number) field(playerCase.session, "elapsedTicks")).intValue() == elapsedBefore + 1,
                    "inconclusive: benchmark tick did not advance exactly once");
            check(((Boolean) field(aircraftTest, "surrenderedToPlayer")), "inconclusive: latch not set");
            check(!controls.containsKey(aircraftId) && !heartbeats.contains(aircraftId),
                    "unsafe: target controls or heartbeat survived latch tick");
            check(field(aircraftTest, "phase") == phaseBefore
                            && ((Number) field(aircraftTest, "phaseTick")).intValue() == phaseTickBefore
                            && before.equals(snapshot(playerCase.aircraft))
                            && forcedPlayerBefore.equals(Set.copyOf(level.getForcedChunks())),
                    "unsafe: latch tick changed phase, inputs, movement or forced set");
            WWDebugBenchmarkMod.LOGGER.info("benchmark_silent_stop_latch_probe latch_verified aircraft={} session_same=true test_same=true surrendered=true controls=false heartbeat=false snapshot={} forced={}",
                    aircraftId, before, forcedPlayerBefore.stream().sorted().toList());
            verifyLease(playerCase, level, sessions);
            check(playerCase.aircraft.getControllingPassenger() == player && !controls.containsKey(aircraftId) && !heartbeats.contains(aircraftId),
                    "inconclusive: player or latch state changed before direct call");
            stopOwned(playerCase, source, sessions);
            WWDebugBenchmarkMod.LOGGER.info("benchmark_silent_stop_probe player_direct_returned");
            WWDebugBenchmarkMod.LOGGER.info("benchmark_silent_stop_probe player_basic aircraft_removed={} player_removed={} pilot_removed={} player_vehicle={} controlling={} session_same={} session_absent={} controls_present={} heartbeat={}",
                    playerCase.aircraft.isRemoved(), player.isRemoved(), playerCase.pilot.isRemoved(), player.getVehicle(),
                    playerCase.aircraft.getControllingPassenger(), sessions.get(server) == playerCase.session, sessions.get(server) == null,
                    controls.containsKey(playerCase.aircraft.getUUID()), heartbeats.contains(playerCase.aircraft.getUUID()));
            Snapshot after = null;
            Set<Long> forcedPlayerAfter = null;
            try { after = snapshot(playerCase.aircraft); }
            catch (Exception e) { WWDebugBenchmarkMod.LOGGER.warn("benchmark_silent_stop_probe snapshot_after=unknown", e); }
            try { forcedPlayerAfter = Set.copyOf(level.getForcedChunks()); }
            catch (Exception e) { WWDebugBenchmarkMod.LOGGER.warn("benchmark_silent_stop_probe forced_after=unknown", e); }
            WWDebugBenchmarkMod.LOGGER.info("benchmark_silent_stop_probe player_details snapshot={} forced={}",
                    after == null ? "unknown" : after,
                    forcedPlayerAfter == null ? "unknown" : forcedPlayerAfter.stream().sorted().toList());
            check(!playerCase.aircraft.isRemoved() && !player.isRemoved() && player.getVehicle() == playerCase.aircraft
                    && playerCase.aircraft.getControllingPassenger() == player,
                    "unsafe: stop removed the player aircraft or detached its controlling player");
            check(level.getEntity(playerCase.aircraft.getUUID()) == playerCase.aircraft,
                    "inconclusive: surviving aircraft is not visible by UUID");
            check(after != null && forcedPlayerAfter != null, "inconclusive: post-call snapshot or forced state unknown");
            check(before.equals(after), "unsafe: silent stop changed player aircraft controls or motion");
            check(sessions.get(server) == null, "inconclusive: retained session requires continuity verification");
            check(!controls.containsKey(playerCase.aircraft.getUUID()) && !heartbeats.contains(playerCase.aircraft.getUUID()),
                    "inconclusive: target controls or heartbeat remain");
            WWDebugBenchmarkMod.LOGGER.info("benchmark_silent_stop_probe player_pass");
        } catch (Throwable t) {
            failure = t;
            throw t;
        } finally {
            FakePlayer ownedPlayer = player;
            Throwable original = failure;
            AtomicReference<Set<Long>> forcedAfter = new AtomicReference<>();
            BenchmarkProbeCleanup cleanup = new BenchmarkProbeCleanup();
            cleanup.run("dismount_own_fake_player", () -> {
                if (ownedPlayer == null || ownedPlayer.getVehicle() == null) return;
                check(playerCase.world != null && ownedPlayer.level() == playerCase.world
                                && playerCase.aircraft.level() == playerCase.world && ownedPlayer.getVehicle() == playerCase.aircraft,
                        "player vehicle or world changed; preserve world");
                ownedPlayer.stopRiding();
            });
            cleanup.run("abort_owned_player_session", () -> abortOwned(playerCase, server, sessions));
            cleanup.run("abort_owned_positive_session", () -> abortOwned(positive, server, sessions));
            cleanup.run("state_check", () -> check(sessions.isEmpty() && controls.isEmpty() && heartbeats.isEmpty(),
                    "benchmark state remains; preserve world"));
            cleanup.run("forced_snapshot", () -> forcedAfter.set(Set.copyOf(level.getForcedChunks())));
            cleanup.run("forced_compare", () -> check(forcedAfter.get() != null && forcedBefore.equals(forcedAfter.get()),
                    "forced chunk state unknown or differs; preserve world"));
            cleanup.run("status_log", () -> WWDebugBenchmarkMod.LOGGER.info(
                    "benchmark_silent_stop_probe cleanup forced_before={} forced_after={} sessions={} controls={} heartbeats={} failure={}",
                    forcedBefore, forcedAfter.get() == null ? "unknown" : forcedAfter.get(), sessions.size(), controls.size(),
                    heartbeats.size(), original == null ? "none" : original.toString()));
            if (original != null) cleanup.run("failure_log", () -> WWDebugBenchmarkMod.LOGGER.error(
                    "benchmark_silent_stop_probe failed; preserve world", original));
            for (BenchmarkProbeCleanup.Failure item : List.copyOf(cleanup.failures())) {
                cleanup.run("cleanup_failure_log", () -> WWDebugBenchmarkMod.LOGGER.error(
                        "benchmark_silent_stop_probe cleanup step={} failed; preserve world", item.step(), item.error()));
            }
            Throwable combined = cleanup.combine(original);
            if (original == null && combined != null) throw new IllegalStateException("cleanup failed; preserve world", combined);
        }
        helper.succeed();
    }

    private static final class Lease {
        Object session;
        Object test;
        Entity aircraft;
        ArmorStand pilot;
        boolean registered;
        boolean wasPlayerOccupied;
        ServerLevel world;
    }
    private static void create(Lease lease, Object candidate, CommandSourceStack source, Map<Object, Object> sessions) throws Exception {
        check(sessions.isEmpty(), "inconclusive: another session appeared before construction");
        Class<?> cls = Class.forName(BenchmarkManager.class.getName() + "$BenchmarkSession");
        Constructor<?> ctor = cls.getDeclaredConstructor(CommandSourceStack.class, BenchmarkCategory.class, boolean.class, List.class);
        ctor.setAccessible(true);
        // Constructor can fail after partial spawn or force; unknown ownership must not be guessed.
        lease.world = source.getLevel();
        lease.session = ctor.newInstance(source, BenchmarkCategory.ALL, true, List.of(candidate));
        check(sessions.putIfAbsent(source.getServer(), lease.session) == null, "inconclusive: concurrent session; preserve world");
        lease.registered = true;
        List<?> active = (List<?>) field(lease.session, "active");
        check(active.size() == 1, "inconclusive: expected one spawned test");
        lease.test = active.get(0);
        lease.aircraft = (Entity) field(lease.test, "aircraft");
        lease.pilot = (ArmorStand) field(lease.test, "pilot");
    }
    private static void verifyLease(Lease lease, ServerLevel level, Map<Object, Object> sessions) {
        check(BenchmarkSilentStopProbePolicy.mayStop(lease.session, sessions.get(level.getServer())), "inconclusive: session ownership changed");
        check(lease.aircraft != null && lease.pilot != null &&
                lease.aircraft.getType() == net.minecraft.core.registries.BuiltInRegistries.ENTITY_TYPE.get(AIRCRAFT), "inconclusive: wrong aircraft");
        check(level.getEntity(lease.aircraft.getUUID()) == lease.aircraft && level.getEntity(lease.pilot.getUUID()) == lease.pilot,
                "inconclusive: aircraft or pilot not visible by UUID");
        check(lease.pilot.isPassengerOfSameVehicle(lease.aircraft), "inconclusive: pilot not mounted");
    }
    private static void stopOwned(Lease lease, CommandSourceStack source, Map<Object, Object> sessions) {
        check(BenchmarkSilentStopProbePolicy.mayStop(lease.session, sessions.get(source.getServer())),
                "inconclusive: refusing silent stop on non-owned session");
        BenchmarkManager.stopSilently(source.getServer());
    }
    private static void abortOwned(Lease lease, MinecraftServer server, Map<Object, Object> sessions) throws Exception {
        if (!lease.registered) return;
        Object current = sessions.get(server);
        check(current == null || current == lease.session, "session ownership changed; refusing cleanup");
        if (current == null) return;
        check(!lease.wasPlayerOccupied, "player-occupied session retained; refusing cleanup and preserving world");
        if (lease.aircraft != null) {
            check(lease.world != null && lease.aircraft.level() == lease.world && lease.pilot != null
                            && lease.pilot.level() == lease.world
                            && !lease.pilot.isRemoved() && lease.pilot.getVehicle() == lease.aircraft
                            && lease.pilot.getPassengers().isEmpty(),
                    "pilot ownership changed; refusing cleanup");
            check(!hasPlayerPassenger(lease.aircraft), "player still aboard; refusing cleanup");
            check(lease.aircraft.getPassengers().stream().allMatch(p -> p == lease.pilot),
                    "unexpected occupant; refusing cleanup");
        }
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
