package com.wwdebug.autopilot;

import net.minecraft.world.phys.Vec3;

import java.util.List;
import java.util.Objects;
import java.util.UUID;

/**
 * Pure role/profile-driven geometry for compact noncombat route qualification.
 *
 * <p>This class deliberately has no access to aircraft entities, mission managers, control input,
 * terrain state, or weapons. It only turns a measured {@link FlightProfile}, origin, and heading
 * into an immutable four-waypoint route. Live validation may adopt it in a later focused change.</p>
 */
public final class ProfileDrivenRoutePlan {
    private static final double EPSILON = 1.0e-8;

    private ProfileDrivenRoutePlan() {
    }

    public static Plan plan(FlightProfile profile) {
        Objects.requireNonNull(profile, "profile");
        if (!profile.supportsAutonomousFlight()) {
            throw new IllegalArgumentException("unsupported autonomous-flight role " + profile.role());
        }

        if (profile.isFighter()) {
            return new Plan("fighter", clamp(profile.cruiseSpeedBps() * 3.2, 130.0, 180.0),
                    0.30, 18.0, 58.0);
        }
        if (profile.isAttacker()) {
            return new Plan("attacker", clamp(profile.cruiseSpeedBps() * 3.4, 130.0, 175.0),
                    0.28, 18.0, 62.0);
        }
        if (profile.isTorpedoBomber()) {
            return new Plan("torpedo_bomber", clamp(profile.cruiseSpeedBps() * 3.1, 110.0, 145.0),
                    0.24, 24.0, 76.0);
        }
        return new Plan("bomber", clamp(profile.cruiseSpeedBps() * 3.1, 110.0, 145.0),
                0.16, 16.0, 82.0);
    }

    public static WaypointRoute build(UUID routeId, Vec3 origin, Vec3 heading,
                                      FlightProfile profile) {
        Objects.requireNonNull(routeId, "routeId");
        requireFinite(origin, "origin");
        requireFinite(heading, "heading");

        Vec3 forward = new Vec3(heading.x, 0.0, heading.z);
        if (forward.lengthSqr() < EPSILON) {
            throw new IllegalArgumentException("heading must have a finite horizontal component");
        }
        forward = forward.normalize();
        Vec3 right = new Vec3(-forward.z, 0.0, forward.x);
        Plan plan = plan(profile);
        double leg = plan.legBlocks();
        double lateral = leg * plan.lateralRatio();

        return WaypointRoute.start(routeId, List.of(
                waypoint(origin, forward, right, leg, 0.0,
                        plan.relativeAltitudeBlocks(), plan.arrivalRadiusBlocks()),
                waypoint(origin, forward, right, leg * 1.45, lateral,
                        plan.relativeAltitudeBlocks() + 6.0, plan.arrivalRadiusBlocks()),
                waypoint(origin, forward, right, leg * 1.90, -lateral * 0.85,
                        plan.relativeAltitudeBlocks() + 3.0, plan.arrivalRadiusBlocks()),
                waypoint(origin, forward, right, leg * 2.35, 0.0,
                        Math.max(12.0, plan.relativeAltitudeBlocks() - 2.0),
                        plan.arrivalRadiusBlocks() + 6.0)));
    }

    private static WaypointRoute.Waypoint waypoint(Vec3 origin, Vec3 forward, Vec3 right,
                                                     double longitudinal, double lateral,
                                                     double altitude, double radius) {
        Vec3 position = origin.add(forward.scale(longitudinal))
                .add(right.scale(lateral)).add(0.0, altitude, 0.0);
        return new WaypointRoute.Waypoint(position, radius);
    }

    private static void requireFinite(Vec3 value, String name) {
        Objects.requireNonNull(value, name);
        if (!Double.isFinite(value.x) || !Double.isFinite(value.y) || !Double.isFinite(value.z)) {
            throw new IllegalArgumentException(name + " must be finite");
        }
    }

    private static double clamp(double value, double minimum, double maximum) {
        return Math.max(minimum, Math.min(maximum, value));
    }

    public record Plan(String role, double legBlocks, double lateralRatio,
                       double relativeAltitudeBlocks, double arrivalRadiusBlocks) {
        public Plan {
            Objects.requireNonNull(role, "role");
            if (!Double.isFinite(legBlocks) || legBlocks <= 0.0
                    || !Double.isFinite(lateralRatio) || lateralRatio < 0.0
                    || !Double.isFinite(relativeAltitudeBlocks)
                    || !Double.isFinite(arrivalRadiusBlocks) || arrivalRadiusBlocks <= 0.0) {
                throw new IllegalArgumentException("route plan values must be finite and valid");
            }
        }
    }
}
