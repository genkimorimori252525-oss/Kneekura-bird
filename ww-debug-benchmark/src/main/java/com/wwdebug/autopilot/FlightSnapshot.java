package com.wwdebug.autopilot;

import com.wwdebug.benchmark.ReflectiveAircraft;
import net.minecraft.util.Mth;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.level.ClipContext;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraft.world.phys.HitResult;
import net.minecraft.world.phys.Vec3;

public record FlightSnapshot(
        Vec3 position,
        Vec3 velocity,
        Vec3 forward,
        Vec3 horizontalForward,
        Vec3 right,
        double speedBps,
        double horizontalSpeedBps,
        double verticalSpeedBps,
        double altitudeAboveGround,
        boolean onGround,
        float yawDeg,
        float pitchDeg,
        double movementYawDeg,
        String movementDirection,
        double enginePower
) {
    public static FlightSnapshot capture(Entity aircraft) {
        Vec3 position = aircraft.position();
        Vec3 velocity = aircraft.getDeltaMovement();
        Vec3 forward = aircraft.getLookAngle();
        if (forward.lengthSqr() < 1.0e-8) {
            forward = Vec3.directionFromRotation(aircraft.getXRot(), aircraft.getYRot());
        }
        forward = forward.normalize();

        Vec3 horizontalForward = new Vec3(forward.x, 0.0, forward.z);
        if (horizontalForward.lengthSqr() < 1.0e-8) {
            horizontalForward = Vec3.directionFromRotation(0.0f, aircraft.getYRot());
        }
        horizontalForward = horizontalForward.normalize();
        Vec3 right = new Vec3(-horizontalForward.z, 0.0, horizontalForward.x).normalize();

        double horizontalSpeed = velocity.horizontalDistance() * 20.0;
        double movementYaw = horizontalSpeed > 0.05
                ? Math.toDegrees(Math.atan2(-velocity.x, velocity.z))
                : aircraft.getYRot();

        return new FlightSnapshot(
                position,
                velocity,
                forward,
                horizontalForward,
                right,
                velocity.length() * 20.0,
                horizontalSpeed,
                velocity.y * 20.0,
                altitudeAboveGround(aircraft),
                aircraft.onGround(),
                Mth.wrapDegrees(aircraft.getYRot()),
                Mth.wrapDegrees(aircraft.getXRot()),
                Mth.wrapDegrees((float) movementYaw),
                cardinal(movementYaw),
                ReflectiveAircraft.enginePower(aircraft)
        );
    }

    private static double altitudeAboveGround(Entity aircraft) {
        double bottom = aircraft.level().getMinBuildHeight() + 1.0;
        Vec3 start = aircraft.position();
        Vec3 end = new Vec3(start.x, Math.max(bottom, start.y - 320.0), start.z);
        BlockHitResult hit = aircraft.level().clip(new ClipContext(
                start,
                end,
                ClipContext.Block.COLLIDER,
                ClipContext.Fluid.NONE,
                aircraft
        ));
        if (hit.getType() == HitResult.Type.MISS) {
            return Math.max(0.0, start.y - bottom);
        }
        return Math.max(0.0, start.y - hit.getLocation().y);
    }

    private static String cardinal(double yaw) {
        String[] directions = {"south", "southwest", "west", "northwest", "north", "northeast", "east", "southeast"};
        int index = Mth.floor((Mth.wrapDegrees((float) yaw) + 22.5f) / 45.0f);
        return directions[Math.floorMod(index, directions.length)];
    }
}