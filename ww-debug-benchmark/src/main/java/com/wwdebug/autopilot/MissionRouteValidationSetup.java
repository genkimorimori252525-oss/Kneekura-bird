package com.wwdebug.autopilot;

import net.minecraft.core.BlockPos;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.phys.Vec3;

import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/** Test-only route assignment for the representative real-physics live-guidance matrix. */
final class MissionRouteValidationSetup {
    private static final String SCENARIO_PROPERTY = "wwdebug.flightGameTestScenario";
    private static final String AIRCRAFT_PROPERTY = "wwdebug.flightGameTestAircraft";
    private static final String VALIDATION_NAME_PREFIX = "AUTOPILOT TEST ";
    private static final Set<String> PROOF_AIRCRAFT = Set.of(
            "warfare_wings:a6m",
            "warfare_wings:b17",
            "warfare_wings:il2",
            "warfare_wings:g4m");
    private static final Set<UUID> APPLIED = ConcurrentHashMap.newKeySet();

    private MissionRouteValidationSetup() {
    }

    static boolean applyIfRequested(MinecraftServer server,
                                    Entity aircraft,
                                    FlightPhase phase,
                                    FlightProfile profile) {
        String requested = requestedAircraft();
        String actual = BuiltInRegistries.ENTITY_TYPE.getKey(aircraft.getType()).toString();
        if (!"full".equals(System.getProperty(SCENARIO_PROPERTY, "").trim().toLowerCase(Locale.ROOT))
                || !PROOF_AIRCRAFT.contains(requested)
                || !requested.equals(actual)
                || phase != FlightPhase.CRUISE_OUTBOUND
                || !profile.supportsAutonomousFlight()
                || !aircraft.getName().getString().startsWith(VALIDATION_NAME_PREFIX)
                || MissionOrderManager.current(aircraft.getUUID()).isPresent()
                || MissionRouteManager.current(aircraft.getUUID()).isPresent()
                || !APPLIED.add(aircraft.getUUID())) {
            return false;
        }
        if (!(aircraft.level() instanceof ServerLevel level)) {
            APPLIED.remove(aircraft.getUUID());
            return false;
        }

        Vec3 origin = aircraft.position();
        Vec3 forward = horizontal(aircraft.getLookAngle());
        if (forward.lengthSqr() < 1.0e-8) {
            forward = horizontal(Vec3.directionFromRotation(0.0f, aircraft.getYRot()));
        }
        forward = forward.normalize();
        Vec3 right = new Vec3(-forward.z, 0.0, forward.x).normalize();

        RouteGeometry geometry = geometry(profile);
        MissionOrder order = MissionOrder.builder(MissionOrder.Type.HOLD_POSITION)
                .orderId(UUID.randomUUID())
                .build();
        MissionOrderManager.Assignment mission = MissionOrderManager.assign(aircraft.getUUID(), order);
        WaypointRoute route = WaypointRoute.start(UUID.randomUUID(), List.of(
                waypoint(origin, forward, right,
                        geometry.leg(), 0.0, geometry.altitudeGain(), geometry.radius()),
                waypoint(origin, forward, right,
                        geometry.leg() * 1.55, geometry.lateral(),
                        geometry.altitudeGain() + 8.0, geometry.radius() + 4.0),
                waypoint(origin, forward, right,
                        geometry.leg() * 2.10, -geometry.lateral() * 0.85,
                        geometry.altitudeGain() + 3.0, geometry.radius() + 4.0),
                waypoint(origin, forward, right,
                        geometry.leg() * 2.65, 0.0,
                        geometry.altitudeGain() - 5.0, geometry.radius() + 8.0)));
        if (MissionRouteManager.bind(aircraft.getUUID(), mission, route).isEmpty()) {
            MissionOrderManager.clear(aircraft.getUUID(), mission.revision());
            APPLIED.remove(aircraft.getUUID());
            throw new IllegalStateException("Could not bind representative validation route for " + actual);
        }

        buildFloatingObstacle(level, origin, forward, right, geometry);
        AutopilotLogManager.writeEvent(server, aircraft, "route_validation_assigned",
                "aircraft=" + actual
                        + ":profile=" + profile.profileId()
                        + ":role=" + profile.role()
                        + ":order_id=" + order.orderId()
                        + ":route_id=" + route.routeId()
                        + ":waypoints=" + route.waypoints().size()
                        + ":leg=" + geometry.leg()
                        + ":radius=" + geometry.radius()
                        + ":obstacle_longitudinal=" + geometry.obstacleLongitudinal()
                        + ":obstacle_top_relative=12.0",
                phase);
        return true;
    }

    static void forget(UUID aircraftId) {
        APPLIED.remove(aircraftId);
    }

    private static String requestedAircraft() {
        return System.getProperty(AIRCRAFT_PROPERTY, "").trim().toLowerCase(Locale.ROOT);
    }

    private static RouteGeometry geometry(FlightProfile profile) {
        // PR #53 proved a remaining live-route distance of roughly 730 blocks. Scale the
        // representative route by measured cruise speed while keeping the whole proof within the
        // unchanged return-to-pattern budget for both fast fighters and slow heavy aircraft.
        double leg = clamp(profile.cruiseSpeedBps() * 7.5, 220.0, 280.0);
        boolean heavy = profile.isLevelBomber() || profile.isTorpedoBomber();
        double lateral = heavy ? 135.0 : profile.isAttacker() ? 105.0 : 95.0;
        double radius = heavy ? 78.0 : profile.isAttacker() ? 62.0 : 54.0;
        double altitudeGain = heavy ? 36.0 : profile.isAttacker() ? 30.0 : 26.0;
        int obstacleHalfWidth = heavy ? 52 : 42;
        // Keep the barrier inside the first predictive-terrain sensor horizon for every role.
        // This proves route-before-terrain precedence without measuring reaction to a late-spawned wall.
        double obstacleLongitudinal = clamp(profile.cruiseSpeedBps() * 3.5, 55.0, 120.0);
        return new RouteGeometry(
                leg,
                lateral,
                radius,
                altitudeGain,
                obstacleLongitudinal,
                obstacleHalfWidth,
                32);
    }

    private static WaypointRoute.Waypoint waypoint(Vec3 origin, Vec3 forward, Vec3 right,
                                                     double longitudinal, double lateral,
                                                     double relativeAltitude, double radius) {
        Vec3 position = origin.add(forward.scale(longitudinal))
                .add(right.scale(lateral))
                .add(0.0, relativeAltitude, 0.0);
        return new WaypointRoute.Waypoint(position, radius);
    }

    private static void buildFloatingObstacle(ServerLevel level,
                                               Vec3 origin,
                                               Vec3 forward,
                                               Vec3 right,
                                               RouteGeometry geometry) {
        // Match the proven PR #53 vertical relationship: the barrier intersects the current
        // flight path, but its top is only 12 blocks above live cruise altitude. Terrain safety
        // must still override route guidance without demanding an artificial 40-block zoom climb.
        Vec3 center = origin.add(forward.scale(geometry.obstacleLongitudinal()))
                .add(0.0, -20.0, 0.0);
        for (int lateral = -geometry.obstacleHalfWidth();
             lateral <= geometry.obstacleHalfWidth(); lateral++) {
            for (int depth = -2; depth <= 2; depth++) {
                for (int vertical = -geometry.obstacleHalfHeight();
                     vertical <= geometry.obstacleHalfHeight(); vertical++) {
                    Vec3 point = center
                            .add(right.scale(lateral))
                            .add(forward.scale(depth))
                            .add(0.0, vertical, 0.0);
                    level.setBlock(BlockPos.containing(point), Blocks.STONE.defaultBlockState(), 2);
                }
            }
        }
    }

    private static double clamp(double value, double minimum, double maximum) {
        return Math.max(minimum, Math.min(maximum, value));
    }

    private static Vec3 horizontal(Vec3 value) {
        return new Vec3(value.x, 0.0, value.z);
    }

    private record RouteGeometry(double leg,
                                 double lateral,
                                 double radius,
                                 double altitudeGain,
                                 double obstacleLongitudinal,
                                 int obstacleHalfWidth,
                                 int obstacleHalfHeight) {
    }
}
