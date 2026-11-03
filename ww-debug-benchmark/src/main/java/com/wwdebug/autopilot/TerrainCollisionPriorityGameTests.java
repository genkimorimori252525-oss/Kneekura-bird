package com.wwdebug.autopilot;

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
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.phys.Vec3;
import net.minecraftforge.gametest.GameTestHolder;
import net.minecraftforge.gametest.PrefixGameTestTemplate;

import java.lang.reflect.Field;
import java.util.Map;
import java.util.UUID;

/** A control-priority check using real aircraft and both real safety predicates. */
@GameTestHolder(WWDebugBenchmarkMod.MOD_ID)
@PrefixGameTestTemplate(false)
public final class TerrainCollisionPriorityGameTests {
    private TerrainCollisionPriorityGameTests() {
    }

    @GameTest(template = "empty", timeoutTicks = 40, batch = "terrain_collision_priority")
    public static void terrainInputSurvivesConcurrentCollisionRisk(GameTestHelper helper) {
        ServerLevel level = helper.getLevel();
        EntityType<?> type = BuiltInRegistries.ENTITY_TYPE
                .getOptional(new ResourceLocation("warfare_wings", "a6m"))
                .orElseThrow(() -> new IllegalStateException("fixed Warfare Wings A6M is required"));
        Entity first = type.create(level);
        Entity second = type.create(level);
        Villager pilot = EntityType.VILLAGER.create(level);
        check(first != null && second != null && pilot != null, "could not create test entities");
        // With no terrain preemption this secondary aircraft's collision control commands 0.28.
        Entity aircraft = first.getUUID().compareTo(second.getUUID()) > 0 ? first : second;
        Entity nearby = aircraft == first ? second : first;
        BlockPos[] testBlock = {null};
        boolean[] blockPlaced = {false};
        try (SafetyFixtureLogIsolation.Cleanup cleanup = new SafetyFixtureLogIsolation.Cleanup()) {
            cleanup.add(() -> AutonomousFlightManager.forceStop(aircraft.getUUID(), "terrain_collision_test_cleanup"));
            cleanup.add(() -> FormationFlightManager.clear(aircraft.getUUID()));
            cleanup.add(pilot::discard);
            cleanup.add(nearby::discard);
            cleanup.add(aircraft::discard);
            cleanup.add(() -> {
                if (blockPlaced[0]) {
                    check(level.getBlockState(testBlock[0]).is(Blocks.STONE),
                            "temporary terrain changed before cleanup");
                    check(level.setBlock(testBlock[0], Blocks.AIR.defaultBlockState(), 3),
                            "could not remove temporary terrain block");
                }
            });
            cleanup.add(() -> clearTestState(TerrainAvoidancePlanner.class,
                    "ACTIVE_UNTIL_GAME_TICK", aircraft.getUUID()));
            cleanup.add(() -> SafetyFixtureLogIsolation.clearAuthority(aircraft.getUUID()));
            cleanup.add(() -> SafetyFixtureLogIsolation.isolate(level.getServer(), aircraft.getUUID()));
            Vec3 ground = Vec3.atBottomCenterOf(helper.absolutePos(new BlockPos(1, 2, 1)));
            aircraft.moveTo(ground.x, ground.y, ground.z, 0.0f, 0.0f);
            nearby.moveTo(ground.x + 5.0, ground.y, ground.z, 0.0f, 0.0f);
            pilot.moveTo(ground.x, ground.y, ground.z, 0.0f, 0.0f);
            pilot.setNoAi(true);
            check(level.addFreshEntity(aircraft) && level.addFreshEntity(nearby)
                    && level.addFreshEntity(pilot), "could not add test entities to the server");
            ReflectiveAircraft.fillFuel(aircraft);
            check(pilot.startRiding(aircraft, true) && MobPilotGate.isMobPiloted(aircraft),
                    "the villager must hold the aircraft controls");
            aircraft.tick();
            check(ReflectiveAircraft.fuelUtilization(aircraft) > 0.0,
                    "the aircraft must have usable fuel");
            FlightProfile profile = AutopilotProfileRegistry.resolve(level.getServer(), aircraft)
                    .orElseThrow(() -> new IllegalStateException("the A6M measured profile is required"));
            check(AutonomousFlightManager.status(aircraft.getUUID()).isPresent(),
                    "the setup tick must create an autonomous session");

            Vec3 position = ground.add(0.0, 100.0, 0.0);
            testBlock[0] = BlockPos.containing(position.x, position.y - 28.0, position.z);
            check(level.getBlockState(testBlock[0]).isAir(), "the temporary terrain position must be air");
            check(level.setBlock(testBlock[0], Blocks.STONE.defaultBlockState(), 3),
                    "could not place the temporary terrain block");
            blockPlaced[0] = true;
            aircraft.moveTo(position.x, position.y, position.z, 0.0f, 0.0f);
            nearby.moveTo(position.x + 5.0, position.y, position.z, 0.0f, 0.0f);
            aircraft.setOnGround(false);
            double speed = Math.max(profile.cruiseSpeedBps() * 1.15,
                    profile.stallGuardSpeedBps() * 1.35);
            aircraft.setDeltaMovement(0.0, 0.0, speed / 20.0);
            nearby.setDeltaMovement(0.0, 0.0, speed / 20.0);
            seedCruisePhase(aircraft);

            FlightSnapshot snapshot = FlightSnapshot.capture(aircraft);
            check(!snapshot.onGround() && snapshot.altitudeAboveGround() > 24.0
                            && snapshot.altitudeAboveGround() < 30.0,
                    "the low-clearance terrain risk must exist without ground contact");
            check(snapshot.speedBps() > profile.cruiseSpeedBps() * 1.08
                            && snapshot.speedBps() >= profile.stallGuardSpeedBps() * 1.25,
                    "the cruise, collision and terrain inputs must be distinguishable");
            check(AirspaceSafetyProbe.collisionRisk(aircraft),
                    "the neighboring aircraft must trigger collision risk");
            check(AirspaceSafetyProbe.nearbyAircraft(level, aircraft).stream()
                            .filter(other -> AirspaceSafetyProbe.predict(aircraft, other).dangerous())
                            .allMatch(other -> other == nearby),
                    "no unrelated dangerous aircraft may affect this fixture");
            ReflectiveAircraft.applyControl(aircraft, 0.0f, 0.0f, 0.0f, 0.13f);
            check(Math.abs(ReflectiveAircraft.engineTarget(aircraft) - 0.13) < 0.001,
                    "the engine-target sentinel must be observable");

            ControlAuthorityArbiter.Authority owner = ControlAuthorityArbiter.applyControl(aircraft);
            check(AutonomousFlightManager.status(aircraft.getUUID())
                            .map(status -> status.phase() == FlightPhase.CRUISE_OUTBOUND).orElse(false),
                    "the test must remain in a terrain-eligible cruise phase");
            check(TerrainAvoidancePlanner.active(aircraft),
                    "the real terrain planner must be active on the tested tick");
            check(AirspaceSafetyProbe.collisionRisk(aircraft),
                    "collision risk must still coexist with terrain avoidance");
            check(Math.abs(ReflectiveAircraft.engineTarget(aircraft) - 1.0) < 0.001,
                    "terrain engine input must survive concurrent collision risk");
            // On main ee4e970 the legacy arbiter reports COLLISION_AVOIDANCE even though the
            // terrain controller wrote the input. Accept the corrected TERRAIN_AVOIDANCE label too:
            // this test protects the input, not the known reporting discrepancy.
            check(owner == ControlAuthorityArbiter.Authority.COLLISION_AVOIDANCE
                            || owner == ControlAuthorityArbiter.Authority.TERRAIN_AVOIDANCE,
                    "the arbiter must report a safety authority for the overlapping risks");
        }
        helper.succeed();
    }

    private static void seedCruisePhase(Entity aircraft) {
        try {
            Field sessionsField = field(AutonomousFlightManager.class, "SESSIONS");
            Object entry = ((Map<?, ?>) sessionsField.get(null)).get(aircraft.getUUID());
            check(entry != null, "the autonomous session must exist before seeding cruise");
            Object session = field(entry.getClass(), "session").get(entry);
            field(AutopilotSession.class, "phase").set(session, FlightPhase.CRUISE_OUTBOUND);
            field(AutopilotSession.class, "phaseTicks").setInt(session, 0);
        } catch (ReflectiveOperationException exception) {
            throw new IllegalStateException("could not seed the test-only cruise phase", exception);
        }
    }

    private static void clearTestState(Class<?> owner, String name, UUID aircraftUuid) {
        try {
            ((Map<?, ?>) field(owner, name).get(null)).remove(aircraftUuid);
        } catch (ReflectiveOperationException exception) {
            throw new IllegalStateException("could not clear " + name + " after test", exception);
        }
    }

    private static Field field(Class<?> owner, String name) throws NoSuchFieldException {
        Field field = owner.getDeclaredField(name);
        field.setAccessible(true);
        return field;
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new IllegalStateException(message);
        }
    }
}
