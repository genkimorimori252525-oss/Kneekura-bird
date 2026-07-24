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

/** Test-only route assignment for exact-physics live-guidance proofs. */
final class MissionRouteValidationSetup {
    private static final String SCENARIO_PROPERTY = "wwdebug.flightGameTestScenario";
    private static final String AIRCRAFT_PROPERTY = "wwdebug.flightGameTestAircraft";
    private static final String VALIDATION_NAME_PREFIX = "AUTOPILOT TEST ";
    private static final String A6M = "warfare_wings:a6m";
    private static final String B17 = "warfare_wings:b17";
    private static final String G4M = "warfare_wings:g4m";
    private static final String IL2 = "warfare_wings:il2";
    private static final Set<String> FULL_PROOFS = Set.of(A6M, B17, G4M, IL2);
    private static final Set<UUID> APPLIED = ConcurrentHashMap.newKeySet();

    private MissionRouteValidationSetup() {
    }

    static boolean applyIfRequested(MinecraftServer server, Entity aircraft,
                                    FlightPhase phase, FlightProfile profile) {
        String scenario = scenario();
        String requested = requestedAircraft();
        String actual = BuiltInRegistries.ENTITY_TYPE.getKey(aircraft.getType()).toString();
        boolean genericRoute = "route".equals(scenario);
        boolean representativeFull = "full".equals(scenario) && FULL_PROOFS.contains(requested);
        if ((!genericRoute && !representativeFull)
                || !requested.equals(actual)
                || !aircraft.getName().getString().startsWith(VALIDATION_NAME_PREFIX)
                || MissionOrderManager.current(aircraft.getUUID()).isPresent()
                || MissionRouteManager.current(aircraft.getUUID()).isPresent()
                || !eligibleStart(scenario, requested, phase, profile)
                || !APPLIED.add(aircraft.getUUID())) {
            return false;
        }
        if (!(aircraft.level() instanceof ServerLevel level)) {
            APPLIED.remove(aircraft.getUUID());
            return false;
        }

        if (genericRoute) {
            assignProfileDrivenProof(server, aircraft, phase, profile, requested);
        } else if (A6M.equals(requested)) {
            assignA6mProof(server, level, aircraft);
        } else if (B17.equals(requested)) {
            assignRepresentativeCompactProof(server, aircraft, phase, profile, requested,
                    geometryForRole("bomber"), "B-17");
        } else if (G4M.equals(requested)) {
            assignRepresentativeCompactProof(server, aircraft, phase, profile, requested,
                    geometryForRole("torpedo_bomber"), "G4M");
        } else {
            assignRepresentativeCompactProof(server, aircraft, phase, profile, requested,
                    geometryForRole("attacker"), "IL-2");
        }
        return true;
    }

    static void forget(UUID aircraftId) {
        APPLIED.remove(aircraftId);
    }

    private static boolean eligibleStart(String scenario, String requested,
                                         FlightPhase phase, FlightProfile profile) {
        if ("full".equals(scenario) && A6M.equals(requested)) {
            return true;
        }
        if (phase != FlightPhase.CRUISE_OUTBOUND || !profile.supportsAutonomousFlight()) {
            return false;
        }
        if ("route".equals(scenario)) {
            return true;
        }
        if (B17.equals(requested)) {
            return profile.isLevelBomber();
        }
        if (G4M.equals(requested)) {
            return profile.isTorpedoBomber();
        }
        return profile.isAttacker();
    }

    private static void assignProfileDrivenProof(MinecraftServer server, Entity aircraft,
                                                 FlightPhase phase, FlightProfile profile,
                                                 String requested) {
        ProfileDrivenRoutePlan.Plan plan = ProfileDrivenRoutePlan.plan(profile);
        MissionOrder order = MissionOrder.builder(MissionOrder.Type.HOLD_POSITION)
                .orderId(UUID.randomUUID())
                .build();
        MissionOrderManager.Assignment mission = MissionOrderManager.assign(aircraft.getUUID(), order);
        WaypointRoute route = ProfileDrivenRoutePlan.build(
                UUID.randomUUID(), aircraft.position(), forward(aircraft), profile);
        bind(aircraft, mission, route, requested);
        AutopilotLogManager.writeEvent(server, aircraft, "route_validation_assigned",
                "scenario=route:aircraft=" + requested + ":profile=" + profile.profileId()
                        + ":role=" + plan.role() + ":order_id=" + order.orderId()
                        + ":route_id=" + route.routeId() + ":waypoints=4:compact=true"
                        + ":leg=" + plan.legBlocks() + ":terrain_proof=false",
                phase);
    }

    private static void assignA6mProof(MinecraftServer server, ServerLevel level, Entity aircraft) {
        Vec3 home = aircraft.position();
        Vec3 forward = forward(aircraft);
        Vec3 right = new Vec3(-forward.z, 0.0, forward.x).normalize();
        MissionOrder order = MissionOrder.builder(MissionOrder.Type.HOLD_POSITION)
                .orderId(UUID.randomUUID())
                .build();
        MissionOrderManager.Assignment mission = MissionOrderManager.assign(aircraft.getUUID(), order);
        WaypointRoute route = WaypointRoute.start(UUID.randomUUID(), List.of(
                waypoint(home, forward, right, 1100.0, 0.0, 100.0, 42.0),
                waypoint(home, forward, right, 1280.0, 100.0, 105.0, 40.0),
                waypoint(home, forward, right, 1440.0, -80.0, 100.0, 40.0),
                waypoint(home, forward, right, 1580.0, 0.0, 95.0, 45.0)));
        bind(aircraft, mission, route, "A6M");
        buildA6mObstacle(level, home, forward, right);
        AutopilotLogManager.writeEvent(server, aircraft, "route_validation_assigned",
                "scenario=full:aircraft=" + A6M + ":order_id=" + order.orderId()
                        + ":route_id=" + route.routeId() + ":waypoints=4:terrain_proof=true",
                FlightPhase.STARTUP);
    }

    private static void assignRepresentativeCompactProof(MinecraftServer server, Entity aircraft,
                                                          FlightPhase phase, FlightProfile profile,
                                                          String requested, RouteGeometry geometry,
                                                          String label) {
        Vec3 origin = aircraft.position();
        Vec3 forward = forward(aircraft);
        Vec3 right = new Vec3(-forward.z, 0.0, forward.x).normalize();
        MissionOrder order = MissionOrder.builder(MissionOrder.Type.HOLD_POSITION)
                .orderId(UUID.randomUUID())
                .build();
        MissionOrderManager.Assignment mission = MissionOrderManager.assign(aircraft.getUUID(), order);
        WaypointRoute route = WaypointRoute.start(UUID.randomUUID(), List.of(
                waypoint(origin, forward, right, geometry.leg(), 0.0,
                        geometry.altitude1(), geometry.radius1()),
                waypoint(origin, forward, right, geometry.leg() * 1.45, geometry.lateral2(),
                        geometry.altitude2(), geometry.radius2()),
                waypoint(origin, forward, right, geometry.leg() * 1.90, geometry.lateral3(),
                        geometry.altitude3(), geometry.radius3()),
                waypoint(origin, forward, right, geometry.leg() * 2.35, 0.0,
                        geometry.altitude4(), geometry.radius4())));
        bind(aircraft, mission, route, label);
        AutopilotLogManager.writeEvent(server, aircraft, "route_validation_assigned",
                "scenario=full:aircraft=" + requested + ":profile=" + profile.profileId()
                        + ":role=" + geometry.role() + ":order_id=" + order.orderId()
                        + ":route_id=" + route.routeId() + ":waypoints=4:compact=true"
                        + ":leg=" + geometry.leg() + ":terrain_proof=false",
                phase);
    }

    private static RouteGeometry geometryForRole(String role) {
        return switch (role) {
            case "attacker" -> new RouteGeometry(role, 150.0, 45.0, -38.0,
                    18.0, 24.0, 20.0, 16.0, 58.0, 62.0, 62.0, 68.0);
            case "torpedo_bomber" -> new RouteGeometry(role, 145.0, 55.0, -48.0,
                    24.0, 30.0, 26.0, 20.0, 72.0, 76.0, 76.0, 82.0);
            case "bomber" -> new RouteGeometry(role, 125.0, 20.0, -16.0,
                    16.0, 20.0, 18.0, 14.0, 78.0, 82.0, 82.0, 88.0);
            default -> throw new IllegalArgumentException("Unsupported representative role " + role);
        };
    }

    private static void bind(Entity aircraft, MissionOrderManager.Assignment mission,
                             WaypointRoute route, String label) {
        if (MissionRouteManager.bind(aircraft.getUUID(), mission, route).isEmpty()) {
            MissionOrderManager.clear(aircraft.getUUID(), mission.revision());
            APPLIED.remove(aircraft.getUUID());
            throw new IllegalStateException("Could not bind validation route for " + label);
        }
    }

    private static WaypointRoute.Waypoint waypoint(Vec3 origin, Vec3 forward, Vec3 right,
                                                     double longitudinal, double lateral,
                                                     double relativeAltitude, double radius) {
        Vec3 position = origin.add(forward.scale(longitudinal))
                .add(right.scale(lateral)).add(0.0, relativeAltitude, 0.0);
        return new WaypointRoute.Waypoint(position, radius);
    }

    private static Vec3 forward(Entity aircraft) {
        Vec3 value = horizontal(aircraft.getLookAngle());
        if (value.lengthSqr() < 1.0e-8) {
            value = horizontal(Vec3.directionFromRotation(0.0f, aircraft.getYRot()));
        }
        return value.normalize();
    }

    private static void buildA6mObstacle(ServerLevel level, Vec3 home,
                                         Vec3 forward, Vec3 right) {
        Vec3 center = home.add(forward.scale(970.0)).add(0.0, 80.0, 0.0);
        for (int lateral = -30; lateral <= 30; lateral++) {
            for (int depth = -2; depth <= 2; depth++) {
                for (int vertical = -32; vertical <= 32; vertical++) {
                    Vec3 point = center.add(right.scale(lateral)).add(forward.scale(depth))
                            .add(0.0, vertical, 0.0);
                    level.setBlock(BlockPos.containing(point), Blocks.STONE.defaultBlockState(), 2);
                }
            }
        }
    }

    private static String scenario() {
        return System.getProperty(SCENARIO_PROPERTY, "").trim().toLowerCase(Locale.ROOT);
    }

    private static String requestedAircraft() {
        return System.getProperty(AIRCRAFT_PROPERTY, "").trim().toLowerCase(Locale.ROOT);
    }

    private static Vec3 horizontal(Vec3 value) {
        return new Vec3(value.x, 0.0, value.z);
    }

    private record RouteGeometry(String role, double leg, double lateral2, double lateral3,
                                 double altitude1, double altitude2, double altitude3,
                                 double altitude4, double radius1, double radius2,
                                 double radius3, double radius4) {
    }
}
