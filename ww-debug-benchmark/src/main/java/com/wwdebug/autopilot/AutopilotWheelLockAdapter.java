package com.wwdebug.autopilot;

import net.minecraft.world.entity.Entity;
import net.minecraft.world.phys.Vec3;

/**
 * Final low-speed wheel lock for fighter airframes whose native ground physics settles just above
 * the primary post-physics brake threshold. It is intentionally isolated from airborne control and
 * player control: only an active autonomous BRAKE session on physical ground is eligible.
 */
public final class AutopilotWheelLockAdapter {
    private static final double LOCK_SPEED_BPS = 1.0;

    private AutopilotWheelLockAdapter() {
    }

    public static void apply(Entity aircraft) {
        if (aircraft.level().isClientSide || !aircraft.onGround()) {
            return;
        }
        AutonomousFlightManager.SessionStatus status = AutonomousFlightManager
                .status(aircraft.getUUID())
                .orElse(null);
        if (status == null || status.phase() != FlightPhase.BRAKE) {
            return;
        }

        Vec3 velocity = aircraft.getDeltaMovement();
        if (velocity.horizontalDistance() * 20.0 <= LOCK_SPEED_BPS) {
            aircraft.setDeltaMovement(0.0, Math.min(0.0, velocity.y), 0.0);
        }
    }
}
