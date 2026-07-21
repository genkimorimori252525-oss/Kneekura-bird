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

import java.util.EnumMap;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Utility-selected fighter manoeuvres layered above ordinary mission flight.
 *
 * <p>The selector deliberately separates available actions from their selection policy. Actions
 * have minimum commitment and cooldowns, while utility is recomputed at a fixed cadence from
 * range, aspect, closure, energy and altitude. This gives later aircraft doctrines a stable place
 * to tune how often each manoeuvre is used without rewriting the flight controller.</p>
 */
public final class AirCombatManeuverManager {
    private static final String AIR_TARGET_TAG = "wwcombat:air_target";
    private static final int EVALUATION_INTERVAL_TICKS = 5;
    private static final double PROJECTILE_SPEED_BPS = 94.0;
    private static final Map<UUID, State> STATES = new ConcurrentHashMap<>();
    private static final Map<UUID, AimSolution> AIM_SOLUTIONS = new ConcurrentHashMap<>();

    private AirCombatManeuverManager() {
    }

    public static void applyControl(Entity aircraft) {
        if (aircraft.level().isClientSide || !(aircraft.level() instanceof ServerLevel level)
                || !ReflectiveAircraft.isAirplane(aircraft) || !ReflectiveAircraft.isControllable(aircraft)) {
            clear(aircraft.getUUID());
            return;
        }
        Entity pilot = aircraft.getControllingPassenger();
        Optional<AutonomousFlightManager.SessionStatus> status =
                AutonomousFlightManager.status(aircraft.getUUID());
        if (pilot instanceof Player || !(pilot instanceof Mob) || status.isEmpty()
                || !eligiblePhase(status.get().phase()) || aircraft.onGround()
                || TerrainAvoidancePlanner.active(aircraft)) {
            clear(aircraft.getUUID());
            return;
        }

        Optional<CombatTargetSelector.Solution> selected =
                CombatAwarenessManager.currentSolution(aircraft.getUUID());
        if (selected.isEmpty()) {
            clearAfterTargetLoss(level, aircraft, status.get().phase(), "no_combat_target");
            return;
        }
        CombatTargetSelector.Solution targetSolution = selected.get();
        Entity selectedEntity = level.getEntity(targetSolution.targetUuid());
        if (!(selectedEntity instanceof LivingEntity livingTarget) || !livingTarget.isAlive()) {
            clearAfterTargetLoss(level, aircraft, status.get().phase(), "combat_target_missing");
            return;
        }
        Entity pursuitTarget = pursuitTarget(livingTarget);
        if (!airTarget(livingTarget, pursuitTarget)) {
            clearAfterTargetLoss(level, aircraft, status.get().phase(), "target_is_not_airborne_combat_target");
            return;
        }

        FlightProfile profile = AutopilotProfileRegistry.resolve(level.getServer(), aircraft).orElse(null);
        if (profile == null) {
            clear(aircraft.getUUID());
            return;
        }
        State state = STATES.computeIfAbsent(aircraft.getUUID(), ignored -> new State());
        state.tick();
        FlightSnapshot snapshot = FlightSnapshot.capture(aircraft);
        CombatContext context = context(aircraft, pursuitTarget, targetSolution, snapshot, profile);
        AIM_SOLUTIONS.put(aircraft.getUUID(), context.aim());

        boolean hasMachineGun = ReflectiveArmament.machineGuns(aircraft).stream()
                .anyMatch(weapon -> weapon.gunnerOffset() == 0);
        int shotsRemaining = ReflectiveArmament.estimatedShotsRemaining(aircraft);
        if (!hasMachineGun) {
            clearAfterTargetLoss(level, aircraft, status.get().phase(), "no_pilot_machine_gun");
            return;
        }

        AirCombatAction chosen = selectAction(state, context, shotsRemaining);
        if (chosen != state.action) {
            transition(level, aircraft, status.get().phase(), state, chosen, context, shotsRemaining);
        }
        state.actionTicks++;
        state.targetUuid = targetSolution.targetUuid();

        FlightControlOutput output = controlFor(state.action, aircraft, pursuitTarget,
                snapshot, profile, context);
        if (output == null) {
            return;
        }
        ReflectiveAircraft.applyControl(aircraft, -output.x(), output.y(), output.z(),
                output.engineTarget());
        AutopilotLogManager.writeControlAdapter(level.getServer(), aircraft, status.get().phase(),
                tacticalDescription(state, context, shotsRemaining), snapshot,
                baseline(snapshot), output);

        if (state.statusTicks++ % 10 == 0) {
            AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                    "air_combat_status", tacticalDescription(state, context, shotsRemaining),
                    status.get().phase());
        }
    }

    public static boolean active(Entity aircraft) {
        State state = STATES.get(aircraft.getUUID());
        return state != null && state.action != AirCombatAction.NONE;
    }

    public static Optional<AimSolution> currentAim(UUID aircraftUuid, UUID targetUuid) {
        AimSolution solution = AIM_SOLUTIONS.get(aircraftUuid);
        return solution != null && solution.targetUuid().equals(targetUuid)
                ? Optional.of(solution) : Optional.empty();
    }

    private static AirCombatAction selectAction(State state, CombatContext context,
                                                int shotsRemaining) {
        if (shotsRemaining <= 0) {
            return AirCombatAction.DISENGAGE;
        }

        boolean emergencyBreak = context.distance() < 18.0
                || (context.distance() < 32.0 && context.closureBps() > 18.0);
        if (emergencyBreak && state.action != AirCombatAction.BREAK_AWAY) {
            return AirCombatAction.BREAK_AWAY;
        }
        if (state.action != AirCombatAction.NONE
                && state.actionTicks < state.action.minimumCommitTicks()) {
            return state.action;
        }
        if (state.action == AirCombatAction.BREAK_AWAY && context.distance() >= 45.0) {
            return AirCombatAction.EXTEND;
        }
        if (firingWindow(context)
                && state.cooldowns.getOrDefault(AirCombatAction.FIRING_PASS, 0) <= 0) {
            return AirCombatAction.FIRING_PASS;
        }
        if (state.action == AirCombatAction.EXTEND && context.distance() > 95.0
                && context.energyRatio() > 0.92) {
            return AirCombatAction.REPOSITION;
        }

        if (state.evaluationTicks > 0 && state.action != AirCombatAction.NONE) {
            return state.action;
        }
        state.evaluationTicks = EVALUATION_INTERVAL_TICKS;

        EnumMap<AirCombatAction, Double> utilities = new EnumMap<>(AirCombatAction.class);
        utilities.put(AirCombatAction.INTERCEPT, interceptUtility(context));
        utilities.put(AirCombatAction.ATTACK_APPROACH, approachUtility(context));
        utilities.put(AirCombatAction.FIRING_PASS, firingUtility(context));
        utilities.put(AirCombatAction.BREAK_AWAY, breakAwayUtility(context));
        utilities.put(AirCombatAction.EXTEND, extendUtility(state, context));
        utilities.put(AirCombatAction.REPOSITION, repositionUtility(context));
        utilities.put(AirCombatAction.DISENGAGE, 0.0);

        AirCombatAction best = AirCombatAction.INTERCEPT;
        double bestUtility = Double.NEGATIVE_INFINITY;
        for (Map.Entry<AirCombatAction, Double> entry : utilities.entrySet()) {
            if (state.cooldowns.getOrDefault(entry.getKey(), 0) > 0) {
                continue;
            }
            if (entry.getValue() > bestUtility) {
                best = entry.getKey();
                bestUtility = entry.getValue();
            }
        }

        double currentUtility = utilities.getOrDefault(state.action, 0.0);
        return state.action == AirCombatAction.NONE || bestUtility >= currentUtility + 12.0
                ? best : state.action;
    }

    private static boolean firingWindow(CombatContext context) {
        return context.lineOfSight()
                && context.distance() >= 24.0
                && context.distance() <= 125.0
                && context.aim().angleOffNoseDeg() <= 7.0
                && context.closureBps() >= -6.0
                && context.closureBps() <= 28.0;
    }

    private static double interceptUtility(CombatContext context) {
        return Mth.clamp((context.distance() - 80.0) * 0.75, 0.0, 85.0)
                + Mth.clamp(context.aim().angleOffNoseDeg() * 0.25, 0.0, 25.0)
                + (context.closureBps() < 2.0 ? 14.0 : 0.0);
    }

    private static double approachUtility(CombatContext context) {
        double range = 75.0 - Math.abs(context.distance() - 82.0) * 0.75;
        double angle = 35.0 - Math.min(35.0, context.aim().angleOffNoseDeg() * 0.65);
        return range + angle + Math.max(0.0, context.altitudeAdvantage() * 0.12);
    }

    private static double firingUtility(CombatContext context) {
        if (!context.lineOfSight() || context.distance() < 20.0 || context.distance() > 130.0) {
            return -100.0;
        }
        return 150.0
                - context.aim().angleOffNoseDeg() * 8.0
                - Math.abs(context.distance() - 70.0) * 0.28
                - Math.max(0.0, context.closureBps() - 12.0) * 1.5;
    }

    private static double breakAwayUtility(CombatContext context) {
        return Mth.clamp((35.0 - context.distance()) * 4.2, 0.0, 120.0)
                + Mth.clamp((context.closureBps() - 12.0) * 3.0, 0.0, 50.0);
    }

    private static double extendUtility(State state, CombatContext context) {
        return state.action == AirCombatAction.BREAK_AWAY
                ? 100.0 + Math.max(0.0, 0.9 - context.energyRatio()) * 50.0 : 4.0;
    }

    private static double repositionUtility(CombatContext context) {
        return Mth.clamp((context.aim().angleOffNoseDeg() - 45.0) * 1.3, 0.0, 95.0)
                + (context.targetAspectDeg() < 55.0 ? 22.0 : 0.0);
    }

    private static FlightControlOutput controlFor(AirCombatAction action, Entity aircraft,
                                                  Entity target, FlightSnapshot snapshot,
                                                  FlightProfile profile, CombatContext context) {
        return switch (action) {
            case INTERCEPT -> control(snapshot, context.aim().direction(),
                    context.aim().aimPoint().y + 8.0,
                    Math.max(profile.cruiseSpeedBps() + 6.0, context.targetSpeedBps() + 5.0),
                    profile, 1.0f, "combat_intercept", "air_combat_intercept");
            case ATTACK_APPROACH -> control(snapshot, context.aim().direction(),
                    context.aim().aimPoint().y + 4.0,
                    Math.max(profile.cruiseSpeedBps() + 2.0, context.targetSpeedBps() + 4.0),
                    profile, 0.75f, "combat_attack_approach", "air_combat_approach");
            case FIRING_PASS -> control(snapshot, context.aim().direction(),
                    context.aim().aimPoint().y,
                    Math.max(profile.cruiseSpeedBps(), context.targetSpeedBps() + 3.0),
                    profile, 0.62f, "combat_firing_pass", "air_combat_firing_pass");
            case BREAK_AWAY -> {
                Vec3 relative = horizontal(target.position().subtract(aircraft.position()));
                double side = Math.signum(snapshot.right().dot(relative));
                if (Math.abs(side) < 0.5) {
                    side = aircraft.getUUID().compareTo(target.getUUID()) <= 0 ? -1.0 : 1.0;
                }
                Vec3 breakDirection = safeNormalize(snapshot.horizontalForward().scale(0.30)
                        .add(snapshot.right().scale(-side * 1.25)), snapshot.horizontalForward());
                yield control(snapshot, breakDirection, snapshot.position().y + 22.0,
                        Math.max(profile.cruiseSpeedBps() + 8.0, snapshot.speedBps() + 5.0),
                        profile, 1.0f, "combat_break_away", "air_combat_break_away");
            }
            case EXTEND -> control(snapshot, snapshot.horizontalForward(),
                    snapshot.position().y + 10.0,
                    Math.max(profile.cruiseSpeedBps() + 9.0, snapshot.speedBps() + 4.0),
                    profile, 1.0f, "combat_extend", "air_combat_extend");
            case REPOSITION -> {
                Vec3 targetForward = safeNormalize(horizontal(target.getLookAngle()),
                        context.aim().direction());
                double side = aircraft.getUUID().compareTo(target.getUUID()) <= 0 ? -1.0 : 1.0;
                Vec3 targetRight = new Vec3(-targetForward.z, 0.0, targetForward.x);
                Vec3 reposition = target.position().subtract(targetForward.scale(72.0))
                        .add(targetRight.scale(side * 38.0)).add(0.0, 14.0, 0.0);
                Vec3 direction = safeNormalize(reposition.subtract(snapshot.position()),
                        snapshot.horizontalForward());
                yield control(snapshot, direction, reposition.y,
                        Math.max(profile.cruiseSpeedBps() + 4.0, context.targetSpeedBps() + 3.0),
                        profile, 0.88f, "combat_reposition", "air_combat_reposition");
            }
            case DISENGAGE -> {
                Vec3 away = safeNormalize(horizontal(aircraft.position().subtract(target.position())),
                        snapshot.horizontalForward());
                yield control(snapshot, away, snapshot.position().y + 28.0,
                        profile.cruiseSpeedBps() + 10.0, profile, 1.0f,
                        "combat_disengage", "air_combat_disengage");
            }
            case NONE -> null;
        };
    }

    private static FlightControlOutput control(FlightSnapshot snapshot, Vec3 desired,
                                               double targetAltitude, double targetSpeed,
                                               FlightProfile profile, float engineTarget,
                                               String reason, String override) {
        Vec3 horizontalDesired = safeNormalize(horizontal(desired), snapshot.horizontalForward());
        double desiredYaw = Math.toDegrees(Math.atan2(-horizontalDesired.x, horizontalDesired.z));
        double headingError = Mth.wrapDegrees((float) (desiredYaw - snapshot.yawDeg()));
        float x = (float) Mth.clamp(headingError / 40.0, -0.76, 0.76);
        double altitudeError = targetAltitude - snapshot.position().y;
        double desiredPitch = Mth.clamp(-altitudeError * 0.18
                + snapshot.verticalSpeedBps() * 0.28, -11.0, 8.0);
        if (snapshot.speedBps() < profile.stallGuardSpeedBps() * 1.30) {
            desiredPitch = Math.max(desiredPitch, -3.5);
            x *= 0.58f;
            engineTarget = Math.max(engineTarget, 0.95f);
        }
        float z = (float) Mth.clamp((desiredPitch - snapshot.pitchDeg()) / 18.0,
                -0.76, 0.76);
        return new FlightControlOutput(x, 0.0f, z, engineTarget, horizontalDesired,
                targetAltitude, targetSpeed, headingError, altitudeError,
                targetSpeed - snapshot.speedBps(),
                snapshot.speedBps() < profile.stallGuardSpeedBps(), false, reason, override);
    }

    private static CombatContext context(Entity aircraft, Entity target,
                                         CombatTargetSelector.Solution targetSolution,
                                         FlightSnapshot snapshot, FlightProfile profile) {
        Vec3 origin = aircraft.getBoundingBox().getCenter();
        Vec3 targetPoint = target.getBoundingBox().getCenter();
        Vec3 relativePosition = targetPoint.subtract(origin);
        Vec3 relativeVelocity = target.getDeltaMovement().subtract(aircraft.getDeltaMovement())
                .scale(20.0);
        double time = interceptTime(relativePosition, relativeVelocity, PROJECTILE_SPEED_BPS);
        Vec3 predicted = targetPoint.add(target.getDeltaMovement().scale(time * 20.0));
        Vec3 direction = safeNormalize(predicted.subtract(origin), targetSolution.direction());
        double angle = Math.toDegrees(Math.acos(Mth.clamp(snapshot.forward().dot(direction), -1.0, 1.0)));
        AimSolution aim = new AimSolution(targetSolution.targetUuid(), predicted, direction,
                predicted.distanceTo(origin), angle, time);

        Vec3 line = safeNormalize(relativePosition, direction);
        double closure = -relativeVelocity.dot(line);
        Vec3 targetForward = safeNormalize(horizontal(target.getLookAngle()),
                safeNormalize(horizontal(target.getDeltaMovement()), direction));
        Vec3 targetToAircraft = safeNormalize(horizontal(aircraft.position().subtract(target.position())),
                targetForward.scale(-1.0));
        double aspect = Math.toDegrees(Math.acos(Mth.clamp(targetForward.dot(targetToAircraft), -1.0, 1.0)));
        double targetSpeed = target.getDeltaMovement().horizontalDistance() * 20.0;
        return new CombatContext(aim, targetSolution.lineOfSight(), relativePosition.length(), closure,
                targetSpeed, snapshot.position().y - target.position().y, aspect,
                snapshot.speedBps() / Math.max(1.0, profile.cruiseSpeedBps()));
    }

    private static double interceptTime(Vec3 relativePosition, Vec3 relativeVelocity,
                                        double projectileSpeed) {
        double a = relativeVelocity.lengthSqr() - projectileSpeed * projectileSpeed;
        double b = 2.0 * relativePosition.dot(relativeVelocity);
        double c = relativePosition.lengthSqr();
        double result = c / Math.max(1.0, projectileSpeed);
        if (Math.abs(a) < 1.0e-8) {
            if (Math.abs(b) > 1.0e-8) {
                double linear = -c / b;
                if (linear > 0.0) {
                    result = linear;
                }
            }
        } else {
            double discriminant = b * b - 4.0 * a * c;
            if (discriminant >= 0.0) {
                double root = Math.sqrt(discriminant);
                double first = (-b - root) / (2.0 * a);
                double second = (-b + root) / (2.0 * a);
                if (first > 0.0 && second > 0.0) {
                    result = Math.min(first, second);
                } else if (first > 0.0) {
                    result = first;
                } else if (second > 0.0) {
                    result = second;
                }
            }
        }
        return Mth.clamp(result, 0.0, 3.0);
    }

    private static void transition(ServerLevel level, Entity aircraft, FlightPhase phase,
                                   State state, AirCombatAction next, CombatContext context,
                                   int shotsRemaining) {
        AirCombatAction previous = state.action;
        if (previous != AirCombatAction.NONE) {
            state.cooldowns.put(previous, previous.cooldownTicks());
        }
        state.action = next;
        state.actionTicks = 0;
        state.statusTicks = 0;
        AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                "air_combat_action_transition",
                "from=" + previous + ":to=" + next
                        + ":distance=" + round(context.distance())
                        + ":lead_angle=" + round(context.aim().angleOffNoseDeg())
                        + ":closure=" + round(context.closureBps())
                        + ":energy_ratio=" + round(context.energyRatio())
                        + ":shots=" + shotsRemaining,
                phase);
    }

    private static String tacticalDescription(State state, CombatContext context,
                                              int shotsRemaining) {
        return "action=" + state.action
                + ":action_ticks=" + state.actionTicks
                + ":target_uuid=" + context.aim().targetUuid()
                + ":distance=" + round(context.distance())
                + ":lead_angle=" + round(context.aim().angleOffNoseDeg())
                + ":lead_seconds=" + round(context.aim().timeSeconds())
                + ":closure=" + round(context.closureBps())
                + ":aspect=" + round(context.targetAspectDeg())
                + ":altitude_advantage=" + round(context.altitudeAdvantage())
                + ":energy_ratio=" + round(context.energyRatio())
                + ":shots=" + shotsRemaining;
    }

    private static FlightControlOutput baseline(FlightSnapshot snapshot) {
        float engine = Double.isFinite(snapshot.engineTarget()) ? (float) snapshot.engineTarget() : 0.0f;
        return new FlightControlOutput(0.0f, 0.0f, 0.0f, engine,
                snapshot.horizontalForward(), snapshot.position().y, snapshot.speedBps(),
                0.0, 0.0, 0.0, false, false, "mission_control", "none");
    }

    private static Entity pursuitTarget(LivingEntity target) {
        Entity vehicle = target.getVehicle();
        return vehicle != null && ReflectiveAircraft.isAirplane(vehicle) ? vehicle : target;
    }

    private static boolean airTarget(LivingEntity selected, Entity pursuitTarget) {
        return ReflectiveAircraft.isAirplane(pursuitTarget)
                || selected.getTags().contains(AIR_TARGET_TAG)
                || pursuitTarget.getTags().contains(AIR_TARGET_TAG);
    }

    private static boolean eligiblePhase(FlightPhase phase) {
        return phase.isAirborneMissionPhase() && !phase.isLandingPhase()
                && phase != FlightPhase.STALL_ENTRY && phase != FlightPhase.STALL_RECOVERY;
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

    private static void clearAfterTargetLoss(ServerLevel level, Entity aircraft,
                                             FlightPhase phase, String reason) {
        State removed = STATES.remove(aircraft.getUUID());
        AIM_SOLUTIONS.remove(aircraft.getUUID());
        if (removed != null && removed.action != AirCombatAction.NONE) {
            AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                    "air_combat_action_clear", reason + ":previous=" + removed.action, phase);
        }
    }

    public static void clear(UUID aircraftUuid) {
        STATES.remove(aircraftUuid);
        AIM_SOLUTIONS.remove(aircraftUuid);
    }

    public record AimSolution(UUID targetUuid, Vec3 aimPoint, Vec3 direction,
                              double distanceBlocks, double angleOffNoseDeg,
                              double timeSeconds) {
    }

    private record CombatContext(AimSolution aim, boolean lineOfSight, double distance,
                                 double closureBps, double targetSpeedBps,
                                 double altitudeAdvantage, double targetAspectDeg,
                                 double energyRatio) {
    }

    private static final class State {
        private final EnumMap<AirCombatAction, Integer> cooldowns =
                new EnumMap<>(AirCombatAction.class);
        private AirCombatAction action = AirCombatAction.NONE;
        private UUID targetUuid;
        private int actionTicks;
        private int evaluationTicks;
        private int statusTicks;

        private void tick() {
            if (evaluationTicks > 0) {
                evaluationTicks--;
            }
            cooldowns.replaceAll((action, ticks) -> Math.max(0, ticks - 1));
        }
    }
}
