package com.wwdebug.autopilot;

import net.minecraft.util.Mth;
import net.minecraft.world.phys.Vec3;

public record FlightControlOutput(
        float x,
        float y,
        float z,
        float engineTarget,
        Vec3 desiredDirection,
        double targetAltitude,
        double targetSpeedBps,
        double headingErrorDeg,
        double altitudeError,
        double speedErrorBps,
        boolean stallRisk,
        boolean terrainRisk,
        String reason,
        String safetyOverride
) {
    public FlightControlOutput {
        x = Mth.clamp(x, -1.0f, 1.0f);
        y = Mth.clamp(y, -1.0f, 1.0f);
        z = Mth.clamp(z, -1.0f, 1.0f);
        engineTarget = Mth.clamp(engineTarget, 0.0f, 1.0f);
        desiredDirection = desiredDirection == null ? Vec3.ZERO : desiredDirection;
        reason = reason == null ? "unspecified" : reason;
        safetyOverride = safetyOverride == null ? "none" : safetyOverride;
    }
}