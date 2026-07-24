package com.wwdebug.autopilot;

import net.minecraft.core.BlockPos;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.phys.Vec3;

import java.util.List;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/** Test-only route assignment for the first real-physics live-guidance proof. */
final class MissionRouteValidationSetup {
    private static final String SCENARIO_PROPERTY = "wwdebug.flightGameTestScenario";
    private static final String VALIDATION_NAME_PREFIX = "AUTOPILOT TEST ";
    private static final String PROOF_AIRCRAFT = "warfare_wings:a6m";
    private static final Set<UUID> APPLIED = ConcurrentHashMap.newKeySet();

    private MissionRouteValidationSetup() {
    }

    static boolean applyIfRequested(MinecraftServer server, Entity aircraft) {
        if (!"full".equals(System.getProperty(SCENARIO_PROPERTY, "full").trim().toLowerCase())
                || !aircraft.getName().getString().startsWith(VALIDATION_NAME_PREFIX)
                || !PROOF_AIRCRAFT.equals(BuiltInRegistries.ENTITY_TYPE.getKey(aircraft.getType()).toString())
                || MissionOrderManager.current(aircraft.getUUID()).isPresent()
                || MissionRouteManager.current(aircraft.getUUID()).isPresent()
                || !APPLIED.add(aircraft.getUUID())) {
            return false;
        }
        if (!(aircraft.level() instanceof ServerLevel level)) {
            APPLIED.remove(aircraft.getUUID());
            return false;
        }

        Vec3 home = aircraft.position();
        Vec3 forward = horizontal(aircraft.getLookAngle());
        if (forward.lengthSqr() < 1.0e-8) {
            forward = horizontal(Vec3.directionFromRotation(0.0f, aircraft.getYRot()));
        }
        forward = forward.normalize();
        Vec3 right = new Vec3(-forward.z, 0.0, forward.x).normalize();

        MissionOrder order = MissionOrder.builder(MissionOrder.Type.HOLD_POSITION)
                .orderId(UUID.randomUUID())
                .build();
        MissionOrderManager.Assignment mission = MissionOrderManager.assign(aircraft.getUUID(), order);
        WaypointRoute route = WaypointRoute.start(UUID.randomUUID(), List.of(
                waypoint(home, forward, right, 600.0, 0.0, 90.0, 42.0),
                waypoint(home, forward, right, 690.0, 80.0, 100.0, 40.0),
                waypoint(home, forward, right, 780.0, -60.0, 95.0, 40.0),
                waypoint(home, forward, right, 850.0, 0.0, 90.0, 45.0)));
        if (MissionRouteManager.bind(aircraft.getUUID(), mission, route).isEmpty()) {
            MissionOrderManager.clear(aircraft.getUUID(), mission.revision());
            APPLIED.remove(aircraft.getUUID());
            throw new IllegalStateException("Could not bind validation route to current A6M mission");
        }

        buildFloatingObstacle(level, home, forward, right);
        AutopilotLogManager.writeEvent(server, aircraft, "route_validation_assigned",
                "order_id=" + order.orderId()
                        + ":route_id=" + route.routeId()
                        + ":waypoints=" + route.waypoints().size()
                        + ":obstacle_longitudinal=500.0",
                FlightPhase.STARTUP);
        return true;
    }

    private static WaypointRoute.Waypoint waypoint(Vec3 home, Vec3 forward, Vec3 right,
                                                    double longitudinal, double lateral,
                                                    double relativeAltitude, double radius) {
        Vec3 position = home.add(forward.scale(longitudinal))
                .add(right.scale(lateral))
                .add(0.0, relativeAltitude, 0.0);
        return new WaypointRoute.Waypoint(position, radius);
    }

    private static void buildFloatingObstacle(ServerLevel level, Vec3 home,
                                              Vec3 forward, Vec3 right) {
        Vec3 center = home.add(forward.scale(500.0)).add(0.0, 77.0, 0.0);
        for (int lateral = -24; lateral <= 24; lateral++) {
            for (int depth = -2; depth <= 2; depth++) {
                for (int vertical = -32; vertical <= 32; vertical++) {
                    Vec3 point = center
                            .add(right.scale(lateral))
                            .add(forward.scale(depth))
                            .add(0.0, vertical, 0.0);
                    level.setBlock(BlockPos.containing(point), Blocks.STONE.defaultBlockState(), 2);
                }
            }
        }
    }

    private static Vec3 horizontal(Vec3 value) {
        return new Vec3(value.x, 0.0, value.z);
    }
}
