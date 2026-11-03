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
import net.minecraft.world.phys.Vec3;
import net.minecraftforge.gametest.GameTestHolder;
import net.minecraftforge.gametest.PrefixGameTestTemplate;

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
        try {
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
            helper.succeed();
        } finally {
            AutonomousFlightManager.forceStop(aircraft.getUUID(), "collision_risk_test_cleanup");
            pilot.discard();
            nearby.discard();
            aircraft.discard();
        }
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new IllegalStateException(message);
        }
    }
}
