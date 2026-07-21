package com.wwdebug.autopilot;

import com.wwdebug.benchmark.ReflectiveAircraft;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.util.Mth;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.phys.Vec3;

import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/** Preserves a short forward alignment window before defensive control replaces it. */
public final class EnergyFighterForwardAlignmentAdapter {
    private static final double MIN_DISTANCE = 24.0;
    private static final double MAX_DISTANCE = 90.0;
    private static final double MAX_RAW_ANGLE = 20.0;
    private static final double MIN_CLOSURE = 15.0;
    private static final double MAX_CLOSURE = 80.0;
    private static final double MAX_LEAD_ANGLE = 12.0;
    private static final int MAX_TICKS = 8;
    private static final int COOLDOWN_TICKS = 80;

    private static final Map<UUID, State> STATES = new ConcurrentHashMap<>();
    private static final Map<UUID, Integer> COOLDOWNS = new ConcurrentHashMap<>();

    private EnergyFighterForwardAlignmentAdapter() {
    }

    public static boolean applyControl(Entity aircraft) {
        tickCooldown(aircraft.getUUID());
        if (!(aircraft.level() instanceof ServerLevel level) || aircraft.level().isClientSide
                || !ReflectiveAircraft.isAirplane(aircraft)
                || !ReflectiveAircraft.isControllable(aircraft)
                || aircraft.onGround()
                || TerrainAvoidancePlanner.active(aircraft)
                || AirspaceSafetyProbe.collisionRisk(aircraft)) {
            STATES.remove(aircraft.getUUID());
            return false;
        }

        Optional<AutonomousFlightManager.SessionStatus> status =
                AutonomousFlightManager.status(aircraft.getUUID());
        FlightProfile profile = AutopilotProfileRegistry.resolve(level.getServer(), aircraft)
                .orElse(null);
        if (status.isEmpty() || profile == null
                || !"energy_fighter".equalsIgnoreCase(profile.doctrine())) {
            STATES.remove(aircraft.getUUID());
            return false;
        }

        Target target = target(level, aircraft).orElse(null);
        State state = STATES.get(aircraft.getUUID());
        if (target == null) {
            finish(aircraft.getUUID());
            return false;
        }

        FlightSnapshot snapshot = FlightSnapshot.capture(aircraft);
        Vec3 rawDirection = normalize(target.aircraft().getBoundingBox().getCenter()
                .subtract(aircraft.getBoundingBox().getCenter()), snapshot.forward());
        double rawAngle = angle(snapshot.forward(), rawDirection);
        double distance = aircraft.distanceTo(target.aircraft());
        double closure = closure(aircraft, target.aircraft());

        if (state == null) {
            if (COOLDOWNS.containsKey(aircraft.getUUID())
                    || DefensiveAirCombatManager.active(aircraft)
                    || !target.lineOfSight()
                    || distance < MIN_DISTANCE || distance > MAX_DISTANCE
                    || rawAngle > MAX_RAW_ANGLE
                    || closure < MIN_CLOSURE || closure > MAX_CLOSURE) {
                return false;
            }
            AirCombatManeuverManager.applyControl(aircraft);
            Optional<AirCombatManeuverManager.AimSolution> aim =
                    AirCombatManeuverManager.currentAim(aircraft.getUUID(), target.pilotUuid());
            if (aim.isEmpty() || aim.get().angleOffNoseDeg() > MAX_LEAD_ANGLE) {
                return false;
            }
            state = new State(target.pilotUuid());
            STATES.put(aircraft.getUUID(), state);
            AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                    "energy_forward_alignment_start",
                    description(state, distance, rawAngle, closure,
                            aim.get().angleOffNoseDeg()), status.get().phase());
        } else {
            if (!state.targetPilotUuid.equals(target.pilotUuid())
                    || state.ticks >= MAX_TICKS
                    || distance < MIN_DISTANCE || distance > MAX_DISTANCE
                    || rawAngle > MAX_RAW_ANGLE
                    || closure < MIN_CLOSURE || closure > MAX_CLOSURE) {
                finish(aircraft.getUUID());
                return false;
            }
            AirCombatManeuverManager.applyControl(aircraft);
        }

        Optional<AirCombatManeuverManager.AimSolution> aim =
                AirCombatManeuverManager.currentAim(aircraft.getUUID(), target.pilotUuid());
        if (aim.isEmpty() || aim.get().angleOffNoseDeg() > MAX_LEAD_ANGLE) {
            finish(aircraft.getUUID());
            return false;
        }

        if (aim.get().angleOffNoseDeg() > 3.0) {
            applyAlignment(level, aircraft, snapshot, profile, aim.get(),
                    rawAngle, closure, state, status.get().phase());
        }
        state.ticks++;
        if (state.ticks == 1 || state.ticks % 2 == 0) {
            AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                    "energy_forward_alignment_status",
                    description(state, distance, rawAngle, closure,
                            aim.get().angleOffNoseDeg()), status.get().phase());
        }
        return true;
    }

    private static void applyAlignment(ServerLevel level, Entity aircraft,
                                       FlightSnapshot snapshot, FlightProfile profile,
                                       AirCombatManeuverManager.AimSolution aim,
                                       double rawAngle, double closure,
                                       State state, FlightPhase phase) {
        Vec3 horizontalDesired = normalize(horizontal(aim.direction()),
                snapshot.horizontalForward());
        double desiredYaw = Math.toDegrees(Math.atan2(-horizontalDesired.x, horizontalDesired.z));
        double headingError = Mth.wrapDegrees((float) (desiredYaw - snapshot.yawDeg()));
        float x = (float) Mth.clamp(headingError / 8.0, -0.95, 0.95);

        double targetAltitude = aim.aimPoint().y;
        double altitudeError = targetAltitude - snapshot.position().y;
        double desiredPitch = Mth.clamp(-altitudeError * 0.28
                + snapshot.verticalSpeedBps() * 0.25, -12.0, 10.0);
        if (snapshot.speedBps() < profile.stallGuardSpeedBps() * 1.30) {
            desiredPitch = Math.max(desiredPitch, -2.0);
            x *= 0.65f;
        }
        float z = (float) Mth.clamp((desiredPitch - snapshot.pitchDeg()) / 11.0,
                -0.88, 0.88);
        double targetSpeed = Math.max(profile.stallGuardSpeedBps() * 1.70,
                snapshot.speedBps() - 4.0);
        float engineTarget = closure > 40.0 ? 0.16f : 0.32f;

        FlightControlOutput output = new FlightControlOutput(x, 0.0f, z, engineTarget,
                horizontalDesired, targetAltitude, targetSpeed, headingError, altitudeError,
                targetSpeed - snapshot.speedBps(),
                snapshot.speedBps() < profile.stallGuardSpeedBps(), false,
                "energy_forward_alignment", "preserve_forward_solution");
        ReflectiveAircraft.applyControl(aircraft, -output.x(), output.y(), output.z(),
                output.engineTarget());
        AutopilotLogManager.writeControlAdapter(level.getServer(), aircraft, phase,
                "alignment_ticks=" + state.ticks
                        + ":lead_angle=" + round(aim.angleOffNoseDeg())
                        + ":raw_target_angle=" + round(rawAngle)
                        + ":closure=" + round(closure),
                snapshot, baseline(snapshot), output);
    }

    private static Optional<Target> target(ServerLevel level, Entity aircraft) {
        return CombatAwarenessManager.currentSolution(aircraft.getUUID())
                .map(solution -> {
                    Entity entity = level.getEntity(solution.targetUuid());
                    if (!(entity instanceof LivingEntity pilot) || !pilot.isAlive()) {
                        return null;
                    }
                    Entity targetAircraft = pilot.getVehicle();
                    return targetAircraft != null && ReflectiveAircraft.isAirplane(targetAircraft)
                            ? new Target(pilot.getUUID(), targetAircraft, solution.lineOfSight())
                            : null;
                });
    }

    private static void finish(UUID aircraftUuid) {
        if (STATES.remove(aircraftUuid) != null) {
            COOLDOWNS.put(aircraftUuid, COOLDOWN_TICKS);
        }
    }

    private static void tickCooldown(UUID aircraftUuid) {
        COOLDOWNS.computeIfPresent(aircraftUuid, (ignored, ticks) ->
                ticks <= 1 ? null : ticks - 1);
    }

    public static void clear(UUID aircraftUuid) {
        STATES.remove(aircraftUuid);
        COOLDOWNS.remove(aircraftUuid);
    }

    private static String description(State state, double distance, double rawAngle,
                                      double closure, double leadAngle) {
        return "alignment_ticks=" + state.ticks
                + ":distance=" + round(distance)
                + ":raw_target_angle=" + round(rawAngle)
                + ":lead_angle=" + round(leadAngle)
                + ":closure=" + round(closure);
    }

    private static double closure(Entity defender, Entity attacker) {
        Vec3 line = attacker.position().subtract(defender.position());
        if (line.lengthSqr() < 1.0e-8) {
            return 0.0;
        }
        return -attacker.getDeltaMovement().subtract(defender.getDeltaMovement())
                .scale(20.0).dot(line.normalize());
    }

    private static double angle(Vec3 first, Vec3 second) {
        if (first.lengthSqr() < 1.0e-8 || second.lengthSqr() < 1.0e-8) {
            return 0.0;
        }
        return Math.toDegrees(Math.acos(Mth.clamp(
                first.normalize().dot(second.normalize()), -1.0, 1.0)));
    }

    private static Vec3 horizontal(Vec3 vector) {
        return new Vec3(vector.x, 0.0, vector.z);
    }

    private static Vec3 normalize(Vec3 vector, Vec3 fallback) {
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

    private record Target(UUID pilotUuid, Entity aircraft, boolean lineOfSight) {
    }

    private static final class State {
        private final UUID targetPilotUuid;
        private int ticks;

        private State(UUID targetPilotUuid) {
            this.targetPilotUuid = targetPilotUuid;
        }
    }
}
