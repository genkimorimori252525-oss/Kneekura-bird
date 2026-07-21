package com.wwdebug.autopilot;

import com.wwdebug.benchmark.ReflectiveAircraft;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.util.Mth;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.phys.Vec3;

import java.util.Optional;

/**
 * Gives a fighter a brief, high-authority final alignment when a valid fixed-gun solution is close
 * but ordinary approach control would carry it through the crossing before reaching the weapon cone.
 *
 * <p>This adapter does not fire and does not relax weapon safety. It only points the aircraft at the
 * existing lead solution while the real target remains in the forward hemisphere. Range, line of
 * sight, the three-degree machine-gun cone, friendly-fire checks, and the raw-target forward check
 * remain enforced by {@link CombatWeaponManager}.</p>
 */
public final class FixedGunFinalAlignmentAdapter {
    private static final double MIN_DISTANCE = 38.0;
    private static final double MAX_DISTANCE = 170.0;
    private static final double MIN_LEAD_ANGLE_DEG = 3.0;
    private static final double TURN_FIGHTER_MAX_LEAD_ANGLE_DEG = 15.0;
    private static final double ENERGY_FIGHTER_MAX_LEAD_ANGLE_DEG = 8.0;
    private static final double MAX_RAW_TARGET_ANGLE_DEG = 35.0;
    private static final double MIN_CLOSURE_BPS = 20.0;

    private FixedGunFinalAlignmentAdapter() {
    }

    /**
     * Applies a final-alignment override after an offensive controller has produced its aim solution.
     *
     * @return true when this adapter replaced the prior offensive control for the current tick
     */
    public static boolean applyControl(Entity aircraft) {
        if (aircraft.level().isClientSide || !(aircraft.level() instanceof ServerLevel level)
                || !ReflectiveAircraft.isAirplane(aircraft)
                || !ReflectiveAircraft.isControllable(aircraft)
                || aircraft.onGround()
                || TerrainAvoidancePlanner.active(aircraft)
                || AirspaceSafetyProbe.collisionRisk(aircraft)
                || DefensiveAirCombatManager.active(aircraft)) {
            return false;
        }

        Optional<AutonomousFlightManager.SessionStatus> status =
                AutonomousFlightManager.status(aircraft.getUUID());
        FlightProfile profile = AutopilotProfileRegistry.resolve(level.getServer(), aircraft)
                .orElse(null);
        if (status.isEmpty() || profile == null) {
            return false;
        }

        Optional<CombatTargetSelector.Solution> selected =
                CombatAwarenessManager.currentSolution(aircraft.getUUID());
        if (selected.isEmpty() || !selected.get().lineOfSight()) {
            return false;
        }
        Entity selectedEntity = level.getEntity(selected.get().targetUuid());
        if (!(selectedEntity instanceof LivingEntity livingTarget) || !livingTarget.isAlive()) {
            return false;
        }
        Entity target = livingTarget.getVehicle();
        if (target == null || !ReflectiveAircraft.isAirplane(target)) {
            target = livingTarget;
        }

        Optional<AirCombatManeuverManager.AimSolution> aim =
                AirCombatManeuverManager.currentAim(aircraft.getUUID(), livingTarget.getUUID());
        if (aim.isEmpty()) {
            return false;
        }

        FlightSnapshot snapshot = FlightSnapshot.capture(aircraft);
        double distance = aim.get().distanceBlocks();
        double leadAngle = aim.get().angleOffNoseDeg();
        Vec3 rawDirection = safeNormalize(target.getBoundingBox().getCenter()
                .subtract(aircraft.getBoundingBox().getCenter()), snapshot.forward());
        double rawAngle = angleDegrees(snapshot.forward(), rawDirection);
        double closure = relativeClosureBps(aircraft, target);
        double maxLeadAngle = "turn_fighter".equalsIgnoreCase(profile.doctrine())
                ? TURN_FIGHTER_MAX_LEAD_ANGLE_DEG : ENERGY_FIGHTER_MAX_LEAD_ANGLE_DEG;
        if (distance < MIN_DISTANCE || distance > MAX_DISTANCE
                || leadAngle < MIN_LEAD_ANGLE_DEG || leadAngle > maxLeadAngle
                || rawAngle > MAX_RAW_TARGET_ANGLE_DEG
                || closure < MIN_CLOSURE_BPS) {
            return false;
        }

        Vec3 desired = aim.get().direction();
        Vec3 horizontalDesired = safeNormalize(horizontal(desired), snapshot.horizontalForward());
        double desiredYaw = Math.toDegrees(Math.atan2(-horizontalDesired.x, horizontalDesired.z));
        double headingError = Mth.wrapDegrees((float) (desiredYaw - snapshot.yawDeg()));
        float x = (float) Mth.clamp(headingError / 10.0, -0.92, 0.92);

        double targetAltitude = aim.get().aimPoint().y;
        double altitudeError = targetAltitude - snapshot.position().y;
        double desiredPitch = Mth.clamp(-altitudeError * 0.24
                + snapshot.verticalSpeedBps() * 0.25, -12.0, 10.0);
        if (snapshot.speedBps() < profile.stallGuardSpeedBps() * 1.30) {
            desiredPitch = Math.max(desiredPitch, -2.5);
            x *= 0.62f;
        }
        float z = (float) Mth.clamp((desiredPitch - snapshot.pitchDeg()) / 12.0,
                -0.86, 0.86);
        double targetSpeed = Math.max(profile.stallGuardSpeedBps() * 1.65,
                target.getDeltaMovement().horizontalDistance() * 20.0);
        float engineTarget = closure > 45.0 ? 0.18f : 0.38f;

        FlightControlOutput output = new FlightControlOutput(x, 0.0f, z, engineTarget,
                horizontalDesired, targetAltitude, targetSpeed, headingError, altitudeError,
                targetSpeed - snapshot.speedBps(),
                snapshot.speedBps() < profile.stallGuardSpeedBps(), false,
                "fixed_gun_final_alignment", "fixed_gun_final_alignment");
        ReflectiveAircraft.applyControl(aircraft, -output.x(), output.y(), output.z(),
                output.engineTarget());
        String description = "doctrine=" + profile.doctrine()
                + ":distance=" + round(distance)
                + ":lead_angle=" + round(leadAngle)
                + ":max_lead_angle=" + round(maxLeadAngle)
                + ":raw_target_angle=" + round(rawAngle)
                + ":closure=" + round(closure);
        AutopilotLogManager.writeControlAdapter(level.getServer(), aircraft, status.get().phase(),
                description, snapshot, baseline(snapshot), output);
        AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                "fixed_gun_final_alignment", description, status.get().phase());
        return true;
    }

    private static double relativeClosureBps(Entity defender, Entity attacker) {
        Vec3 line = attacker.position().subtract(defender.position());
        if (line.lengthSqr() < 1.0e-8) {
            return 0.0;
        }
        Vec3 relativeVelocity = attacker.getDeltaMovement().subtract(defender.getDeltaMovement())
                .scale(20.0);
        return -relativeVelocity.dot(line.normalize());
    }

    private static double angleDegrees(Vec3 first, Vec3 second) {
        if (first.lengthSqr() < 1.0e-8 || second.lengthSqr() < 1.0e-8) {
            return 0.0;
        }
        return Math.toDegrees(Math.acos(Mth.clamp(
                first.normalize().dot(second.normalize()), -1.0, 1.0)));
    }

    private static Vec3 horizontal(Vec3 vector) {
        return new Vec3(vector.x, 0.0, vector.z);
    }

    private static Vec3 safeNormalize(Vec3 vector, Vec3 fallback) {
        if (vector.lengthSqr() > 1.0e-8) {
            return vector.normalize();
        }
        return fallback.lengthSqr() > 1.0e-8
                ? fallback.normalize() : new Vec3(0.0, 0.0, 1.0);
    }

    private static FlightControlOutput baseline(FlightSnapshot snapshot) {
        float engine = Double.isFinite(snapshot.engineTarget())
                ? (float) snapshot.engineTarget() : 0.0f;
        return new FlightControlOutput(0.0f, 0.0f, 0.0f, engine,
                snapshot.horizontalForward(), snapshot.position().y, snapshot.speedBps(),
                0.0, 0.0, 0.0, false, false, "previous_control", "none");
    }

    private static double round(double value) {
        return Math.rint(value * 100.0) / 100.0;
    }
}
