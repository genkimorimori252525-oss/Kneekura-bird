package com.wwdebug.autopilot;

import com.wwdebug.benchmark.ReflectiveAircraft;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.util.Mth;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.Vec3;

/** Shared read-only separation probe used to preserve collision-control priority. */
public final class AirspaceSafetyProbe {
    private static final double SEARCH_HORIZONTAL = 110.0;
    private static final double SEARCH_VERTICAL = 48.0;
    private static final double HARD_CURRENT_SEPARATION = 9.0;
    private static final double HARD_PREDICTED_SEPARATION = 13.0;
    private static final double PREDICTION_TICKS = 60.0;

    private AirspaceSafetyProbe() {
    }

    public static boolean collisionRisk(Entity aircraft) {
        if (!(aircraft.level() instanceof ServerLevel level)) {
            return false;
        }
        AABB area = aircraft.getBoundingBox().inflate(
                SEARCH_HORIZONTAL, SEARCH_VERTICAL, SEARCH_HORIZONTAL);
        return level.getEntities(aircraft, area,
                        other -> !other.isRemoved() && ReflectiveAircraft.isAirplane(other))
                .stream().anyMatch(other -> dangerous(aircraft, other));
    }

    private static boolean dangerous(Entity aircraft, Entity other) {
        Vec3 relativePosition = other.position().subtract(aircraft.position());
        Vec3 relativeVelocity = other.getDeltaMovement().subtract(aircraft.getDeltaMovement());
        double velocitySquared = relativeVelocity.lengthSqr();
        double closestTicks = velocitySquared < 1.0e-8 ? 0.0
                : Mth.clamp(-relativePosition.dot(relativeVelocity) / velocitySquared,
                0.0, PREDICTION_TICKS);
        double current = relativePosition.length();
        double predicted = relativePosition.add(relativeVelocity.scale(closestTicks)).length();
        return current < HARD_CURRENT_SEPARATION
                || (closestTicks > 0.0 && predicted < HARD_PREDICTED_SEPARATION);
    }
}
