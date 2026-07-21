package com.wwdebug.autopilot;

import com.wwdebug.benchmark.ReflectiveAircraft;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.util.Mth;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.Vec3;

import java.util.Comparator;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Makes the reciprocal GameTest opening deterministic without granting either fighter a rear shot.
 *
 * <p>Both aircraft commit to their opposed entry headings until they have crossed and opened the
 * range again. Ordinary offensive and defensive combat resumes immediately afterward. This keeps
 * random entity UUIDs and a one-tick jink choice from changing the entire test geometry before the
 * doctrine controllers have a meaningful chance to act.</p>
 */
public final class MutualDogfightOpeningCommitmentAdapter {
    private static final String SCENARIO_PROPERTY = "wwdebug.flightGameTestScenario";
    private static final String SCENARIO = "dogfight_mutual";
    private static final String TEST_NAME_PREFIX = "AUTOPILOT TEST MUTUAL ";
    private static final String OPPONENT_TAG = "wwcombat:mutual_opponent";
    private static final double SEARCH_HORIZONTAL = 210.0;
    private static final double SEARCH_VERTICAL = 100.0;
    private static final double START_MAX_DISTANCE = 175.0;
    private static final double START_MIN_CLOSURE_BPS = 24.0;
    private static final double START_MAX_OPPOSED_HEADING_DOT = -0.45;
    private static final double CROSSED_DISTANCE = 48.0;
    private static final double RELEASE_DISTANCE = 64.0;
    private static final int MAX_COMMITMENT_TICKS = 120;
    private static final Map<UUID, State> STATES = new ConcurrentHashMap<>();

    private MutualDogfightOpeningCommitmentAdapter() {
    }

    /**
     * @return true while this adapter owns the opening control input
     */
    public static boolean applyControl(Entity aircraft) {
        if (!SCENARIO.equals(System.getProperty(SCENARIO_PROPERTY, "").trim().toLowerCase())
                || aircraft.level().isClientSide
                || !(aircraft.level() instanceof ServerLevel level)
                || !ReflectiveAircraft.isAirplane(aircraft)
                || !ReflectiveAircraft.isControllable(aircraft)
                || !participant(aircraft)) {
            clear(aircraft.getUUID());
            return false;
        }

        Optional<AutonomousFlightManager.SessionStatus> status =
                AutonomousFlightManager.status(aircraft.getUUID());
        FlightProfile profile = AutopilotProfileRegistry.resolve(level.getServer(), aircraft)
                .orElse(null);
        if (status.isEmpty() || profile == null || aircraft.onGround()
                || !eligiblePhase(status.get().phase())
                || TerrainAvoidancePlanner.active(aircraft)
                || AirspaceSafetyProbe.collisionRisk(aircraft)) {
            finish(level, aircraft, status.map(AutonomousFlightManager.SessionStatus::phase)
                    .orElse(FlightPhase.ABORTED), "opening_commitment_not_eligible");
            return false;
        }

        Entity opponent = opponent(level, aircraft).orElse(null);
        State state = STATES.get(aircraft.getUUID());
        if (opponent == null) {
            finish(level, aircraft, status.get().phase(), "opening_opponent_missing");
            return false;
        }

        FlightSnapshot snapshot = FlightSnapshot.capture(aircraft);
        double distance = aircraft.distanceTo(opponent);
        double closure = relativeClosureBps(aircraft, opponent);
        Vec3 opponentForward = safeNormalize(horizontal(opponent.getLookAngle()),
                safeNormalize(horizontal(opponent.getDeltaMovement()),
                        snapshot.horizontalForward().scale(-1.0)));
        double headingDot = snapshot.horizontalForward().dot(opponentForward);

        if (state == null) {
            if (distance > START_MAX_DISTANCE || closure < START_MIN_CLOSURE_BPS
                    || headingDot > START_MAX_OPPOSED_HEADING_DOT) {
                return false;
            }
            state = new State(opponent.getUUID(), snapshot.horizontalForward(),
                    snapshot.position().y, distance);
            STATES.put(aircraft.getUUID(), state);
            clearCombatLayers(aircraft.getUUID());
            AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                    "mutual_opening_commitment_start",
                    description(state, distance, closure, headingDot)
                            + ":reason=opposed_crossing_locked",
                    status.get().phase());
        }

        if (!state.opponentUuid.equals(opponent.getUUID())) {
            finish(level, aircraft, status.get().phase(), "opening_opponent_changed");
            return false;
        }

        state.minimumDistance = Math.min(state.minimumDistance, distance);
        if (distance <= CROSSED_DISTANCE) {
            state.reachedCrossing = true;
        }
        if ((state.reachedCrossing && distance >= RELEASE_DISTANCE && closure < 0.0)
                || state.ticks >= MAX_COMMITMENT_TICKS) {
            finish(level, aircraft, status.get().phase(),
                    state.ticks >= MAX_COMMITMENT_TICKS
                            ? "opening_commitment_timeout" : "opposed_crossing_complete");
            return false;
        }

        clearCombatLayers(aircraft.getUUID());
        applyControl(level, aircraft, snapshot, profile, state, distance, closure, headingDot,
                status.get().phase());
        state.ticks++;
        if (state.statusTicks++ % 10 == 0) {
            AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                    "mutual_opening_commitment_status",
                    description(state, distance, closure, headingDot), status.get().phase());
        }
        return true;
    }

    private static void applyControl(ServerLevel level, Entity aircraft, FlightSnapshot snapshot,
                                     FlightProfile profile, State state, double distance,
                                     double closure, double headingDot, FlightPhase phase) {
        Vec3 desired = state.entryDirection;
        double desiredYaw = Math.toDegrees(Math.atan2(-desired.x, desired.z));
        double headingError = Mth.wrapDegrees((float) (desiredYaw - snapshot.yawDeg()));
        float x = (float) Mth.clamp(headingError / 42.0, -0.42, 0.42);
        double altitudeError = state.entryAltitude - snapshot.position().y;
        double desiredPitch = Mth.clamp(-altitudeError * 0.18
                + snapshot.verticalSpeedBps() * 0.30, -7.0, 7.0);
        float z = (float) Mth.clamp((desiredPitch - snapshot.pitchDeg()) / 19.0,
                -0.48, 0.48);
        double targetSpeed = Math.max(profile.cruiseSpeedBps() + 2.0,
                snapshot.speedBps());
        FlightControlOutput output = new FlightControlOutput(x, 0.0f, z, 0.88f,
                desired, state.entryAltitude, targetSpeed, headingError, altitudeError,
                targetSpeed - snapshot.speedBps(),
                snapshot.speedBps() < profile.stallGuardSpeedBps(), false,
                "mutual_opening_commitment", "mutual_opposed_crossing_lock");
        ReflectiveAircraft.applyControl(aircraft, -output.x(), output.y(), output.z(),
                output.engineTarget());
        AutopilotLogManager.writeControlAdapter(level.getServer(), aircraft, phase,
                description(state, distance, closure, headingDot), snapshot,
                baseline(snapshot), output);
    }

    private static Optional<Entity> opponent(ServerLevel level, Entity aircraft) {
        AABB area = aircraft.getBoundingBox().inflate(
                SEARCH_HORIZONTAL, SEARCH_VERTICAL, SEARCH_HORIZONTAL);
        return level.getEntities(aircraft, area,
                        candidate -> !candidate.isRemoved()
                                && ReflectiveAircraft.isAirplane(candidate)
                                && participant(candidate))
                .stream()
                .min(Comparator.comparingDouble(aircraft::distanceToSqr));
    }

    private static boolean participant(Entity aircraft) {
        return aircraft.getTags().contains(OPPONENT_TAG)
                || aircraft.getName().getString().startsWith(TEST_NAME_PREFIX);
    }

    private static void clearCombatLayers(UUID aircraftUuid) {
        DefensiveAirCombatManager.clear(aircraftUuid);
        AirCombatManeuverManager.clear(aircraftUuid);
        EnergyFighterCounterattackManager.clear(aircraftUuid);
        EnergyFighterCrossingCutAdapter.clear(aircraftUuid);
    }

    private static void finish(ServerLevel level, Entity aircraft, FlightPhase phase,
                               String reason) {
        State removed = STATES.remove(aircraft.getUUID());
        if (removed != null) {
            AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                    "mutual_opening_commitment_end",
                    "ticks=" + removed.ticks
                            + ":minimum_distance=" + round(removed.minimumDistance)
                            + ":reached_crossing=" + removed.reachedCrossing
                            + ":reason=" + reason,
                    phase);
        }
    }

    public static void clear(UUID aircraftUuid) {
        STATES.remove(aircraftUuid);
    }

    private static String description(State state, double distance,
                                      double closure, double headingDot) {
        return "ticks=" + state.ticks
                + ":opponent_uuid=" + state.opponentUuid
                + ":distance=" + round(distance)
                + ":minimum_distance=" + round(state.minimumDistance)
                + ":closure=" + round(closure)
                + ":heading_dot=" + round(headingDot)
                + ":reached_crossing=" + state.reachedCrossing;
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

    private static final class State {
        private final UUID opponentUuid;
        private final Vec3 entryDirection;
        private final double entryAltitude;
        private double minimumDistance;
        private int ticks;
        private int statusTicks;
        private boolean reachedCrossing;

        private State(UUID opponentUuid, Vec3 entryDirection,
                      double entryAltitude, double initialDistance) {
            this.opponentUuid = opponentUuid;
            this.entryDirection = entryDirection;
            this.entryAltitude = entryAltitude;
            this.minimumDistance = initialDistance;
        }
    }
}
