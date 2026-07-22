package com.wwdebug.autopilot;

import com.wwdebug.benchmark.ReflectiveAircraft;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.util.Mth;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.Mob;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.phys.Vec3;

import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Levels an energy fighter after a steep vertical reversal before ordinary doctrine resumes.
 * Terrain, collision, and credible defensive threats remain authoritative.
 */
public final class EnergyFighterPulloutAdapter {
    private static final double ACTIVATION_MAX_VERTICAL_SPEED_BPS = -20.0;
    private static final double ACTIVATION_MIN_PITCH_DEG = 70.0;
    private static final double ACTIVATION_MIN_AGL = 40.0;
    private static final double MIN_REENGAGEMENT_START_AGL = 70.0;
    private static final int MIN_PULL_OUT_TICKS = 10;
    private static final int MAX_PULL_OUT_TICKS = 110;
    private static final double COMPLETE_MAX_ABS_PITCH_DEG = 18.0;
    private static final double COMPLETE_MAX_ABS_ROLL_DEG = 18.0;
    private static final double COMPLETE_MIN_VERTICAL_SPEED_BPS = -6.0;

    private static final Map<UUID, State> STATES = new ConcurrentHashMap<>();

    private EnergyFighterPulloutAdapter() {
    }

    /** @return true when this adapter owns aircraft input for the current tick */
    public static boolean applyControl(Entity aircraft) {
        if (!(aircraft.level() instanceof ServerLevel level) || aircraft.level().isClientSide
                || !ReflectiveAircraft.isAirplane(aircraft)
                || !ReflectiveAircraft.isControllable(aircraft)) {
            clear(aircraft.getUUID());
            return false;
        }

        Entity pilotEntity = aircraft.getControllingPassenger();
        Optional<AutonomousFlightManager.SessionStatus> status =
                AutonomousFlightManager.status(aircraft.getUUID());
        FlightProfile profile = AutopilotProfileRegistry.resolve(level.getServer(), aircraft)
                .orElse(null);
        if (pilotEntity instanceof Player || !(pilotEntity instanceof Mob pilot)
                || status.isEmpty() || profile == null || aircraft.onGround()
                || !eligiblePhase(status.get().phase())
                || !"energy_fighter".equalsIgnoreCase(profile.doctrine())
                || TerrainAvoidancePlanner.active(aircraft)
                || AirspaceSafetyProbe.collisionRisk(aircraft)) {
            finish(level, aircraft, status.map(AutonomousFlightManager.SessionStatus::phase)
                    .orElse(FlightPhase.ABORTED), "not_eligible");
            return false;
        }

        FlightSnapshot snapshot = FlightSnapshot.capture(aircraft);
        State state = STATES.get(aircraft.getUUID());
        Optional<Target> target = target(level, aircraft);
        if (target.isPresent() && credibleThreat(aircraft, target.get(), pilot.getUUID())) {
            finish(level, aircraft, status.get().phase(), "credible_threat_restored");
            return false;
        }

        if (state == null) {
            double pitch = Math.abs(Mth.wrapDegrees((float) snapshot.pitchDeg()));
            if (!AirCombatManeuverManager.active(aircraft)
                    || snapshot.verticalSpeedBps() > ACTIVATION_MAX_VERTICAL_SPEED_BPS
                    || pitch < ACTIVATION_MIN_PITCH_DEG
                    || snapshot.altitudeAboveGround() < ACTIVATION_MIN_AGL) {
                return false;
            }
            state = new State(snapshot.position().y, snapshot.altitudeAboveGround());
            STATES.put(aircraft.getUUID(), state);
            AirCombatManeuverManager.clear(aircraft.getUUID());
            AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                    "energy_post_reversal_pullout_start",
                    "pitch=" + round(snapshot.pitchDeg())
                            + ":roll=" + round(snapshot.rollDeg())
                            + ":vertical_speed_bps=" + round(snapshot.verticalSpeedBps())
                            + ":agl=" + round(snapshot.altitudeAboveGround()),
                    status.get().phase());
        }

        double pitch = Math.abs(Mth.wrapDegrees((float) snapshot.pitchDeg()));
        double roll = Math.abs(Mth.wrapDegrees((float) snapshot.rollDeg()));
        boolean stable = state.ticks >= MIN_PULL_OUT_TICKS
                && pitch <= COMPLETE_MAX_ABS_PITCH_DEG
                && roll <= COMPLETE_MAX_ABS_ROLL_DEG
                && snapshot.verticalSpeedBps() >= COMPLETE_MIN_VERTICAL_SPEED_BPS;
        if (stable) {
            finish(level, aircraft, status.get().phase(), "stable_handoff");
            return false;
        }
        if (state.ticks >= MAX_PULL_OUT_TICKS) {
            finish(level, aircraft, status.get().phase(), "pullout_timeout");
            return false;
        }

        float x = (float) Mth.clamp(-Mth.wrapDegrees((float) snapshot.rollDeg()) / 28.0,
                -0.86, 0.86);
        float z = -0.95f;
        double targetAltitude = snapshot.position().y
                + Math.max(35.0, -snapshot.verticalSpeedBps() * 1.8);
        double targetSpeed = Math.max(profile.turnSpeedFloorBps(), profile.cruiseSpeedBps());
        FlightControlOutput output = new FlightControlOutput(x, 0.0f, z, 1.0f,
                snapshot.horizontalForward(), targetAltitude, targetSpeed,
                0.0, targetAltitude - snapshot.position().y,
                targetSpeed - snapshot.speedBps(),
                snapshot.speedBps() < profile.stallGuardSpeedBps(), false,
                "energy_post_reversal_pullout", "stabilize_before_doctrine");
        ReflectiveAircraft.applyControl(aircraft, -output.x(), output.y(), output.z(),
                output.engineTarget());
        AutopilotLogManager.writeControlAdapter(level.getServer(), aircraft,
                status.get().phase(),
                "ticks=" + state.ticks
                        + ":start_altitude=" + round(state.startAltitude)
                        + ":start_agl=" + round(state.startAgl),
                snapshot, baseline(snapshot), output);

        state.ticks++;
        return true;
    }

    /**
     * Prevents a new vertical re-entry from starting without enough terrain margin. An already
     * active re-entry remains eligible so its own terrain and threat guards can finish cleanly.
     */
    public static boolean reengagementStartSafe(Entity aircraft) {
        if (EnergyFighterReengagementAdapter.active(aircraft)) {
            return true;
        }
        if (!ReflectiveAircraft.isAirplane(aircraft) || aircraft.onGround()) {
            return true;
        }
        double agl = FlightSnapshot.capture(aircraft).altitudeAboveGround();
        return !Double.isFinite(agl) || agl >= MIN_REENGAGEMENT_START_AGL;
    }

    private static Optional<Target> target(ServerLevel level, Entity aircraft) {
        return CombatAwarenessManager.currentSolution(aircraft.getUUID())
                .map(solution -> {
                    Entity pilot = level.getEntity(solution.targetUuid());
                    if (!(pilot instanceof LivingEntity living) || !living.isAlive()) {
                        return null;
                    }
                    Entity targetAircraft = living.getVehicle();
                    return targetAircraft != null && ReflectiveAircraft.isAirplane(targetAircraft)
                            ? new Target(living.getUUID(), targetAircraft, solution.lineOfSight())
                            : null;
                });
    }

    private static boolean credibleThreat(Entity defender, Target target, UUID defenderPilotUuid) {
        if (!target.lineOfSight()) {
            return false;
        }
        Vec3 direction = safeNormalize(target.aircraft().getBoundingBox().getCenter()
                .subtract(defender.getBoundingBox().getCenter()), defender.getLookAngle());
        double rawAngle = angleDegrees(defender.getLookAngle(), direction);
        if (rawAngle <= 58.0) {
            return false;
        }
        double distance = defender.distanceTo(target.aircraft());
        double closure = relativeClosureBps(defender, target.aircraft());
        double attackerAim = AirCombatManeuverManager
                .currentAim(target.aircraft().getUUID(), defenderPilotUuid)
                .map(AirCombatManeuverManager.AimSolution::angleOffNoseDeg)
                .orElse(180.0);
        return (distance <= 82.0 && attackerAim <= 3.2)
                || (distance <= 105.0 && closure >= 8.0 && attackerAim <= 5.0);
    }

    private static double relativeClosureBps(Entity defender, Entity attacker) {
        Vec3 line = attacker.position().subtract(defender.position());
        if (line.lengthSqr() < 1.0e-8) {
            return 0.0;
        }
        return -attacker.getDeltaMovement().subtract(defender.getDeltaMovement())
                .scale(20.0).dot(line.normalize());
    }

    private static double angleDegrees(Vec3 first, Vec3 second) {
        if (first.lengthSqr() < 1.0e-8 || second.lengthSqr() < 1.0e-8) {
            return 0.0;
        }
        return Math.toDegrees(Math.acos(Mth.clamp(
                first.normalize().dot(second.normalize()), -1.0, 1.0)));
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

    private static boolean eligiblePhase(FlightPhase phase) {
        return phase.isAirborneMissionPhase() && !phase.isLandingPhase()
                && phase != FlightPhase.STALL_ENTRY && phase != FlightPhase.STALL_RECOVERY;
    }

    private static void finish(ServerLevel level, Entity aircraft,
                               FlightPhase phase, String reason) {
        State removed = STATES.remove(aircraft.getUUID());
        if (removed != null) {
            FlightSnapshot snapshot = FlightSnapshot.capture(aircraft);
            AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                    "energy_post_reversal_pullout_end",
                    "ticks=" + removed.ticks
                            + ":pitch=" + round(snapshot.pitchDeg())
                            + ":roll=" + round(snapshot.rollDeg())
                            + ":vertical_speed_bps=" + round(snapshot.verticalSpeedBps())
                            + ":agl=" + round(snapshot.altitudeAboveGround())
                            + ":reason=" + reason,
                    phase);
        }
    }

    public static boolean active(Entity aircraft) {
        return STATES.containsKey(aircraft.getUUID());
    }

    public static void clear(UUID aircraftUuid) {
        STATES.remove(aircraftUuid);
    }

    private static double round(double value) {
        return Math.rint(value * 100.0) / 100.0;
    }

    private record Target(UUID pilotUuid, Entity aircraft, boolean lineOfSight) {
    }

    private static final class State {
        private final double startAltitude;
        private final double startAgl;
        private int ticks;

        private State(double startAltitude, double startAgl) {
            this.startAltitude = startAltitude;
            this.startAgl = startAgl;
        }
    }
}
