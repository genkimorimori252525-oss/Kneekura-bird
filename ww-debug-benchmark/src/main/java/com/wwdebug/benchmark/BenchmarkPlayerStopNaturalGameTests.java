package com.wwdebug.benchmark;

import com.mojang.authlib.GameProfile;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.core.BlockPos;
import net.minecraft.gametest.framework.*;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.decoration.ArmorStand;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.phys.Vec3;
import net.minecraftforge.common.MinecraftForge;
import net.minecraftforge.common.util.FakePlayer;
import net.minecraftforge.event.TickEvent;
import net.minecraftforge.event.server.ServerStoppingEvent;
import net.minecraftforge.eventbus.api.EventPriority;
import net.minecraftforge.eventbus.api.SubscribeEvent;
import net.minecraftforge.gametest.GameTestHolder;
import net.minecraftforge.gametest.PrefixGameTestTemplate;

import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.Collection;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;

/** Explicitly selected, externally isolated, disposable-world GameTest only. */
@GameTestHolder("wwdebug_benchmark_stop_natural_probe")
@PrefixGameTestTemplate(false)
public final class BenchmarkPlayerStopNaturalGameTests {
    private static final String NS = "wwdebug_benchmark_stop_natural_probe";
    private static final ResourceLocation AIRCRAFT = new ResourceLocation("warfare_wings", "d4y");
    private BenchmarkPlayerStopNaturalGameTests() { }

    @GameTest(template = "empty", timeoutTicks = 80, batch = "benchmark_player_stop_natural_probe_only")
    public static void benchmarkStopNaturalRespectsPlayer(GameTestHelper helper) throws Exception {
        ServerLevel level = helper.getLevel();
        MinecraftServer server = level.getServer();
        check(server instanceof GameTestServer, "inconclusive: not a GameTestServer");
        check("fresh-disposable-world-single-jvm".equals(System.getProperty("wwdebug.benchmarkStopNaturalProbe")),
                "inconclusive: requires independent disposable world and dedicated JVM attestation");
        check(NS.equals(System.getProperty("forge.enabledGameTestNamespaces")), "inconclusive: wrong namespace");
        var selected = GameTestRegistry.getAllTestFunctions().stream().map(f ->
                new BenchmarkNaturalTickRegistration.TestId(f.getTestName(), f.getBatchName(), f.getStructureName())).toList();
        WWDebugBenchmarkMod.LOGGER.info("benchmark_stop_natural_probe selected_test_count={} tests={}", selected.size(), selected);
        check(BenchmarkNaturalTickRegistration.isExpected(selected), "inconclusive: wrong registered test set");
        Map<Object, Object> sessions = map("SESSIONS"), controls = map("CONTROLS");
        Set<?> heartbeats = (Set<?>) staticField(BenchmarkManager.class, "CONTROL_HEARTBEATS");
        check(sessions.isEmpty() && controls.isEmpty() && heartbeats.isEmpty(), "inconclusive: benchmark state not empty");
        Set<Long> baseline = Set.copyOf(level.getForcedChunks());
        ChunkPos center = new ChunkPos(helper.absolutePos(BlockPos.ZERO));
        Set<BenchmarkProbeForcedChunks.Chunk> chunks = baseline.stream().map(p -> {
            ChunkPos c = new ChunkPos(p); return new BenchmarkProbeForcedChunks.Chunk(c.x, c.z);
        }).collect(Collectors.toUnmodifiableSet());
        WWDebugBenchmarkMod.LOGGER.info("benchmark_stop_natural_probe baseline={} structure_center=({}, {})", baseline, center.x, center.z);
        check(BenchmarkProbeForcedChunks.matches(center.x, center.z, chunks), "inconclusive: wrong forced footprint");
        // This reflection is fixed-version infrastructure; establish it before spawning any entities.
        GameTestInfo info = (GameTestInfo) findField(GameTestHelper.class, "testInfo").get(helper);
        Context context = new Context(helper, info, level, sessions, controls, heartbeats, baseline);
        try {
            info.addListener(context);
            // Registration can fail partway; even an incomplete attempt needs an unregister attempt.
            context.registered = true;
            MinecraftForge.EVENT_BUS.register(context);
            context.setup();
        } catch (Throwable failure) {
            context.finish(failure);
            if (failure instanceof Error error) throw error;
        }
    }

    private static final class Lease {
        Object session;
        Object test;
        Entity aircraft;
        ArmorStand pilot;
        boolean registered;
        boolean released;
    }
    public static final class Context implements GameTestListener {
        final GameTestHelper helper;
        final GameTestInfo info;
        final ServerLevel level;
        final MinecraftServer server;
        final Map<Object, Object> sessions, controls;
        final Set<?> heartbeats;
        final Set<Long> baseline;
        final Lease positive = new Lease(), target = new Lease();
        FakePlayer player;
        Set<Long> forcedActive;
        PhaseSnapshot expectedPhase;
        Sample pre;
        BenchmarkNaturalTickPolicy progress = new BenchmarkNaturalTickPolicy();
        int ordinal, startTick;
        boolean occupied = true, ready, closed, registered;

        Context(GameTestHelper helper, GameTestInfo info, ServerLevel level, Map<Object, Object> sessions,
                Map<Object, Object> controls, Set<?> heartbeats, Set<Long> baseline) {
            this.helper = helper; this.info = info; this.level = level; this.server = level.getServer();
            this.sessions = sessions; this.controls = controls; this.heartbeats = heartbeats; this.baseline = baseline;
        }
        void setup() throws Exception {
            Object candidate = candidate(level);
            CommandSourceStack source = server.createCommandSourceStack().withLevel(level).withPosition(new Vec3(0, 80, 0));
            create(positive, candidate, source, sessions);
            verify(positive, level, sessions);
            check(!hasPlayer(positive.aircraft) && positive.aircraft.getControllingPassenger() == positive.pilot
                            && controls.containsKey(positive.aircraft.getUUID()),
                    "inconclusive: positive pilot/occupancy/controls");
            check(stopOwned(positive, source, sessions) == 1, "inconclusive: positive stop failed");
            check(positive.aircraft.isRemoved() && positive.pilot.isRemoved() && sessions.isEmpty()
                            && controls.isEmpty() && heartbeats.isEmpty() && baseline.equals(Set.copyOf(level.getForcedChunks())),
                    "inconclusive: positive stop cleanup failed");
            positive.released = true;
            WWDebugBenchmarkMod.LOGGER.info("benchmark_stop_natural_probe positive_pass");
            create(target, candidate, source, sessions);
            verify(target, level, sessions);
            check(!target.aircraft.getUUID().equals(positive.aircraft.getUUID()) && !hasPlayer(target.aircraft)
                            && target.aircraft.getControllingPassenger() == target.pilot
                            && ReflectiveAircraft.passengerSpace(target.aircraft) >= 2,
                    "inconclusive: target identity/occupancy");
            double fuelBefore = ReflectiveAircraft.fuelUtilization(target.aircraft);
            check(Double.isFinite(fuelBefore), "inconclusive: pre-tick fuel unknown");
            target.aircraft.tick();
            double fuelAfter = ReflectiveAircraft.fuelUtilization(target.aircraft);
            WWDebugBenchmarkMod.LOGGER.info("benchmark_stop_natural_probe fuel_before={} fuel_after={}", fuelBefore, fuelAfter);
            check(Double.isFinite(fuelAfter) && fuelAfter > 0, "inconclusive: no fuel after setup tick");
            verify(target, level, sessions);
            check(!hasPlayer(target.aircraft) && target.aircraft.getControllingPassenger() == target.pilot,
                    "inconclusive: setup tick changed pilot/occupancy");
            BenchmarkManager.applyControl(target.aircraft);
            UUID id = target.aircraft.getUUID();
            check(controls.containsKey(id) && heartbeats.contains(id), "inconclusive: stale controls/heartbeat absent");
            seedEnd(target.test);
            expectedPhase = phase(target.test);
            check(expectedPhase.equals(new PhaseSnapshot("STRAIGHT_ACCELERATION", 599)), "inconclusive: phase baseline");
            Vec3 pos = target.aircraft.position();
            target.aircraft.setPos(pos.x + 1, pos.y + 3, pos.z + 1);
            target.aircraft.setDeltaMovement(new Vec3(.11, .07, .13));
            ReflectiveAircraft.applyControl(target.aircraft, .31f, -.42f, .53f, .24f);
            Snapshot seeded = snapshot(target.aircraft);
            WWDebugBenchmarkMod.LOGGER.info("benchmark_stop_natural_probe sentinel={} expected_position={}", seeded, pos.add(1, 3, 1));
            check(Math.abs(seeded.x - .31) < .001 && Math.abs(seeded.y + .42) < .001 && Math.abs(seeded.z - .53) < .001
                            && Math.abs(seeded.engine - .24) < .001 && seeded.position.distanceToSqr(pos.add(1, 3, 1)) < 1e-8
                            && seeded.velocity.distanceToSqr(new Vec3(.11, .07, .13)) < 1e-8,
                    "inconclusive: sentinel not established");
            player = new FakePlayer(level, new GameProfile(UUID.randomUUID(), "WWNaturalProbe"));
            check(player.startRiding(target.aircraft), "inconclusive: normal mounting failed");
            check(target.aircraft.getControllingPassenger() == player && target.pilot.isPassengerOfSameVehicle(target.aircraft)
                            && seeded.equals(snapshot(target.aircraft)), "inconclusive: mounting changed state");
            forcedActive = Set.copyOf(level.getForcedChunks());
            WWDebugBenchmarkMod.LOGGER.info("benchmark_stop_natural_probe pre_stop_phase={} snapshot={} forced={}",
                    expectedPhase, seeded, forcedActive);
            int result = stopOwned(target, source, sessions);
            WWDebugBenchmarkMod.LOGGER.info("benchmark_stop_natural_probe stop_result={} same_session={} aircraft_removed={} player_vehicle={}",
                    result, sessions.get(server) == target.session, target.aircraft.isRemoved(), player.getVehicle());
            check(result == 0, "unsafe: occupied stop was not refused");
            checkState();
            check(seeded.equals(snapshot(target.aircraft)), "unsafe: occupied stop changed state");
            startTick = server.getTickCount();
            ready = true;
            WWDebugBenchmarkMod.LOGGER.info("benchmark_stop_natural_probe stop_refusal_pass start_tick={}", startTick);
        }
        @SubscribeEvent(priority = EventPriority.HIGHEST)
        public void onPre(TickEvent.ServerTickEvent event) {
            if (closed || !ready || event.phase != TickEvent.Phase.END || event.getServer() != server) return;
            try {
                check(server.getTickCount() - startTick <= 30, "inconclusive: natural-tick watchdog");
                check(pre == null, "inconclusive: unmatched END pre sample");
                logStructure("pre");
                checkState();
                pre = sample();
                logBoundary("pre", pre);
            } catch (Throwable failure) { failEvent(failure); }
        }
        @SubscribeEvent(priority = EventPriority.LOWEST)
        public void onPost(TickEvent.ServerTickEvent event) {
            if (closed || !ready || event.phase != TickEvent.Phase.END || event.getServer() != server) return;
            try {
                check(pre != null, "inconclusive: END post without pre");
                logStructure("post");
                checkState();
                Sample post = sample();
                logBoundary("post", post);
                check(pre.values.equals(post.values), "unsafe: observed values changed inside END event");
                check(progress.accept(pre.clock, post.clock), "inconclusive: END samples or ticks did not progress as required");
                pre = null;
                ordinal++;
                if (!progress.complete()) return;
                if (occupied) {
                    WWDebugBenchmarkMod.LOGGER.info("benchmark_stop_natural_probe occupied_natural_pass");
                    Snapshot beforeDismount = snapshot(target.aircraft);
                    player.stopRiding();
                    occupied = false;
                    checkState();
                    check(beforeDismount.equals(snapshot(target.aircraft)), "unsafe: dismount changed aircraft values");
                    WWDebugBenchmarkMod.LOGGER.info("benchmark_stop_natural_probe dismount_pass");
                    progress = new BenchmarkNaturalTickPolicy();
                    ordinal = 0;
                } else {
                    WWDebugBenchmarkMod.LOGGER.info("benchmark_stop_natural_probe dismounted_natural_pass");
                    finish(null);
                }
            } catch (Throwable failure) { failEvent(failure); }
        }
        @SubscribeEvent(priority = EventPriority.HIGHEST)
        public void onStopping(ServerStoppingEvent event) {
            if (!closed && event.getServer() == server) finish(new IllegalStateException("inconclusive: server stopping"));
        }
        private void logStructure(String boundary) {
            UUID id = target.aircraft == null ? null : target.aircraft.getUUID();
            WWDebugBenchmarkMod.LOGGER.info("benchmark_stop_natural_probe structure={} stage={} server_tick={} game_time={} same_session={} aircraft_removed={} pilot_removed={} player_removed={} player_vehicle={} pilot_vehicle={} controls={} heartbeat={}",
                    boundary, occupied ? "occupied" : "dismounted", server.getTickCount(), level.getGameTime(),
                    target.session != null && sessions.get(server) == target.session,
                    target.aircraft == null ? "unknown" : target.aircraft.isRemoved(),
                    target.pilot == null ? "unknown" : target.pilot.isRemoved(), player == null ? "unknown" : player.isRemoved(),
                    player == null ? "unknown" : player.getVehicle(), target.pilot == null ? "unknown" : target.pilot.getVehicle(),
                    id == null ? "unknown" : controls.containsKey(id), id == null ? "unknown" : heartbeats.contains(id));
        }
        private void checkState() throws Exception {
            verify(target, level, sessions);
            UUID id = target.aircraft.getUUID();
            check(player != null && !player.isRemoved() && !target.aircraft.isRemoved() && !target.pilot.isRemoved(),
                    "unsafe: player or aircraft removed");
            check(occupied ? player.getVehicle() == target.aircraft && target.aircraft.getControllingPassenger() == player
                            : player.getVehicle() == null && target.aircraft.getControllingPassenger() == target.pilot,
                    "unsafe: passenger/control state changed");
            check(!controls.containsKey(id) && !heartbeats.contains(id), "unsafe: controls or heartbeat active");
            check(((Collection<?>) field(target.session, "pending")).isEmpty(), "inconclusive: unexpected pending aircraft");
            check(expectedPhase.equals(phase(target.test)) && Boolean.TRUE.equals(field(target.test, "surrenderedToPlayer")),
                    "unsafe: phase advanced or surrender lost");
            check(forcedActive.equals(Set.copyOf(level.getForcedChunks())), "unsafe: forced set changed");
            check(target.aircraft.canUpdate(), "inconclusive: aircraft cannot update");
        }
        private void logBoundary(String boundary, Sample value) throws Exception {
            UUID id = target.aircraft.getUUID();
            WWDebugBenchmarkMod.LOGGER.info("benchmark_stop_natural_probe boundary={} stage={} sample={} gametest_tick={} phase={} surrendered={} aircraft={} pilot={} player={} controls={} heartbeat={} forced={}",
                    boundary, occupied ? "occupied" : "dismounted", value, field(info, "tickCount"), phase(target.test),
                    field(target.test, "surrenderedToPlayer"), id, target.pilot.getUUID(), player.getUUID(),
                    controls.containsKey(id), heartbeats.contains(id), Set.copyOf(level.getForcedChunks()));
        }
        private Sample sample() throws Exception {
            Snapshot value = snapshot(target.aircraft);
            check(BenchmarkNaturalTickPolicy.finiteValues(value.x, value.y, value.z, value.engine,
                            value.position.x, value.position.y, value.position.z,
                            value.velocity.x, value.velocity.y, value.velocity.z),
                    "inconclusive: nonfinite state sample");
            return new Sample(new BenchmarkNaturalTickPolicy.Sample(ordinal, server.getTickCount(), level.getGameTime(),
                    target.aircraft.tickCount, ((Number) field(target.session, "elapsedTicks")).longValue()), value);
        }
        private void failEvent(Throwable failure) {
            finish(failure);
            if (failure instanceof Error error) throw error;
        }
        @Override public void testStructureLoaded(GameTestInfo ignored) { }
        @Override public void testPassed(GameTestInfo ignored) { if (!closed) finish(new IllegalStateException("inconclusive: unexpected external pass")); }
        @Override public void testFailed(GameTestInfo ignored) { if (!closed) finish(new IllegalStateException("inconclusive: GameTest failed or timed out")); }
        void finish(Throwable failure) {
            if (closed) return;
            closed = true;
            BenchmarkProbeCleanup cleanup = new BenchmarkProbeCleanup();
            cleanup.run("dismount_own_fake_player", () -> {
                if (player == null || player.getVehicle() == null) return;
                check(target.aircraft != null && player.getVehicle() == target.aircraft && player.level() == level,
                        "unknown player vehicle; preserve world");
                player.stopRiding();
                check(player.getVehicle() == null, "player did not dismount; preserve world");
            });
            cleanup.run("abort_target", () -> abortOwned(target));
            cleanup.run("abort_positive", () -> abortOwned(positive));
            cleanup.run("state_check", () -> check(sessions.isEmpty() && controls.isEmpty() && heartbeats.isEmpty(),
                    "benchmark state remains; preserve world"));
            cleanup.run("forced_check", () -> check(baseline.equals(Set.copyOf(level.getForcedChunks())),
                    "forced set differs or unknown; preserve world"));
            cleanup.run("unregister", () -> { if (registered) MinecraftForge.EVENT_BUS.unregister(this); });
            Throwable result = cleanup.combine(failure);
            WWDebugBenchmarkMod.LOGGER.info("benchmark_stop_natural_probe cleanup failure={} cleanup_errors={}",
                    result == null ? "none" : result.toString(), cleanup.failures().size());
            for (BenchmarkProbeCleanup.Failure item : cleanup.failures()) WWDebugBenchmarkMod.LOGGER.error(
                    "benchmark_stop_natural_probe cleanup step={} failed; preserve world", item.step(), item.error());
            if (result != null) WWDebugBenchmarkMod.LOGGER.error(
                    "benchmark_stop_natural_probe failed; preserve world", result);
            // END callbacks run outside GameTestInfo.tick. Schedule completion inside its next
            // tick so normal GameTest listeners can observe it; missing callback is inconclusive.
            if (!info.isDone()) {
                try {
                    helper.runAfterDelay(1, () -> {
                        if (info.isDone()) return;
                        if (result == null) {
                            WWDebugBenchmarkMod.LOGGER.info("benchmark_stop_natural_probe complete_pass");
                            helper.succeed();
                        } else {
                            info.fail(result);
                        }
                    });
                    WWDebugBenchmarkMod.LOGGER.info("benchmark_stop_natural_probe completion_scheduled");
                } catch (Throwable schedulingFailure) {
                    WWDebugBenchmarkMod.LOGGER.error("benchmark_stop_natural_probe completion scheduling failed; preserve world", schedulingFailure);
                    info.fail(schedulingFailure);
                }
            }
        }
        private void abortOwned(Lease lease) throws Exception {
            if (!lease.registered || lease.released) return;
            check(sessions.get(server) == lease.session, "session owner unknown; refusing abort");
            check(lease.aircraft != null && lease.test != null && lease.pilot != null, "entity identity unknown; refusing abort");
            List<?> active = (List<?>) field(lease.session, "active");
            Collection<?> pending = (Collection<?>) field(lease.session, "pending");
            check(active.size() == 1 && active.get(0) == lease.test && pending.isEmpty()
                            && field(lease.test, "aircraft") == lease.aircraft && field(lease.test, "pilot") == lease.pilot,
                    "session contents unknown; refusing abort");
            check(!hasPlayer(lease.aircraft), "player still aboard; refusing abort");
            Method abort = lease.session.getClass().getDeclaredMethod("abort");
            abort.setAccessible(true); abort.invoke(lease.session);
            sessions.remove(server, lease.session);
        }
    }
    private record PhaseSnapshot(String phase, int tick) { }
    private record Snapshot(double x, double y, double z, double engine, Vec3 position, Vec3 velocity) { }
    private record Sample(BenchmarkNaturalTickPolicy.Sample clock, Snapshot values) { }
    private static PhaseSnapshot phase(Object test) throws Exception {
        return new PhaseSnapshot(field(test, "phase").toString(), ((Number) field(test, "phaseTick")).intValue());
    }
    private static Snapshot snapshot(Entity e) throws Exception {
        return new Snapshot(((Number) field(e, "movementX")).doubleValue(), ((Number) field(e, "movementY")).doubleValue(),
                ((Number) field(e, "movementZ")).doubleValue(), ReflectiveAircraft.engineTarget(e), e.position(), e.getDeltaMovement());
    }
    @SuppressWarnings({"unchecked", "rawtypes"}) private static void seedEnd(Object test) throws Exception {
        Class<? extends Enum> c = (Class<? extends Enum>) Class.forName(BenchmarkManager.class.getName() + "$Phase");
        findField(test.getClass(), "phase").set(test, Enum.valueOf(c, "STRAIGHT_ACCELERATION"));
        findField(test.getClass(), "phaseTick").set(test, 599);
    }
    private static boolean hasPlayer(Entity entity) {
        for (Entity p : entity.getPassengers()) if (p instanceof Player || hasPlayer(p)) return true;
        return false;
    }
    private static void create(Lease lease, Object candidate, CommandSourceStack source, Map<Object, Object> sessions) throws Exception {
        check(sessions.isEmpty(), "inconclusive: session appeared before construction");
        Class<?> cls = Class.forName(BenchmarkManager.class.getName() + "$BenchmarkSession");
        Constructor<?> ctor = cls.getDeclaredConstructor(CommandSourceStack.class, BenchmarkCategory.class, boolean.class, List.class);
        ctor.setAccessible(true);
        // Partial constructor effects are not recoverable by guessing an owner.
        lease.session = ctor.newInstance(source, BenchmarkCategory.ALL, true, List.of(candidate));
        check(sessions.putIfAbsent(source.getServer(), lease.session) == null, "inconclusive: concurrent session");
        lease.registered = true;
        List<?> active = (List<?>) field(lease.session, "active");
        check(active.size() == 1, "inconclusive: expected one active aircraft");
        lease.test = active.get(0);
        lease.aircraft = (Entity) field(lease.test, "aircraft");
        lease.pilot = (ArmorStand) field(lease.test, "pilot");
    }
    private static void verify(Lease lease, ServerLevel level, Map<Object, Object> sessions) throws Exception {
        check(lease.session != null && sessions.get(level.getServer()) == lease.session && lease.aircraft != null && lease.pilot != null,
                "inconclusive: session/aircraft owner unknown");
        List<?> active = (List<?>) field(lease.session, "active");
        check(active.size() == 1 && active.get(0) == lease.test && field(lease.test, "aircraft") == lease.aircraft
                        && field(lease.test, "pilot") == lease.pilot && level.getEntity(lease.aircraft.getUUID()) == lease.aircraft
                        && level.getEntity(lease.pilot.getUUID()) == lease.pilot
                        && lease.aircraft.getType() == net.minecraft.core.registries.BuiltInRegistries.ENTITY_TYPE.get(AIRCRAFT)
                        && lease.pilot.isPassengerOfSameVehicle(lease.aircraft), "inconclusive: aircraft/test identity changed");
    }
    private static int stopOwned(Lease lease, CommandSourceStack source, Map<Object, Object> sessions) {
        check(lease.session != null && sessions.get(source.getServer()) == lease.session, "inconclusive: refusing non-owned stop");
        return BenchmarkManager.stop(source);
    }
    private static Object candidate(ServerLevel level) throws Exception {
        Method m = BenchmarkManager.class.getDeclaredMethod("discover", ServerLevel.class, BenchmarkCategory.class, boolean.class);
        m.setAccessible(true);
        for (Object c : (List<?>) m.invoke(null, level, BenchmarkCategory.ALL, true)) if (AIRCRAFT.equals(field(c, "id"))) return c;
        throw new IllegalStateException("inconclusive: D4Y candidate absent");
    }
    private static Field findField(Class<?> type, String name) throws NoSuchFieldException {
        for (Class<?> c = type; c != null; c = c.getSuperclass()) {
            try { Field f = c.getDeclaredField(name); f.setAccessible(true); return f; } catch (NoSuchFieldException ignored) { }
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
