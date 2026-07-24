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
    private static final String G4M = "warfare_wings:g4m";
    private static final String IL2 = "warfare_wings:il2";
    private static final Set<UUID> APPLIED = ConcurrentHashMap.newKeySet();

    private MissionRouteValidationSetup() {
    }

    static boolean applyIfRequested(MinecraftServer server, Entity aircraft,
                                    FlightPhase phase, FlightProfile profile) {
        String requested = requestedAircraft();
        String actual = BuiltInRegistries.ENTITY_TYPE.getKey(aircraft.getType()).toString();
        if (!"full".equals(System.getProperty(SCENARIO_PROPERTY, "").trim().toLowerCase(Locale.ROOT))
                || (!A6M.equals(requested) && !G4M.equals(requested) && !IL2.equals(requested))
                || !requested.equals(actual)
                || !aircraft.getName().getString().startsWith(VALIDATION_NAME_PREFIX)
                || MissionOrderManager.current(aircraft.getUUID()).isPresent()
                || MissionRouteManager.current(aircraft.getUUID()).isPresent()
                || !eligibleStart(requested, phase, profile)
                || !APPLIED.add(aircraft.getUUID())) {
            return false;
        }
        if (!(aircraft.level() instanceof ServerLevel level)) {
            APPLIED.remove(aircraft.getUUID());
            return false;
        }

        if (A6M.equals(requested)) {
            assignA6mProof(server, level, aircraft);
        } else if (G4M.equals(requested)) {
            assignCompactG4mProof(server, aircraft, phase, profile);
        } else {
            assignCompactIl2Proof(server, aircraft, phase, profile);
        }
        return true;
    }

    static void forget(UUID aircraftId) {
        APPLIED.remove(aircraftId);
    }

    private static boolean eligibleStart(String requested, FlightPhase phase, FlightProfile profile) {
        if (A6M.equals(requested)) {
            return true;
        }
        if (phase != FlightPhase.CRUISE_OUTBOUND || !profile.supportsAutonomousFlight()) {
            return false;
        }
        return G4M.equals(requested) ? profile.isTorpedoBomber() : profile.isAttacker();
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
                "aircraft=" + A6M + ":order_id=" + order.orderId()
                        + ":route_id=" + route.routeId() + ":waypoints=4:terrain_proof=true",
                FlightPhase.STARTUP);
    }

    private static void assignCompactG4mProof(MinecraftServer server, Entity aircraft,
                                              FlightPhase phase, FlightProfile profile) {
        Vec3 origin = aircraft.position();
        Vec3 forward = forward(aircraft);
        Vec3 right = new Vec3(-forward.z, 0.0, forward.x).normalize();
        MissionOrder order = MissionOrder.builder(MissionOrder.Type.HOLD_POSITION)
                .orderId(UUID.randomUUID())
                .build();
        MissionOrderManager.Assignment mission = MissionOrderManager.assign(aircraft.getUUID(), order);
        double leg = 145.0;
        WaypointRoute route = WaypointRoute.start(UUID.randomUUID(), List.of(
                waypoint(origin, forward, right, leg, 0.0, 24.0, 72.0),
                waypoint(origin, forward, right, leg * 1.45, 55.0, 30.0, 76.0),
                waypoint(origin, forward, right, leg * 1.90, -48.0, 26.0, 76.0),
                waypoint(origin, forward, right, leg * 2.35, 0.0, 20.0, 82.0)));
        bind(aircraft, mission, route, "G4M");
        AutopilotLogManager.writeEvent(server, aircraft, "route_validation_assigned",
                "aircraft=" + G4M + ":profile=" + profile.profileId() + ":role=" + profile.role()
                        + ":order_id=" + order.orderId() + ":route_id=" + route.routeId()
                        + ":waypoints=4:compact=true:leg=" + leg + ":terrain_proof=false",
                phase);
    }

    private static void assignCompactIl2Proof(MinecraftServer server, Entity aircraft,
                                              FlightPhase phase, FlightProfile profile) {
        Vec3 origin = aircraft.position();
        Vec3 forward = forward(aircraft);
        Vec3 right = new Vec3(-forward.z, 0.0, forward.x).normalize();
        MissionOrder order = MissionOrder.builder(MissionOrder.Type.HOLD_POSITION)
                .orderId(UUID.randomUUID())
                .build();
        MissionOrderManager.Assignment mission = MissionOrderManager.assign(aircraft.getUUID(), order);
        double leg = 150.0;
        WaypointRoute route = WaypointRoute.start(UUID.randomUUID(), List.of(
                waypoint(origin, forward, right, leg, 0.0, 18.0, 58.0),
                waypoint(origin, forward, right, leg * 1.45, 45.0, 24.0, 62.0),
                waypoint(origin, forward, right, leg * 1.90, -38.0, 20.0, 62.0),
                waypoint(origin, forward, right, leg * 2.35, 0.0, 16.0, 68.0)));
        bind(aircraft, mission, route, "IL-2");
        AutopilotLogManager.writeEvent(server, aircraft, "route_validation_assigned",
                "aircraft=" + IL2 + ":profile=" + profile.profileId() + ":role=" + profile.role()
                        + ":order_id=" + order.orderId() + ":route_id=" + route.routeId()
                        + ":waypoints=4:compact=true:leg=" + leg + ":terrain_proof=false",
                phase);
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

    private static String requestedAircraft() {
        return System.getProperty(AIRCRAFT_PROPERTY, "").trim().toLowerCase(Locale.ROOT);
    }

    private static Vec3 horizontal(Vec3 value) {
        return new Vec3(value.x, 0.0, value.z);
    }
}
