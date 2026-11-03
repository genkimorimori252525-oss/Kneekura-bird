package com.wwdebug.autopilot;

import com.mojang.authlib.GameProfile;
import com.wwdebug.benchmark.BenchmarkManager;
import com.wwdebug.benchmark.ReflectiveAircraft;
import com.wwdebug.benchmark.WWDebugBenchmarkMod;
import net.minecraft.core.BlockPos;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.gametest.framework.GameTest;
import net.minecraft.gametest.framework.GameTestHelper;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.entity.npc.Villager;
import net.minecraft.world.phys.Vec3;
import net.minecraftforge.common.util.FakePlayer;
import net.minecraftforge.gametest.GameTestHolder;
import net.minecraftforge.gametest.PrefixGameTestTemplate;

import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

/** Real-aircraft regression for the arbiter's player-takeover gate. */
@GameTestHolder(WWDebugBenchmarkMod.MOD_ID)
@PrefixGameTestTemplate(false)
public final class PlayerTakeoverControlGameTests {
    private PlayerTakeoverControlGameTests() {
    }

    @GameTest(template = "empty", timeoutTicks = 40, batch = "player_takeover_control")
    public static void playerTakeoverPreservesInputsAndClearsMobSession(GameTestHelper helper) {
        ServerLevel level = helper.getLevel();
        EntityType<?> type = BuiltInRegistries.ENTITY_TYPE
                .getOptional(new ResourceLocation("warfare_wings", "a6m"))
                .orElseThrow(() -> new IllegalStateException("fixed Warfare Wings A6M is required"));
        Entity aircraft = type.create(level);
        Villager mob = EntityType.VILLAGER.create(level);
        check(aircraft != null && mob != null, "could not create test entities");
        FakePlayer player = new FakePlayer(level, new GameProfile(UUID.randomUUID(), "WWTestPilot"));
        UUID aircraftId = aircraft.getUUID();
        Map<UUID, Object> controls = benchmarkControls();
        Set<UUID> heartbeats = benchmarkHeartbeats();
        boolean[] benchmarkInstalled = {false};
        try (SafetyFixtureLogIsolation.Cleanup cleanup = new SafetyFixtureLogIsolation.Cleanup()) {
            cleanup.add(() -> {
                if (benchmarkInstalled[0]) {
                    controls.remove(aircraftId);
                }
            });
            cleanup.add(() -> {
                if (benchmarkInstalled[0]) {
                    heartbeats.remove(aircraftId);
                }
            });
            cleanup.add(player::stopRiding);
            cleanup.add(() -> AutonomousFlightManager.forceStop(aircraftId, "player_takeover_test_cleanup"));
            cleanup.add(() -> FormationFlightManager.clear(aircraftId));
            cleanup.add(() -> removeAuthorityRecord(aircraftId));
            cleanup.add(mob::discard);
            cleanup.add(aircraft::discard);
            cleanup.add(() -> SafetyFixtureLogIsolation.isolate(level.getServer(), aircraftId));
            Vec3 origin = Vec3.atBottomCenterOf(helper.absolutePos(new BlockPos(1, 2, 1)));
            aircraft.moveTo(origin.x, origin.y, origin.z, 0.0f, 0.0f);
            mob.moveTo(origin.x, origin.y, origin.z, 0.0f, 0.0f);
            mob.setNoAi(true);
            check(level.addFreshEntity(aircraft) && level.addFreshEntity(mob),
                    "could not add test entities to the server");
            check(ReflectiveAircraft.isAirplane(aircraft) && ReflectiveAircraft.isControllable(aircraft),
                    "the primary entity must expose real aircraft controls");
            check(AutopilotProfileRegistry.resolve(level.getServer(), aircraft).isPresent(),
                    "the A6M measured profile must be staged");
            ReflectiveAircraft.fillFuel(aircraft);
            check(mob.startRiding(aircraft, true) && MobPilotGate.isMobPiloted(aircraft),
                    "the villager must initially hold the controls");
            aircraft.tick();
            check(ReflectiveAircraft.fuelUtilization(aircraft) > 0.0,
                    "the test aircraft must have usable fuel");
            check(AutonomousFlightManager.status(aircraftId).isPresent(),
                    "the mob must start an autonomous session before takeover");

            // A live legacy benchmark command makes bypassing the arbiter's player gate visible.
            // Verify that command actually reaches all four real inputs before the takeover.
            check(!heartbeats.contains(aircraftId), "fixture aircraft already has a benchmark heartbeat");
            Object previous = controls.putIfAbsent(aircraftId,
                    benchmarkInput(-0.72f, 0.63f, -0.54f, 0.82f));
            check(previous == null, "fixture aircraft already has benchmark control");
            benchmarkInstalled[0] = true;
            BenchmarkManager.applyControl(aircraft);
            checkInputs(aircraft, -0.72f, 0.63f, -0.54f, 0.82f,
                    "benchmark positive control must write the real aircraft inputs");
            check(heartbeats.remove(aircraftId), "benchmark positive control must emit a heartbeat");

            mob.stopRiding();
            player.moveTo(origin.x, origin.y, origin.z, 0.0f, 0.0f);
            check(player.startRiding(aircraft, true), "the fake player must mount the aircraft");
            check(aircraft.getControllingPassenger() == player && MobPilotGate.isPlayerControlled(aircraft),
                    "the fake player must hold the aircraft controls");
            check(AutonomousFlightManager.status(aircraftId).isPresent(),
                    "the stale mob session must still exist when takeover is tested");

            ReflectiveAircraft.applyControl(aircraft, 0.31f, -0.42f, 0.53f, 0.24f);
            checkInputs(aircraft, 0.31f, -0.42f, 0.53f, 0.24f,
                    "player input sentinels must be observable before the arbiter");
            ControlAuthorityArbiter.Authority owner = ControlAuthorityArbiter.applyControl(aircraft);
            checkInputs(aircraft, 0.31f, -0.42f, 0.53f, 0.24f,
                    "automated control must not alter any player input on takeover");
            check(owner == ControlAuthorityArbiter.Authority.PLAYER_CONTROLLED,
                    "the player must own the takeover tick");
            check(!heartbeats.contains(aircraftId),
                    "benchmark control must not run while the player owns the aircraft");
            check(AutonomousFlightManager.status(aircraftId).isEmpty(),
                    "player takeover must clear the old mob session");
        }
        helper.succeed();
    }

    private static void checkInputs(Entity aircraft, float x, float y, float z, float engine,
                                    String message) {
        check(Math.abs(inputField(aircraft, "movementX") - x) < 0.001
                        && Math.abs(inputField(aircraft, "movementY") - y) < 0.001
                        && Math.abs(inputField(aircraft, "movementZ") - z) < 0.001
                        && Math.abs(ReflectiveAircraft.engineTarget(aircraft) - engine) < 0.001,
                message);
    }

    private static float inputField(Entity aircraft, String name) {
        try {
            for (Class<?> type = aircraft.getClass(); type != null; type = type.getSuperclass()) {
                try {
                    Field field = type.getDeclaredField(name);
                    field.setAccessible(true);
                    return field.getFloat(aircraft);
                } catch (NoSuchFieldException ignored) {
                    // The field is declared on the Immersive Aircraft base vehicle class.
                }
            }
        } catch (IllegalAccessException exception) {
            throw new IllegalStateException("could not inspect aircraft input " + name, exception);
        }
        throw new IllegalStateException("aircraft input field is absent: " + name);
    }

    private static Object benchmarkInput(float x, float y, float z, float engine) {
        try {
            Class<?> type = Class.forName(BenchmarkManager.class.getName() + "$ControlInput");
            Constructor<?> constructor = type.getDeclaredConstructor(
                    float.class, float.class, float.class, float.class);
            constructor.setAccessible(true);
            return constructor.newInstance(x, y, z, engine);
        } catch (ReflectiveOperationException exception) {
            throw new IllegalStateException("could not construct benchmark positive control", exception);
        }
    }

    @SuppressWarnings("unchecked")
    private static Map<UUID, Object> benchmarkControls() {
        return (Map<UUID, Object>) staticField(BenchmarkManager.class, "CONTROLS");
    }

    @SuppressWarnings("unchecked")
    private static Set<UUID> benchmarkHeartbeats() {
        return (Set<UUID>) staticField(BenchmarkManager.class, "CONTROL_HEARTBEATS");
    }

    private static void removeAuthorityRecord(UUID aircraftId) {
        ((Map<?, ?>) staticField(ControlAuthorityArbiter.class, "LAST_AUTHORITY")).remove(aircraftId);
    }

    private static Object staticField(Class<?> type, String name) {
        try {
            Field field = type.getDeclaredField(name);
            field.setAccessible(true);
            return field.get(null);
        } catch (ReflectiveOperationException exception) {
            throw new IllegalStateException("could not inspect " + type.getSimpleName() + "." + name,
                    exception);
        }
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new IllegalStateException(message);
        }
    }
}
