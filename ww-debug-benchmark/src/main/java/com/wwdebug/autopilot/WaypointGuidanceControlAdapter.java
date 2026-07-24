package com.wwdebug.autopilot;

import net.minecraft.util.Mth;
import net.minecraft.world.phys.Vec3;

import java.util.Objects;

/**
 * Pure conversion from waypoint guidance intent to the existing base-autonomy control envelope.
 *
 * <p>This class never writes aircraft input or requests control authority. The returned output must
 * still pass through the established terrain, collision, combat, and player-control boundaries
 * before it can become the final writer for a tick.</p>
 */
public final class WaypointGuidanceControlAdapter {
    private static final double HEADING_INPUT_DIVISOR = 38.0;
    private static final double PITCH_INPUT_DIVISOR = 18.0;
    private static final double ALTITUDE_ERROR_GAIN = 0.24;
    private static final double VERTICAL_SPEED_DAMPING = 0.32;
    private static final double MAXIMUM_NOSE_UP_DEG = 9.0;
    private static final double MAXIMUM_NOSE_DOWN_DEG = 9.0;

    private WaypointGuidanceControlAdapter() {
    }

    public static FlightControlOutput adapt(
            FlightSnapshot snapshot,
            FlightProfile profile,
            WaypointGuidancePlanner.GuidanceTarget target) {
        Objects.requireNonNull(snapshot, "snapshot");
        Objects.requireNonNull(profile, "profile");
        Objects.requireNonNull(target, "target");

        Vec3 desiredDirection = target.horizontalDirection();
        double desiredYaw = Math.toDegrees(Math.atan2(-desiredDirection.x, desiredDirection.z));
        double headingError = Mth.wrapDegrees((float) (desiredYaw - snapshot.yawDeg()));
        double altitudeError = target.targetAltitude() - snapshot.position().y;
        double speedError = target.targetSpeedBps() - snapshot.speedBps();

        double desiredPitch = Mth.clamp(
                -altitudeError * ALTITUDE_ERROR_GAIN
                        + snapshot.verticalSpeedBps() * VERTICAL_SPEED_DAMPING,
                -MAXIMUM_NOSE_UP_DEG,
                MAXIMUM_NOSE_DOWN_DEG);
        float x = (float) Mth.clamp(
                headingError / HEADING_INPUT_DIVISOR,
                -0.78,
                0.78);
        float z = (float) Mth.clamp(
                (desiredPitch - snapshot.pitchDeg()) / PITCH_INPUT_DIVISOR,
                -0.78,
                0.78);
        float engineTarget = cruiseThrottle(snapshot.speedBps(), target.targetSpeedBps());

        boolean stallRisk = !snapshot.onGround()
                && snapshot.speedBps() < profile.stallGuardSpeedBps();
        boolean terrainRisk = !snapshot.onGround()
                && snapshot.altitudeAboveGround() < 24.0;
        return new FlightControlOutput(
                x,
                0.0f,
                z,
                engineTarget,
                desiredDirection,
                target.targetAltitude(),
                target.targetSpeedBps(),
                headingError,
                altitudeError,
                speedError,
                stallRisk,
                terrainRisk,
                "follow_owned_waypoint_route",
                "none");
    }

    private static float cruiseThrottle(double speedBps, double targetSpeedBps) {
        if (speedBps < targetSpeedBps * 0.93) {
            return 1.0f;
        }
        if (speedBps > targetSpeedBps * 1.08) {
            return 0.35f;
        }
        return 0.68f;
    }
}
