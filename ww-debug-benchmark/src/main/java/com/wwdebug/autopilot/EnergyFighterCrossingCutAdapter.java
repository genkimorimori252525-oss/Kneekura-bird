package com.wwdebug.autopilot;

import com.wwdebug.benchmark.ReflectiveAircraft;
import com.wwdebug.benchmark.ReflectiveArmament;
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
 * Cuts an energy fighter across the opponent's turn circle when a high-yo-yo reaches its broadside
 * crossing. Waiting for the target to enter a narrow forward cone can carry the fighter past the
 * best intercept; this adapter converts the roughly ninety-degree crossing into a short-lead attack
 * setup and then hands control to the normal fixed-gun offensive selector.
 */
public final class EnergyFighterCrossingCutAdapter {
    private static final double START_MIN_RAW_ANGLE = 78.0;
    private static final double START_MAX_RAW_ANGLE = 108.0;
    private static final double START_MIN_DISTANCE = 58.0;
    private static final double START_MAX_DISTANCE = 125.0;
    private static final double START_MIN_CLOSURE_BPS = 2.0;
    private static final double START_MIN_ENERGY_RATIO = 1.03;
    private static final double OFFENSIVE_HANDOFF_RAW_ANGLE = 34.0;
    private static final double ABORT_RAW_ANGLE = 145.0;
    private static final double ABORT_DISTANCE = 175.0;
    private static final int MAX_CUT_TICKS = 150;
    private static final Map<UUID, State> STATES = new ConcurrentHashMap<>();

    private EnergyFighterCrossingCutAdapter() {
    }

    public static boolean applyControl(Entity aircraft) {
        if (aircraft.level().isClientSide || !(aircraft.level() instanceof ServerLevel level)
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
        if (pilotEntity instanceof Player || !(pilotEntity instanceof Mob)
                || status.isEmpty() || !eligiblePhase(status.get().phase())
                || aircraft.onGround() || profile == null
                || !"energy_fighter".equalsIgnoreCase(profile.doctrine())
                || TerrainAvoidancePlanner.active(aircraft)
                || AirspaceSafetyProbe.collisionRisk(aircraft)) {
            finish(level, aircraft, status.map(AutonomousFlightManager.SessionStatus::phase)
                    .orElse(FlightPhase.ABORTED), "crossing_cut_not_eligible");
            return false;
        }

        Target target = target(level, aircraft).orElse(null);
        State state = STATES.get(aircraft.getUUID());
        if (target == null) {
            finish(level, aircraft, status.get().phase(), "crossing_target_lost");
            return false;
        }

        FlightSnapshot snapshot = FlightSnapshot.capture(aircraft);
        Vec3 targetDirection = directionTo(aircraft, target.aircraft(), snapshot.forward());
        double rawAngle = angleDegrees(snapshot.forward(), targetDirection);
        double distance = aircraft.distanceTo(target.aircraft());
        double closure = relativeClosureBps(aircraft, target.aircraft());
        double energyRatio = snapshot.speedBps() / Math.max(1.0, profile.cruiseSpeedBps());

        if (state == null) {
            if (!target.lineOfSight()
                    || rawAngle < START_MIN_RAW_ANGLE || rawAngle > START_MAX_RAW_ANGLE
                    || distance < START_MIN_DISTANCE || distance > START_MAX_DISTANCE
                    || closure < START_MIN_CLOSURE_BPS
                    || energyRatio < START_MIN_ENERGY_RATIO) {
                return false;
            }
            state = new State(target.pilotUuid(),
                    ReflectiveArmament.estimatedShotsRemaining(aircraft));
            STATES.put(aircraft.getUUID(), state);
            DefensiveAirCombatManager.clear(aircraft.getUUID());
            AirCombatManeuverManager.clear(aircraft.getUUID());
            AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                    "energy_crossing_cut_start",
                    description(state, target, rawAngle, distance, closure)
                            + ":energy_ratio=" + round(energyRatio),
                    status.get().phase());
        }

        if (!state.targetPilotUuid.equals(target.pilotUuid())) {
            finish(level, aircraft, status.get().phase(), "crossing_target_changed");
            return false;
        }

        int shotsRemaining = ReflectiveArmament.estimatedShotsRemaining(aircraft);
        if (shotsRemaining < state.initialShotsRemaining) {
            finish(level, aircraft, status.get().phase(), "crossing_cut_weapon_fire_confirmed");
            return false;
        }
        if (state.ticks >= MAX_CUT_TICKS || distance > ABORT_DISTANCE
                || (state.ticks > 20 && rawAngle > ABORT_RAW_ANGLE)) {
            AirCombatManeuverManager.clear(aircraft.getUUID());
            finish(level, aircraft, status.get().phase(), "crossing_cut_geometry_lost");
            return false;
        }

        DefensiveAirCombatManager.clear(aircraft.getUUID());
        if (rawAngle > OFFENSIVE_HANDOFF_RAW_ANGLE) {
            AirCombatManeuverManager.clear(aircraft.getUUID());
            applyCutControl(level, aircraft, target.aircraft(), snapshot, profile,
                    rawAngle, distance, closure, state);
        } else {
            AirCombatManeuverManager.applyControl(aircraft);
        }

        state.ticks++;
        if (state.statusTicks++ % 10 == 0) {
            double leadAngle = AirCombatManeuverManager
                    .currentAim(aircraft.getUUID(), state.targetPilotUuid)
                    .map(AirCombatManeuverManager.AimSolution::angleOffNoseDeg)
                    .map(EnergyFighterCrossingCutAdapter::round).orElse(-1.0);
            AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                    "energy_crossing_cut_status",
                    description(state, target, rawAngle, distance, closure)
                            + ":lead_angle=" + leadAngle
                            + ":offensive_active=" + AirCombatManeuverManager.active(aircraft)
                            + ":shots_remaining=" + shotsRemaining,
                    status.get().phase());
        }
        return true;
    }

    private static void applyCutControl(ServerLevel level, Entity aircraft, Entity target,
                                        FlightSnapshot snapshot, FlightProfile profile,
                                        double rawAngle, double distance, double closure,
                                        State state) {
        Vec3 leadPoint = target.getBoundingBox().getCenter()
                .add(target.getDeltaMovement().scale(5.0));
        Vec3 desired = safeNormalize(leadPoint.subtract(aircraft.getBoundingBox().getCenter()),
                snapshot.forward());
        Vec3 horizontalDesired = safeNormalize(horizontal(desired), snapshot.horizontalForward());
        double desiredYaw = Math.toDegrees(Math.atan2(-horizontalDesired.x, horizontalDesired.z));
        double headingError = Mth.wrapDegrees((float) (desiredYaw - snapshot.yawDeg()));
        float x = (float) Mth.clamp(headingError / 27.0, -0.88, 0.88);

        double targetAltitude = target.position().y + 6.0;
        double altitudeError = targetAltitude - snapshot.position().y;
        double desiredPitch = Mth.clamp(-altitudeError * 0.19
                + snapshot.verticalSpeedBps() * 0.30, -10.0, 8.0);
        if (snapshot.speedBps() < profile.turnSpeedFloorBps() * 0.88) {
            desiredPitch = Math.max(desiredPitch, -2.0);
            x *= 0.58f;
        }
        float z = (float) Mth.clamp((desiredPitch - snapshot.pitchDeg()) / 16.0,
                -0.76, 0.76);
        double targetSpeed = Math.max(profile.cruiseSpeedBps() + 4.0,
                target.getDeltaMovement().horizontalDistance() * 20.0 + 3.0);
        FlightControlOutput output = new FlightControlOutput(x, 0.0f, z, 0.96f,
                horizontalDesired, targetAltitude, targetSpeed, headingError, altitudeError,
                targetSpeed - snapshot.speedBps(),
                snapshot.speedBps() < profile.stallGuardSpeedBps(), false,
                "energy_crossing_cut", "energy_counterattack_crossing_cut");
        ReflectiveAircraft.applyControl(aircraft, -output.x(), output.y(), output.z(),
                output.engineTarget());
        AutopilotLogManager.writeControlAdapter(level.getServer(), aircraft,
                AutonomousFlightManager.status(aircraft.getUUID())
                        .map(AutonomousFlightManager.SessionStatus::phase)
                        .orElse(FlightPhase.ABORTED),
                "ticks=" + state.ticks
                        + ":raw_target_angle=" + round(rawAngle)
                        + ":distance=" + round(distance)
                        + ":closure=" + round(closure),
                snapshot, baseline(snapshot), output);
    }

    private static Optional<Target> target(ServerLevel level, Entity aircraft) {
        Optional<CombatTargetSelector.Solution> selected =
                CombatAwarenessManager.currentSolution(aircraft.getUUID());
        if (selected.isEmpty()) {
            return Optional.empty();
        }
        Entity selectedEntity = level.getEntity(selected.get().targetUuid());
        if (!(selectedEntity instanceof LivingEntity living) || !living.isAlive()) {
            return Optional.empty();
        }
        Entity pursuit = living.getVehicle();
        if (pursuit == null || !ReflectiveAircraft.isAirplane(pursuit)) {
            return Optional.empty();
        }
        return Optional.of(new Target(pursuit, living.getUUID(), selected.get().lineOfSight()));
    }

    private static void finish(ServerLevel level, Entity aircraft, FlightPhase phase,
                               String reason) {
        State removed = STATES.remove(aircraft.getUUID());
        if (removed != null) {
            AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                    "energy_crossing_cut_end",
                    "ticks=" + removed.ticks + ":reason=" + reason,
                    phase);
        }
    }

    public static void clear(UUID aircraftUuid) {
        STATES.remove(aircraftUuid);
    }

    private static String description(State state, Target target, double rawAngle,
                                      double distance, double closure) {
        return "ticks=" + state.ticks
                + ":target_aircraft_uuid=" + target.aircraft().getUUID()
                + ":target_pilot_uuid=" + target.pilotUuid()
                + ":raw_target_angle=" + round(rawAngle)
                + ":distance=" + round(distance)
                + ":closure=" + round(closure);
    }

    private static boolean eligiblePhase(FlightPhase phase) {
        return phase.isAirborneMissionPhase() && !phase.isLandingPhase()
                && phase != FlightPhase.STALL_ENTRY && phase != FlightPhase.STALL_RECOVERY;
    }

    private static Vec3 directionTo(Entity from, Entity to, Vec3 fallback) {
        return safeNormalize(to.getBoundingBox().getCenter()
                .subtract(from.getBoundingBox().getCenter()), fallback);
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

    private record Target(Entity aircraft, UUID pilotUuid, boolean lineOfSight) {
    }

    private static final class State {
        private final UUID targetPilotUuid;
        private final int initialShotsRemaining;
        private int ticks;
        private int statusTicks;

        private State(UUID targetPilotUuid, int initialShotsRemaining) {
            this.targetPilotUuid = targetPilotUuid;
            this.initialShotsRemaining = initialShotsRemaining;
        }
    }
}
