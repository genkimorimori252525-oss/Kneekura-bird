package com.wwdebug.autopilot;

import com.wwdebug.benchmark.ReflectiveAircraft;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.util.Mth;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.Mob;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.Vec3;

import java.util.Comparator;
import java.util.EnumMap;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Defensive control layered above offensive manoeuvres when another autonomous aircraft is
 * actively tracking this pilot from a dangerous rear-quarter position.
 */
public final class DefensiveAirCombatManager {
    private static final double SEARCH_HORIZONTAL = 190.0;
    private static final double SEARCH_VERTICAL = 96.0;
    private static final double REAR_THREAT_ANGLE_DEG = 72.0;
    private static final double MAX_THREAT_RANGE = 150.0;
    private static final double IMMINENT_FIRE_ANGLE_DEG = 4.5;
    private static final double STALE_THREAT_MIN_RANGE = 96.0;
    private static final double STALE_THREAT_MAX_CLOSURE_BPS = 2.0;
    private static final double STALE_THREAT_MIN_AIM_ERROR_DEG = 11.0;
    private static final Map<UUID, State> STATES = new ConcurrentHashMap<>();

    private DefensiveAirCombatManager() {
    }

    public static void applyControl(Entity aircraft) {
        if (aircraft.level().isClientSide || !(aircraft.level() instanceof ServerLevel level)
                || !ReflectiveAircraft.isAirplane(aircraft)
                || !ReflectiveAircraft.isControllable(aircraft)) {
            clear(aircraft.getUUID());
            return;
        }
        Mob pilot = MobPilotGate.pilotOf(aircraft).orElse(null);
        Optional<AutonomousFlightManager.SessionStatus> status =
                AutonomousFlightManager.status(aircraft.getUUID());
        if (pilot == null
                || status.isEmpty() || !eligiblePhase(status.get().phase())
                || aircraft.onGround() || TerrainAvoidancePlanner.active(aircraft)) {
            clearWithLog(level, aircraft, status.map(AutonomousFlightManager.SessionStatus::phase)
                    .orElse(FlightPhase.ABORTED), "defensive_control_not_eligible");
            return;
        }

        FlightProfile profile = AutopilotProfileRegistry.resolve(level.getServer(), aircraft).orElse(null);
        if (profile == null) {
            clear(aircraft.getUUID());
            return;
        }
        FlightSnapshot snapshot = FlightSnapshot.capture(aircraft);
        Optional<Threat> threat = findThreat(level, aircraft, pilot, snapshot);
        if (threat.isEmpty()) {
            clearWithLog(level, aircraft, status.get().phase(), "no_active_rear_threat");
            return;
        }

        State state = STATES.computeIfAbsent(aircraft.getUUID(), ignored -> new State());
        state.tick();
        DefensiveAirCombatAction selected = selectAction(state, threat.get(), snapshot, profile);
        if (selected != state.action) {
            transition(level, aircraft, status.get().phase(), state, selected, threat.get());
        }
        state.actionTicks++;
        state.threatAircraftUuid = threat.get().attacker().getUUID();

        FlightControlOutput output = controlFor(state, aircraft, snapshot, profile, threat.get());
        ReflectiveAircraft.applyControl(aircraft, -output.x(), output.y(), output.z(),
                output.engineTarget());
        AutopilotLogManager.writeControlAdapter(level.getServer(), aircraft, status.get().phase(),
                description(state, threat.get()), snapshot, baseline(snapshot), output);
        if (state.statusTicks++ % 10 == 0) {
            AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                    "defensive_air_combat_status", description(state, threat.get()),
                    status.get().phase());
        }
    }

    public static boolean active(Entity aircraft) {
        State state = STATES.get(aircraft.getUUID());
        return state != null && state.action != DefensiveAirCombatAction.NONE;
    }

    private static Optional<Threat> findThreat(ServerLevel level, Entity defender,
                                               LivingEntity defenderPilot,
                                               FlightSnapshot snapshot) {
        AABB area = defender.getBoundingBox().inflate(
                SEARCH_HORIZONTAL, SEARCH_VERTICAL, SEARCH_HORIZONTAL);
        return level.getEntities(defender, area,
                        candidate -> ReflectiveAircraft.isAirplane(candidate)
                                && !candidate.isRemoved())
                .stream()
                .map(candidate -> threat(candidate, defender, defenderPilot, snapshot))
                .flatMap(Optional::stream)
                .max(Comparator.comparingDouble(Threat::score));
    }

    private static Optional<Threat> threat(Entity attacker, Entity defender,
                                           LivingEntity defenderPilot,
                                           FlightSnapshot snapshot) {
        Optional<CombatTargetSelector.Solution> selected =
                CombatAwarenessManager.currentSolution(attacker.getUUID());
        if (selected.isEmpty()
                || !selected.get().targetUuid().equals(defenderPilot.getUUID())) {
            return Optional.empty();
        }
        Vec3 fromDefender = attacker.getBoundingBox().getCenter()
                .subtract(defender.getBoundingBox().getCenter());
        double distance = fromDefender.length();
        if (distance < 1.0e-6 || distance > MAX_THREAT_RANGE) {
            return Optional.empty();
        }
        Vec3 directionToAttacker = fromDefender.scale(1.0 / distance);
        double rearDot = snapshot.forward().scale(-1.0).dot(directionToAttacker);
        double rearAngle = Math.toDegrees(Math.acos(Mth.clamp(rearDot, -1.0, 1.0)));
        Optional<AirCombatManeuverManager.AimSolution> attackerAim =
                AirCombatManeuverManager.currentAim(attacker.getUUID(), defenderPilot.getUUID());
        double attackerAimAngle = attackerAim
                .map(AirCombatManeuverManager.AimSolution::angleOffNoseDeg)
                .orElse(selected.get().angleOffNoseDeg());
        boolean imminentFire = distance >= 18.0 && distance <= 135.0
                && attackerAimAngle <= IMMINENT_FIRE_ANGLE_DEG
                && selected.get().lineOfSight();
        double closure = relativeClosureBps(defender, attacker);

        // A distant aircraft that is no longer closing and has lost its firing solution should not
        // hold the defender in an endless break turn merely because it remains just inside the rear
        // hemisphere. Releasing this stale threat lets an energy fighter convert recovered spacing
        // into a counter-intercept, while close or imminent-fire threats remain fully defensive.
        boolean staleRearThreat = !imminentFire
                && distance >= STALE_THREAT_MIN_RANGE
                && closure <= STALE_THREAT_MAX_CLOSURE_BPS
                && attackerAimAngle >= STALE_THREAT_MIN_AIM_ERROR_DEG;
        if (staleRearThreat) {
            return Optional.empty();
        }
        if (rearAngle > REAR_THREAT_ANGLE_DEG && !imminentFire) {
            return Optional.empty();
        }
        double score = (MAX_THREAT_RANGE - distance)
                + Math.max(0.0, REAR_THREAT_ANGLE_DEG - rearAngle) * 1.7
                + Math.max(0.0, closure) * 2.0
                + (imminentFire ? 180.0 : 0.0);
        return Optional.of(new Threat(attacker, distance, rearAngle, attackerAimAngle,
                closure, imminentFire, score));
    }

    private static DefensiveAirCombatAction selectAction(State state, Threat threat,
                                                          FlightSnapshot snapshot,
                                                          FlightProfile profile) {
        if (state.action != DefensiveAirCombatAction.NONE
                && state.actionTicks < state.action.minimumCommitTicks()) {
            return state.action;
        }
        if (threat.imminentFire()
                && state.cooldowns.getOrDefault(DefensiveAirCombatAction.DEFENSIVE_JINK, 0) <= 0) {
            return DefensiveAirCombatAction.DEFENSIVE_JINK;
        }
        boolean lowEnergy = snapshot.speedBps() < profile.cruiseSpeedBps() * 0.82;
        if (("energy_fighter".equalsIgnoreCase(profile.doctrine()) && lowEnergy)
                || (lowEnergy && threat.distance() > 82.0)) {
            return DefensiveAirCombatAction.DIVE_ESCAPE;
        }
        return DefensiveAirCombatAction.DEFENSIVE_BREAK;
    }

    private static FlightControlOutput controlFor(State state, Entity aircraft,
                                                  FlightSnapshot snapshot, FlightProfile profile,
                                                  Threat threat) {
        Vec3 toThreat = horizontal(threat.attacker().position().subtract(aircraft.position()));
        double side = Math.signum(snapshot.right().dot(toThreat));
        if (Math.abs(side) < 0.25) {
            side = aircraft.getUUID().compareTo(threat.attacker().getUUID()) <= 0 ? -1.0 : 1.0;
        }
        return switch (state.action) {
            case DEFENSIVE_BREAK -> {
                Vec3 desired = safeNormalize(snapshot.horizontalForward().scale(0.18)
                        .add(snapshot.right().scale(side * 1.40)), snapshot.horizontalForward());
                yield control(snapshot, desired, snapshot.position().y + 10.0,
                        Math.max(profile.cruiseSpeedBps(), snapshot.speedBps() + 2.0),
                        profile, 1.0f, "defensive_break", "defensive_air_combat_break");
            }
            case DEFENSIVE_JINK -> {
                int segment = state.actionTicks / 6;
                double oscillation = ((segment + aircraft.getUUID().hashCode()) & 1) == 0
                        ? 1.0 : -1.0;
                Vec3 desired = safeNormalize(snapshot.horizontalForward().scale(0.72)
                        .add(snapshot.right().scale(oscillation * 0.82)),
                        snapshot.horizontalForward());
                double altitudeOffset = (segment & 1) == 0 ? 7.0 : -5.0;
                if (snapshot.altitudeAboveGround() < 48.0 && altitudeOffset < 0.0) {
                    altitudeOffset = 8.0;
                }
                yield control(snapshot, desired, snapshot.position().y + altitudeOffset,
                        Math.max(profile.cruiseSpeedBps(), snapshot.speedBps() + 3.0),
                        profile, 1.0f, "defensive_jink", "defensive_air_combat_jink");
            }
            case DIVE_ESCAPE -> {
                Vec3 away = safeNormalize(horizontal(aircraft.position()
                        .subtract(threat.attacker().position())), snapshot.horizontalForward());
                Vec3 desired = safeNormalize(snapshot.horizontalForward().scale(0.62)
                        .add(away.scale(0.74)), snapshot.horizontalForward());
                double targetAltitude = snapshot.altitudeAboveGround() > 65.0
                        ? snapshot.position().y - 18.0 : snapshot.position().y + 2.0;
                yield control(snapshot, desired, targetAltitude,
                        Math.max(profile.cruiseSpeedBps() + 10.0, snapshot.speedBps() + 6.0),
                        profile, 1.0f, "defensive_dive_escape", "defensive_air_combat_dive_escape");
            }
            case NONE -> baseline(snapshot);
        };
    }

    private static FlightControlOutput control(FlightSnapshot snapshot, Vec3 desired,
                                               double targetAltitude, double targetSpeed,
                                               FlightProfile profile, float engineTarget,
                                               String reason, String override) {
        Vec3 horizontalDesired = safeNormalize(horizontal(desired), snapshot.horizontalForward());
        double desiredYaw = Math.toDegrees(Math.atan2(-horizontalDesired.x, horizontalDesired.z));
        double headingError = Mth.wrapDegrees((float) (desiredYaw - snapshot.yawDeg()));
        float x = (float) Mth.clamp(headingError / 34.0, -0.84, 0.84);
        double altitudeError = targetAltitude - snapshot.position().y;
        double desiredPitch = Mth.clamp(-altitudeError * 0.19
                + snapshot.verticalSpeedBps() * 0.30, -12.0, 9.0);
        if (snapshot.speedBps() < profile.stallGuardSpeedBps() * 1.32) {
            desiredPitch = Math.max(desiredPitch, -3.0);
            x *= 0.54f;
            engineTarget = 1.0f;
        }
        float z = (float) Mth.clamp((desiredPitch - snapshot.pitchDeg()) / 17.0,
                -0.80, 0.80);
        return new FlightControlOutput(x, 0.0f, z, engineTarget, horizontalDesired,
                targetAltitude, targetSpeed, headingError, altitudeError,
                targetSpeed - snapshot.speedBps(),
                snapshot.speedBps() < profile.stallGuardSpeedBps(), false, reason, override);
    }

    private static void transition(ServerLevel level, Entity aircraft, FlightPhase phase,
                                   State state, DefensiveAirCombatAction next, Threat threat) {
        DefensiveAirCombatAction previous = state.action;
        if (previous != DefensiveAirCombatAction.NONE) {
            state.cooldowns.put(previous, previous.cooldownTicks());
        }
        state.action = next;
        state.actionTicks = 0;
        state.statusTicks = 0;
        AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                "defensive_air_combat_transition",
                "from=" + previous + ":to=" + next
                        + ":threat_uuid=" + threat.attacker().getUUID()
                        + ":distance=" + round(threat.distance())
                        + ":rear_angle=" + round(threat.rearAngleDeg())
                        + ":attacker_aim_angle=" + round(threat.attackerAimAngleDeg())
                        + ":closure=" + round(threat.closureBps())
                        + ":imminent_fire=" + threat.imminentFire(),
                phase);
    }

    private static String description(State state, Threat threat) {
        return "action=" + state.action
                + ":action_ticks=" + state.actionTicks
                + ":threat_uuid=" + threat.attacker().getUUID()
                + ":distance=" + round(threat.distance())
                + ":rear_angle=" + round(threat.rearAngleDeg())
                + ":attacker_aim_angle=" + round(threat.attackerAimAngleDeg())
                + ":closure=" + round(threat.closureBps())
                + ":imminent_fire=" + threat.imminentFire();
    }

    private static void clearWithLog(ServerLevel level, Entity aircraft,
                                     FlightPhase phase, String reason) {
        State removed = STATES.remove(aircraft.getUUID());
        if (removed != null && removed.action != DefensiveAirCombatAction.NONE) {
            AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                    "defensive_air_combat_clear",
                    reason + ":previous=" + removed.action,
                    phase);
        }
    }

    public static void clear(UUID aircraftUuid) {
        STATES.remove(aircraftUuid);
    }

    private static boolean eligiblePhase(FlightPhase phase) {
        return phase.isAirborneMissionPhase() && !phase.isLandingPhase()
                && phase != FlightPhase.STALL_ENTRY && phase != FlightPhase.STALL_RECOVERY;
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

    private static FlightControlOutput baseline(FlightSnapshot snapshot) {
        float engine = Double.isFinite(snapshot.engineTarget()) ? (float) snapshot.engineTarget() : 0.0f;
        return new FlightControlOutput(0.0f, 0.0f, 0.0f, engine,
                snapshot.horizontalForward(), snapshot.position().y, snapshot.speedBps(),
                0.0, 0.0, 0.0, false, false, "previous_control", "none");
    }

    private static Vec3 horizontal(Vec3 vector) {
        return new Vec3(vector.x, 0.0, vector.z);
    }

    private static Vec3 safeNormalize(Vec3 vector, Vec3 fallback) {
        if (vector.lengthSqr() > 1.0e-8) {
            return vector.normalize();
        }
        return fallback.lengthSqr() > 1.0e-8 ? fallback.normalize() : new Vec3(0.0, 0.0, 1.0);
    }

    private static double round(double value) {
        return Math.rint(value * 100.0) / 100.0;
    }

    private record Threat(Entity attacker, double distance, double rearAngleDeg,
                          double attackerAimAngleDeg, double closureBps,
                          boolean imminentFire, double score) {
    }

    private static final class State {
        private final EnumMap<DefensiveAirCombatAction, Integer> cooldowns =
                new EnumMap<>(DefensiveAirCombatAction.class);
        private DefensiveAirCombatAction action = DefensiveAirCombatAction.NONE;
        private UUID threatAircraftUuid;
        private int actionTicks;
        private int statusTicks;

        private void tick() {
            cooldowns.replaceAll((action, ticks) -> Math.max(0, ticks - 1));
        }
    }
}
