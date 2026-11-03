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
import net.minecraft.world.level.ClipContext;
import net.minecraft.world.phys.HitResult;
import net.minecraft.world.phys.Vec3;
import net.minecraftforge.gametest.GameTestHolder;
import net.minecraftforge.gametest.PrefixGameTestTemplate;

import java.lang.reflect.Field;
import java.util.Map;

/** Tests the real arbiter against the fixed-version aircraft runtime and measured profile. */
@GameTestHolder(WWDebugBenchmarkMod.MOD_ID)
@PrefixGameTestTemplate(false)
public final class CollisionRiskControlGameTests {
    private CollisionRiskControlGameTests() {
    }

    @GameTest(template = "empty", timeoutTicks = 40, batch = "collision_risk_control")
    public static void startupRiskWithoutAvoidanceRetainsAutonomyInput(GameTestHelper helper) {
        ServerLevel level = helper.getLevel();
        EntityType<?> type = BuiltInRegistries.ENTITY_TYPE
                .getOptional(new ResourceLocation("warfare_wings", "a6m"))
                .orElseThrow(() -> new IllegalStateException("fixed Warfare Wings A6M is required"));
        Entity aircraft = type.create(level);
        Entity nearby = type.create(level);
        Villager pilot = EntityType.VILLAGER.create(level);
        check(aircraft != null && nearby != null && pilot != null, "could not create test entities");
        try (SafetyFixtureLogIsolation.Cleanup cleanup = new SafetyFixtureLogIsolation.Cleanup()) {
            cleanup.add(() -> AutonomousFlightManager.forceStop(aircraft.getUUID(), "collision_risk_test_cleanup"));
            cleanup.add(() -> FormationFlightManager.clear(aircraft.getUUID()));
            cleanup.add(() -> SafetyFixtureLogIsolation.clearAuthority(aircraft.getUUID()));
            cleanup.add(pilot::discard);
            cleanup.add(nearby::discard);
            cleanup.add(aircraft::discard);
            cleanup.add(() -> SafetyFixtureLogIsolation.isolate(level.getServer(), aircraft.getUUID()));
            Vec3 origin = Vec3.atBottomCenterOf(helper.absolutePos(new BlockPos(1, 2, 1)));
            aircraft.moveTo(origin.x, origin.y, origin.z, 0.0f, 0.0f);
            nearby.moveTo(origin.x + 5.0, origin.y, origin.z, 0.0f, 0.0f);
            pilot.moveTo(origin.x, origin.y, origin.z, 0.0f, 0.0f);
            pilot.setNoAi(true);
            aircraft.setDeltaMovement(Vec3.ZERO);
            nearby.setDeltaMovement(Vec3.ZERO);
            check(level.addFreshEntity(aircraft) && level.addFreshEntity(nearby)
                    && level.addFreshEntity(pilot), "could not add test entities to the server");
            ReflectiveAircraft.fillFuel(aircraft);
            check(pilot.startRiding(aircraft, true) && MobPilotGate.isMobPiloted(aircraft),
                    "the villager must hold the aircraft controls");
            // The real engine refuels only while occupied. The setup tick can start autonomy;
            // end that session so the assertion below exercises a fresh STARTUP decision.
            aircraft.tick();
            AutonomousFlightManager.forceStop(aircraft.getUUID(), "collision_risk_fixture_reset");
            check(ReflectiveAircraft.fuelUtilization(aircraft) > 0.0,
                    "the test aircraft must have usable fuel before setting the sentinel");
            aircraft.moveTo(origin.x, origin.y, origin.z, 0.0f, 0.0f);
            aircraft.setDeltaMovement(Vec3.ZERO);
            check(ReflectiveAircraft.isAirplane(aircraft) && ReflectiveAircraft.isControllable(aircraft),
                    "the primary entity must expose real aircraft controls");
            check(AutopilotProfileRegistry.resolve(level.getServer(), aircraft).isPresent(),
                    "the A6M measured profile must be staged");
            check(AirspaceSafetyProbe.collisionRisk(aircraft),
                    "the neighboring aircraft must trigger the real collision probe");

            // STARTUP is not an eligible formation/avoidance phase. Its normal input commands
            // full engine power, so a distinct sentinel exposes a missing autonomy write.
            ReflectiveAircraft.applyControl(aircraft, 0.0f, 0.0f, 0.0f, 0.13f);
            check(Math.abs(ReflectiveAircraft.engineTarget(aircraft) - 0.13) < 0.001,
                    "the engine-target sentinel must be observable before the arbiter runs");
            ControlAuthorityArbiter.applyControl(aircraft);
            check(AutonomousFlightManager.status(aircraft.getUUID())
                            .map(status -> status.phase() == FlightPhase.STARTUP).orElse(false),
                    "the test must exercise STARTUP, where collision avoidance does not write");
            check(Math.abs(ReflectiveAircraft.engineTarget(aircraft) - 1.0) < 0.001,
                    "collision risk without an avoidance write must retain the startup engine input");
        }
        helper.succeed();
    }

    @GameTest(template = "empty", timeoutTicks = 40, batch = "collision_risk_control")
    public static void collisionAvoidanceInputSurvivesAutonomyFallback(GameTestHelper helper) {
        ServerLevel level = helper.getLevel();
        EntityType<?> type = BuiltInRegistries.ENTITY_TYPE
                .getOptional(new ResourceLocation("warfare_wings", "a6m"))
                .orElseThrow(() -> new IllegalStateException("fixed Warfare Wings A6M is required"));
        Entity first = type.create(level);
        Entity second = type.create(level);
        Villager pilot = EntityType.VILLAGER.create(level);
        check(first != null && second != null && pilot != null, "could not create test entities");
        // The larger UUID is the secondary aircraft, whose avoidance engine command is 0.28.
        Entity aircraft = first.getUUID().compareTo(second.getUUID()) > 0 ? first : second;
        Entity nearby = aircraft == first ? second : first;
        try (SafetyFixtureLogIsolation.Cleanup cleanup = new SafetyFixtureLogIsolation.Cleanup()) {
            cleanup.add(() -> AutonomousFlightManager.forceStop(aircraft.getUUID(), "collision_avoidance_test_cleanup"));
            cleanup.add(() -> FormationFlightManager.clear(aircraft.getUUID()));
            cleanup.add(() -> SafetyFixtureLogIsolation.clearAuthority(aircraft.getUUID()));
            cleanup.add(pilot::discard);
            cleanup.add(nearby::discard);
            cleanup.add(aircraft::discard);
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
            // As in the STARTUP test, a tick with an occupant is needed to load engine fuel.
            aircraft.tick();
            check(ReflectiveAircraft.fuelUtilization(aircraft) > 0.0,
                    "the test aircraft must have usable fuel");
            FlightProfile profile = AutopilotProfileRegistry.resolve(level.getServer(), aircraft)
                    .orElseThrow(() -> new IllegalStateException("the A6M measured profile is required"));
            check(AutonomousFlightManager.status(aircraft.getUUID()).isPresent(),
                    "the setup tick must create the autonomous session");

            // Keep this synthetic scene inside one synchronous GameTest call: no physics tick can
            // move either aircraft or overwrite the command before it is inspected.
            Vec3 airborne = ground.add(0.0, 100.0, 0.0);
            aircraft.moveTo(airborne.x, airborne.y, airborne.z, 0.0f, 0.0f);
            nearby.moveTo(airborne.x + 5.0, airborne.y, airborne.z, 0.0f, 0.0f);
            aircraft.setOnGround(false);
            double speed = Math.max(profile.cruiseSpeedBps() * 1.15,
                    profile.stallGuardSpeedBps() * 1.35);
            aircraft.setDeltaMovement(0.0, 0.0, speed / 20.0);
            nearby.setDeltaMovement(0.0, 0.0, speed / 20.0);
            seedCruisePhase(aircraft);
            FlightSnapshot snapshot = FlightSnapshot.capture(aircraft);
            check(!snapshot.onGround() && snapshot.altitudeAboveGround() >= 55.0,
                    "the aircraft must be airborne with clearance for the secondary escape");
            check(snapshot.speedBps() > profile.cruiseSpeedBps() * 1.08
                            && snapshot.speedBps() >= profile.stallGuardSpeedBps() * 1.25,
                    "cruise and collision commands must remain distinguishable and above stall guard");
            Vec3 rayStart = aircraft.getBoundingBox().getCenter();
            check(level.clip(new ClipContext(rayStart,
                            rayStart.add(aircraft.getLookAngle().normalize().scale(48.0)),
                            ClipContext.Block.COLLIDER, ClipContext.Fluid.NONE, aircraft)).getType()
                            == HitResult.Type.MISS,
                    "the forward terrain ray must be clear for collision avoidance");
            check(AirspaceSafetyProbe.collisionRisk(aircraft),
                    "the neighboring aircraft must trigger the real collision probe");
            check(AirspaceSafetyProbe.nearbyAircraft(level, aircraft).stream()
                            .filter(other -> AirspaceSafetyProbe.predict(aircraft, other).dangerous())
                            .allMatch(other -> other == nearby),
                    "no unrelated dangerous aircraft may affect this fixture");

            ControlAuthorityArbiter.Authority owner = ControlAuthorityArbiter.applyControl(aircraft);
            check(AutonomousFlightManager.status(aircraft.getUUID())
                            .map(status -> status.phase() == FlightPhase.CRUISE_OUTBOUND).orElse(false),
                    "the test must remain in an avoidance-eligible cruise phase");
            check(!TerrainAvoidancePlanner.active(aircraft),
                    "terrain avoidance must not preempt this collision-only test");
            check(owner == ControlAuthorityArbiter.Authority.COLLISION_AVOIDANCE,
                    "the collision layer must own the tick");
            // Cruise would command 0.35 at this speed. If its pending proposal overwrites the
            // secondary collision escape, the observed target becomes 0.35 rather than 0.28.
            check(Math.abs(ReflectiveAircraft.engineTarget(aircraft) - 0.28) < 0.001,
                    "the collision avoidance engine input must survive the autonomy fallback");
        }
        helper.succeed();
    }

    private static void seedCruisePhase(Entity aircraft) {
        try {
            Field sessionsField = AutonomousFlightManager.class.getDeclaredField("SESSIONS");
            sessionsField.setAccessible(true);
            Map<?, ?> sessions = (Map<?, ?>) sessionsField.get(null);
            Object entry = sessions.get(aircraft.getUUID());
            check(entry != null, "the autonomous session must exist before seeding cruise");
            Field sessionField = entry.getClass().getDeclaredField("session");
            sessionField.setAccessible(true);
            Object session = sessionField.get(entry);
            Field phaseField = AutopilotSession.class.getDeclaredField("phase");
            phaseField.setAccessible(true);
            phaseField.set(session, FlightPhase.CRUISE_OUTBOUND);
            Field phaseTicksField = AutopilotSession.class.getDeclaredField("phaseTicks");
            phaseTicksField.setAccessible(true);
            phaseTicksField.setInt(session, 0);
        } catch (ReflectiveOperationException exception) {
            throw new IllegalStateException("could not seed the test-only cruise phase", exception);
        }
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new IllegalStateException(message);
        }
    }
}
