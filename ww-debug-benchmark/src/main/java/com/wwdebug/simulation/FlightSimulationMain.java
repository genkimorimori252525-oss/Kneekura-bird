package com.wwdebug.simulation;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;

import java.io.IOException;
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.time.Instant;
import java.util.ArrayList;
import java.util.EnumSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * Fast deterministic pre-flight simulator.
 *
 * <p>This deliberately does not claim to reproduce Immersive Aircraft physics. It exercises the
 * complete mission contract, measured speed thresholds, state reachability, safety overrides and
 * landing geometry before the slower Forge GameTest server is started.</p>
 */
public final class FlightSimulationMain {
    private static final Gson GSON = new GsonBuilder().setPrettyPrinting().create();
    private static final int MAX_TICKS = 16_000;
    private static final double SAFE_ALTITUDE = 80.0;
    private static final double CRUISE_ALTITUDE = 100.0;
    private static final double STALL_TEST_ALTITUDE = 125.0;

    private FlightSimulationMain() {
    }

    public static void main(String[] args) throws Exception {
        Arguments arguments = Arguments.parse(args);
        ProfileSet profileSet = loadProfiles(arguments.profilePath());
        List<Map<String, Object>> results = new ArrayList<>();

        for (Profile profile : profileSet.profiles()) {
            if (!"fighter".equalsIgnoreCase(profile.role())) {
                continue;
            }
            for (Scenario scenario : Scenario.values()) {
                results.add(run(profile, scenario).toMap());
            }
        }

        long failed = results.stream().filter(row -> !Boolean.TRUE.equals(row.get("passed"))).count();
        Map<String, Object> report = new LinkedHashMap<>();
        report.put("generated_at_utc", Instant.now().toString());
        report.put("profile_source", profileSet.source());
        report.put("profile_count", profileSet.profiles().size());
        report.put("scenario_count", Scenario.values().length);
        report.put("result_count", results.size());
        report.put("failed", failed);
        report.put("results", results);

        Path output = arguments.outputPath();
        Files.createDirectories(output.toAbsolutePath().getParent());
        Files.writeString(output, GSON.toJson(report), StandardCharsets.UTF_8);
        System.out.println("Autonomous-flight simulation: " + (results.size() - failed) + "/" + results.size()
                + " passed; report=" + output.toAbsolutePath());

        if (failed > 0) {
            throw new IllegalStateException(failed + " deterministic autonomous-flight scenarios failed");
        }
    }

    private static SimulationResult run(Profile profile, Scenario scenario) {
        State state = new State();
        EnumSet<Phase> visited = EnumSet.of(Phase.STARTUP);
        double minimumAirborneAltitude = Double.POSITIVE_INFINITY;
        double maximumAltitude = 0.0;
        int longestStallRisk = 0;
        int currentStallRisk = 0;
        String reason = "mission_started";

        while (state.tick < MAX_TICKS && !state.phase.terminal()) {
            state.tick++;
            state.phaseTick++;

            Plan plan = plan(profile, state);
            integrate(profile, scenario, state, plan);

            if (!state.onGround) {
                minimumAirborneAltitude = Math.min(minimumAirborneAltitude, state.altitude);
                maximumAltitude = Math.max(maximumAltitude, state.altitude);
            }
            if (!state.onGround && state.speed < profile.stallGuard() * 0.95
                    && state.phase != Phase.STALL_ENTRY && state.phase != Phase.STALL_RECOVERY) {
                currentStallRisk++;
                longestStallRisk = Math.max(longestStallRisk, currentStallRisk);
            } else {
                currentStallRisk = 0;
            }

            Transition transition = transition(profile, state);
            if (transition != null) {
                reason = transition.reason();
                state.enter(transition.next());
                visited.add(state.phase);
            }
        }

        if (!state.phase.terminal()) {
            reason = "simulation_timeout";
            state.phase = Phase.ABORTED;
        }

        List<String> missing = new ArrayList<>();
        for (Phase required : List.of(
                Phase.TAKEOFF_ROLL, Phase.ROTATE, Phase.CLIMB, Phase.CRUISE_OUTBOUND,
                Phase.TURN_LEFT, Phase.CRUISE_CROSS, Phase.TURN_RIGHT, Phase.STALL_SETUP,
                Phase.STALL_ENTRY, Phase.STALL_RECOVERY, Phase.RETURN_TO_PATTERN,
                Phase.DOWNWIND, Phase.BASE, Phase.FINAL, Phase.FLARE,
                Phase.TOUCHDOWN, Phase.BRAKE, Phase.PARKED)) {
            if (!visited.contains(required)) {
                missing.add(required.name());
            }
        }

        boolean passed = state.phase == Phase.PARKED
                && missing.isEmpty()
                && longestStallRisk <= 80
                && maximumAltitude >= SAFE_ALTITUDE - 5.0
                && state.speed < 0.25;
        if (!passed && state.phase == Phase.PARKED && !missing.isEmpty()) {
            reason = "missing_required_phases";
        }

        return new SimulationResult(profile.id(), profile.doctrine(), scenario.id,
                passed, state.phase.name(), reason, state.tick, state.x, state.z,
                state.speed, state.altitude,
                Double.isFinite(minimumAirborneAltitude) ? minimumAirborneAltitude : 0.0,
                maximumAltitude, longestStallRisk, missing);
    }

    private static Plan plan(Profile profile, State state) {
        double targetSpeed = profile.cruise();
        double targetAltitude = CRUISE_ALTITUDE;
        double throttle = 0.68;
        double desiredHeading = state.heading;
        double desiredPitch = 0.0;
        boolean brake = false;

        switch (state.phase) {
            case STARTUP -> {
                targetSpeed = 0.0;
                targetAltitude = 0.0;
                throttle = 1.0;
                desiredHeading = 0.0;
                brake = true;
            }
            case TAKEOFF_ROLL -> {
                targetSpeed = profile.rotateSpeed();
                targetAltitude = 0.0;
                throttle = 1.0;
                desiredHeading = 0.0;
            }
            case ROTATE -> {
                targetSpeed = profile.climb();
                targetAltitude = 20.0;
                throttle = 1.0;
                desiredHeading = 0.0;
                desiredPitch = -10.0;
            }
            case CLIMB -> {
                targetSpeed = profile.climb();
                targetAltitude = SAFE_ALTITUDE;
                throttle = 1.0;
                desiredHeading = 0.0;
                desiredPitch = altitudePitch(state, targetAltitude, 11.0, 6.0);
                if (state.speed < profile.climb() * 0.90) {
                    desiredPitch = Math.max(desiredPitch, -5.0);
                }
            }
            case CRUISE_OUTBOUND -> {
                targetSpeed = profile.cruise();
                targetAltitude = CRUISE_ALTITUDE;
                desiredHeading = 0.0;
                throttle = cruiseThrottle(state.speed, targetSpeed);
                desiredPitch = altitudePitch(state, targetAltitude, 8.0, 7.0);
            }
            case TURN_LEFT, TURN_RIGHT -> {
                targetSpeed = Math.max(profile.turnFloor(), profile.cruise() * 0.82);
                targetAltitude = CRUISE_ALTITUDE;
                desiredHeading = state.phaseTargetHeading;
                throttle = cruiseThrottle(state.speed, targetSpeed);
                desiredPitch = altitudePitch(state, targetAltitude, 7.0, 7.0);
            }
            case CRUISE_CROSS -> {
                targetSpeed = profile.cruise();
                targetAltitude = CRUISE_ALTITUDE;
                desiredHeading = state.phaseDirection;
                throttle = cruiseThrottle(state.speed, targetSpeed);
                desiredPitch = altitudePitch(state, targetAltitude, 8.0, 7.0);
            }
            case STALL_SETUP -> {
                targetSpeed = profile.climb();
                targetAltitude = STALL_TEST_ALTITUDE;
                desiredHeading = state.phaseDirection;
                throttle = 1.0;
                desiredPitch = altitudePitch(state, targetAltitude, 9.0, 6.0);
            }
            case STALL_ENTRY -> {
                targetSpeed = profile.stallGuard();
                targetAltitude = STALL_TEST_ALTITUDE;
                desiredHeading = state.phaseDirection;
                throttle = 0.0;
                desiredPitch = -7.0;
            }
            case STALL_RECOVERY -> {
                targetSpeed = profile.recoverySpeed();
                targetAltitude = Math.max(SAFE_ALTITUDE, state.altitude - 20.0);
                desiredHeading = state.phaseDirection;
                throttle = 1.0;
                desiredPitch = 9.0;
            }
            case RETURN_TO_PATTERN -> {
                Waypoint waypoint = new Waypoint(-90.0, 80.0, 70.0);
                return waypointPlan(profile, state, waypoint,
                        Math.max(profile.approachSpeed() * 1.25, profile.climb()));
            }
            case DOWNWIND -> {
                Waypoint waypoint = new Waypoint(-90.0, -90.0, 58.0);
                return waypointPlan(profile, state, waypoint, profile.approachSpeed() * 1.18);
            }
            case BASE -> {
                Waypoint waypoint = new Waypoint(0.0, -150.0, 36.0);
                return waypointPlan(profile, state, waypoint, profile.approachSpeed() * 1.10);
            }
            case FINAL -> {
                double distance = distance(state.x, state.z, 0.0, 16.0);
                targetAltitude = clamp(distance * 0.20, 2.0, 38.0);
                targetSpeed = profile.approachSpeed();
                desiredHeading = headingTo(state.x, state.z, 0.0, 16.0);
                throttle = cruiseThrottle(state.speed, targetSpeed);
                desiredPitch = altitudePitch(state, targetAltitude, 6.0, 9.0);
            }
            case FLARE -> {
                targetAltitude = 0.5;
                targetSpeed = profile.approachSpeed() * 0.92;
                desiredHeading = headingTo(state.x, state.z, 0.0, 41.0);
                throttle = 0.20;
                desiredPitch = -1.5;
            }
            case TOUCHDOWN, BRAKE, PARKED, ABORTED -> {
                targetSpeed = 0.0;
                targetAltitude = 0.0;
                desiredHeading = 0.0;
                throttle = 0.0;
                brake = true;
            }
            case GO_AROUND -> {
                targetSpeed = profile.climb();
                targetAltitude = SAFE_ALTITUDE;
                desiredHeading = 0.0;
                throttle = 1.0;
                desiredPitch = -10.0;
            }
        }
        return new Plan(targetSpeed, targetAltitude, throttle, desiredHeading, desiredPitch, brake);
    }

    private static Plan waypointPlan(Profile profile, State state, Waypoint waypoint, double speed) {
        return new Plan(speed, waypoint.altitude(), cruiseThrottle(state.speed, speed),
                headingTo(state.x, state.z, waypoint.x(), waypoint.z()),
                altitudePitch(state, waypoint.altitude(), 9.0, 9.0), false);
    }

    private static void integrate(Profile profile, Scenario scenario, State state, Plan plan) {
        double headingError = wrap(plan.desiredHeading() - state.heading);
        double turnCommand = clamp(headingError / 38.0, -0.78, 0.78);
        if (state.phase == Phase.TAKEOFF_ROLL) {
            turnCommand = clamp(turnCommand, -0.35, 0.35);
        }
        if ((state.phase == Phase.TURN_LEFT || state.phase == Phase.TURN_RIGHT)
                && state.speed < profile.turnFloor()) {
            turnCommand *= 0.45;
        }

        double speedRatio = clamp(state.speed / Math.max(profile.cruise(), 0.1), 0.18, 1.15);
        double turnRate = profile.turnRateDegPerSecond() * scenario.turnFactor * speedRatio;
        state.heading = wrap(state.heading + turnCommand * turnRate / 20.0);

        double poweredTarget = plan.throttle() * profile.topSpeed();
        double acceleration = profile.topSpeed() / (scenario.accelerationSeconds * 20.0);
        double drag = state.onGround ? 0.003 * profile.topSpeed() : 0.0015 * profile.topSpeed();
        if (plan.brake()) {
            double brakeDistance = profile.brakeDistance() > 0.0 ? profile.brakeDistance() : 180.0;
            double decelerationPerTick = Math.max(0.025,
                    profile.topSpeed() * profile.topSpeed() / Math.max(40.0, 40.0 * brakeDistance));
            state.speed = Math.max(0.0, state.speed - decelerationPerTick / scenario.brakeFactor);
        } else if (state.speed < poweredTarget) {
            state.speed = Math.min(poweredTarget, state.speed + acceleration);
        } else {
            state.speed = Math.max(poweredTarget, state.speed - acceleration * 0.55 - drag);
        }

        double desiredVertical = -plan.desiredPitch() / 10.0 * profile.maxClimbRate();
        if (state.speed < profile.stallGuard()) {
            desiredVertical -= (profile.stallGuard() - state.speed) * 0.32;
        }
        if (state.onGround && state.phase != Phase.ROTATE && state.phase != Phase.CLIMB
                && state.phase != Phase.GO_AROUND) {
            desiredVertical = 0.0;
        }
        state.verticalSpeed += clamp(desiredVertical - state.verticalSpeed, -0.35, 0.35);
        state.verticalSpeed *= scenario.verticalRetention;

        double radians = Math.toRadians(state.heading);
        state.x += -Math.sin(radians) * state.speed / 20.0;
        state.z += Math.cos(radians) * state.speed / 20.0;
        state.altitude += state.verticalSpeed / 20.0;

        if (state.altitude <= 0.0) {
            state.altitude = 0.0;
            state.verticalSpeed = 0.0;
            state.onGround = true;
        } else {
            state.onGround = false;
        }
    }

    private static Transition transition(Profile profile, State state) {
        switch (state.phase) {
            case STARTUP -> {
                if (state.phaseTick > 30) return new Transition(Phase.TAKEOFF_ROLL, "engine_power_ready");
            }
            case TAKEOFF_ROLL -> {
                if (state.speed >= profile.rotateSpeed() && state.phaseTick > 20)
                    return new Transition(Phase.ROTATE, "measured_rotate_speed_reached");
                if (state.phaseTick > 500) return new Transition(Phase.ABORTED, "takeoff_roll_timeout");
            }
            case ROTATE -> {
                if (state.altitude >= 8.0) return new Transition(Phase.CLIMB, "positive_climb_confirmed");
                if (state.phaseTick > 220 && state.onGround)
                    return new Transition(Phase.ABORTED, "rotation_failed_to_lift_off");
            }
            case CLIMB -> {
                if (state.altitude >= SAFE_ALTITUDE - 5.0 && state.speed >= profile.stallGuard() * 1.15) {
                    if (++state.stableTicks >= 30)
                        return new Transition(Phase.CRUISE_OUTBOUND, "safe_altitude_and_speed_stable");
                } else state.stableTicks = 0;
            }
            case CRUISE_OUTBOUND -> {
                if (state.phaseTick >= 240) return new Transition(Phase.TURN_LEFT, "outbound_cruise_sample_complete");
            }
            case TURN_LEFT -> {
                if (Math.abs(wrap(state.phaseTargetHeading - state.heading)) <= 10.0 && state.phaseTick > 45)
                    return new Transition(Phase.CRUISE_CROSS, "left_turn_heading_reached");
                if (state.phaseTick > 440) return new Transition(Phase.ABORTED, "left_turn_timeout");
            }
            case CRUISE_CROSS -> {
                if (state.phaseTick >= 120) return new Transition(Phase.TURN_RIGHT, "between_turns_stabilization_complete");
            }
            case TURN_RIGHT -> {
                if (Math.abs(wrap(state.phaseTargetHeading - state.heading)) <= 10.0 && state.phaseTick > 45)
                    return new Transition(Phase.STALL_SETUP, "right_turn_heading_reached");
                if (state.phaseTick > 440) return new Transition(Phase.ABORTED, "right_turn_timeout");
            }
            case STALL_SETUP -> {
                if (state.altitude >= STALL_TEST_ALTITUDE - 10.0 && state.speed >= profile.climb()) {
                    if (++state.stableTicks >= 30)
                        return new Transition(Phase.STALL_ENTRY, "stall_test_altitude_and_speed_ready");
                } else state.stableTicks = 0;
            }
            case STALL_ENTRY -> {
                if (state.verticalSpeed < -1.0) state.fallingTicks++; else state.fallingTicks = 0;
                if (state.altitude < 65.0) return new Transition(Phase.STALL_RECOVERY, "stall_test_cancelled_for_low_altitude");
                if (state.speed <= profile.stallGuard()) return new Transition(Phase.STALL_RECOVERY, "measured_stall_guard_reached");
                if (state.fallingTicks >= 8) return new Transition(Phase.STALL_RECOVERY, "sustained_descent_detected_during_stall_entry");
                if (state.phaseTick > 320) return new Transition(Phase.STALL_RECOVERY, "stall_entry_safety_timeout");
            }
            case STALL_RECOVERY -> {
                if (state.speed >= profile.recoverySpeed() && state.verticalSpeed >= -0.5 && state.phaseTick > 20) {
                    if (++state.stableTicks >= 20)
                        return new Transition(Phase.RETURN_TO_PATTERN, "recovery_speed_and_vertical_control_restored");
                } else state.stableTicks = 0;
            }
            case RETURN_TO_PATTERN -> {
                if (distance(state.x, state.z, -90.0, 80.0) < 30.0)
                    return new Transition(Phase.DOWNWIND, "downwind_entry_waypoint_reached");
            }
            case DOWNWIND -> {
                if (distance(state.x, state.z, -90.0, -90.0) < 26.0)
                    return new Transition(Phase.BASE, "base_turn_waypoint_reached");
            }
            case BASE -> {
                if (distance(state.x, state.z, 0.0, -150.0) < 24.0)
                    return new Transition(Phase.FINAL, "final_approach_start_reached");
            }
            case FINAL -> {
                double distance = distance(state.x, state.z, 0.0, 16.0);
                if (state.z > 55.0 && !state.onGround)
                    return new Transition(Phase.GO_AROUND, "runway_threshold_passed_without_touchdown");
                if (state.altitude <= 8.0 || distance <= 35.0)
                    return new Transition(Phase.FLARE, "flare_height_or_distance_reached");
                if (state.speed < profile.stallGuard() * 0.95)
                    return new Transition(Phase.GO_AROUND, "approach_speed_below_stall_guard");
            }
            case FLARE -> {
                if (state.onGround) {
                    if (++state.stableTicks >= 4) return new Transition(Phase.TOUCHDOWN, "ground_contact_confirmed");
                } else state.stableTicks = 0;
                if (state.phaseTick > 220 && !state.onGround)
                    return new Transition(Phase.GO_AROUND, "flare_timeout_without_ground_contact");
            }
            case TOUCHDOWN -> {
                if (!state.onGround && state.phaseTick > 15)
                    return new Transition(Phase.GO_AROUND, "aircraft_bounced_after_touchdown");
                if (state.onGround && state.phaseTick >= 10)
                    return new Transition(Phase.BRAKE, "touchdown_stable_begin_explicit_braking");
            }
            case BRAKE -> {
                if (state.onGround && state.speed < 0.25) {
                    if (++state.stableTicks >= 40) return new Transition(Phase.PARKED, "complete_stop_stable_for_40_ticks");
                } else state.stableTicks = 0;
            }
            case GO_AROUND -> {
                if (state.altitude >= 55.0 && state.speed >= profile.climb())
                    return new Transition(Phase.RETURN_TO_PATTERN, "go_around_safe_altitude_and_speed_reached");
            }
            case PARKED, ABORTED -> {
            }
        }
        return null;
    }

    private static ProfileSet loadProfiles(Path requested) throws IOException {
        Path source = requested;
        if (source == null) {
            String configured = System.getProperty("wwdebug.flightProfiles");
            if (configured == null || configured.isBlank()) configured = System.getenv("WW_FLIGHT_PROFILES");
            if (configured != null && !configured.isBlank()) source = Paths.get(configured);
        }
        if (source != null && Files.isRegularFile(source)) {
            try (Reader reader = Files.newBufferedReader(source, StandardCharsets.UTF_8)) {
                JsonObject root = GSON.fromJson(reader, JsonObject.class);
                List<Profile> profiles = new ArrayList<>();
                for (Map.Entry<String, JsonElement> entry : root.entrySet()) {
                    if (!entry.getValue().isJsonObject()) continue;
                    JsonObject object = entry.getValue().getAsJsonObject();
                    Profile profile = Profile.from(entry.getKey(), object);
                    if (profile != null) profiles.add(profile);
                }
                if (!profiles.isEmpty()) return new ProfileSet(source.toAbsolutePath().toString(), profiles);
            }
        }
        return new ProfileSet("synthetic-boundary-matrix", List.of(
                new Profile("synthetic:turn_fighter", "fighter", "turn_fighter", 13.0, 31.0, 26.0, 23.0, 41.0, 120.0),
                new Profile("synthetic:energy_fighter", "fighter", "energy_fighter", 15.0, 38.0, 31.0, 27.0, 50.0, 165.0),
                new Profile("synthetic:heavy_fighter", "fighter", "energy_fighter", 17.0, 35.0, 29.0, 27.0, 47.0, 230.0)
        ));
    }

    private static double altitudePitch(State state, double targetAltitude, double noseUp, double noseDown) {
        double error = targetAltitude - state.altitude;
        return clamp(-error * 0.24 + state.verticalSpeed * 0.32, -noseUp, noseDown);
    }

    private static double cruiseThrottle(double speed, double target) {
        if (speed < target * 0.93) return 1.0;
        if (speed > target * 1.08) return 0.35;
        return 0.68;
    }

    private static double headingTo(double x, double z, double targetX, double targetZ) {
        return Math.toDegrees(Math.atan2(-(targetX - x), targetZ - z));
    }

    private static double distance(double x, double z, double targetX, double targetZ) {
        return Math.hypot(targetX - x, targetZ - z);
    }

    private static double wrap(double degrees) {
        double value = degrees % 360.0;
        if (value >= 180.0) value -= 360.0;
        if (value < -180.0) value += 360.0;
        return value;
    }

    private static double clamp(double value, double minimum, double maximum) {
        return Math.max(minimum, Math.min(maximum, value));
    }

    private enum Phase {
        STARTUP, TAKEOFF_ROLL, ROTATE, CLIMB, CRUISE_OUTBOUND, TURN_LEFT, CRUISE_CROSS,
        TURN_RIGHT, STALL_SETUP, STALL_ENTRY, STALL_RECOVERY, RETURN_TO_PATTERN,
        DOWNWIND, BASE, FINAL, FLARE, TOUCHDOWN, BRAKE, GO_AROUND, PARKED, ABORTED;

        boolean terminal() {
            return this == PARKED || this == ABORTED;
        }
    }

    private enum Scenario {
        NOMINAL("nominal", 7.5, 1.0, 0.985, 1.0),
        WEAK_ENGINE("weak_engine", 9.0, 1.0, 0.985, 1.0),
        TURN_ENERGY_LOSS("turn_energy_loss", 8.0, 0.88, 0.975, 1.0),
        LONG_BRAKE("long_brake", 7.5, 1.0, 0.985, 1.20);

        private final String id;
        private final double accelerationSeconds;
        private final double turnFactor;
        private final double verticalRetention;
        private final double brakeFactor;

        Scenario(String id, double accelerationSeconds, double turnFactor,
                 double verticalRetention, double brakeFactor) {
            this.id = id;
            this.accelerationSeconds = accelerationSeconds;
            this.turnFactor = turnFactor;
            this.verticalRetention = verticalRetention;
            this.brakeFactor = brakeFactor;
        }
    }

    private static final class State {
        private Phase phase = Phase.STARTUP;
        private int tick;
        private int phaseTick;
        private int stableTicks;
        private int fallingTicks;
        private double speed;
        private double altitude;
        private double verticalSpeed;
        private double heading;
        private double x;
        private double z;
        private boolean onGround = true;
        private double phaseTargetHeading;
        private double phaseDirection;

        private void enter(Phase next) {
            phase = next;
            phaseTick = 0;
            stableTicks = 0;
            fallingTicks = 0;
            phaseDirection = heading;
            if (next == Phase.TURN_LEFT) phaseTargetHeading = wrap(heading - 170.0);
            if (next == Phase.TURN_RIGHT) phaseTargetHeading = wrap(heading + 170.0);
        }
    }

    private record Plan(double targetSpeed, double targetAltitude, double throttle,
                        double desiredHeading, double desiredPitch, boolean brake) {
    }

    private record Transition(Phase next, String reason) {
    }

    private record Waypoint(double x, double z, double altitude) {
    }

    private record Profile(String id, String role, String doctrine,
                           double stallGuard, double cruise, double climb, double turnFloor,
                           double topSpeed, double brakeDistance) {
        static Profile from(String id, JsonObject object) {
            Double stall = number(object, "stall_guard_speed_bps");
            Double cruise = number(object, "cruise_speed_bps");
            Double climb = number(object, "climb_target_speed_bps");
            Double turn = number(object, "turn_speed_floor_bps");
            Double top = number(object, "measured_top_speed_bps");
            if (stall == null || cruise == null || climb == null || turn == null || top == null) return null;
            Double brake = number(object, "brake_lead_blocks");
            if (brake == null) brake = number(object, "brake_distance_lower_bound_blocks");
            return new Profile(id, string(object, "role", "unknown"),
                    string(object, "doctrine", "unknown"), stall, cruise, climb, turn, top,
                    brake == null ? 180.0 : brake);
        }

        double rotateSpeed() {
            return Math.max(stallGuard * 1.15, climb * 0.82);
        }

        double recoverySpeed() {
            return Math.max(climb, stallGuard * 1.35);
        }

        double approachSpeed() {
            return Math.min(cruise * 0.82, Math.max(stallGuard * 1.25, turnFloor));
        }

        double turnRateDegPerSecond() {
            return "turn_fighter".equalsIgnoreCase(doctrine) ? 54.0 : 42.0;
        }

        double maxClimbRate() {
            return Math.max(6.0, Math.min(12.0, climb * 0.32));
        }
    }

    private record ProfileSet(String source, List<Profile> profiles) {
    }

    private record SimulationResult(String aircraft, String doctrine, String scenario,
                                    boolean passed, String finalPhase, String reason, int ticks,
                                    double finalX, double finalZ, double finalSpeed,
                                    double finalAltitude, double minimumAirborneAltitude,
                                    double maximumAltitude, int longestUnexpectedStallTicks,
                                    List<String> missingPhases) {
        Map<String, Object> toMap() {
            Map<String, Object> row = new LinkedHashMap<>();
            row.put("aircraft", aircraft);
            row.put("doctrine", doctrine);
            row.put("scenario", scenario);
            row.put("passed", passed);
            row.put("final_phase", finalPhase);
            row.put("reason", reason);
            row.put("ticks", ticks);
            row.put("final_position", List.of(finalX, finalAltitude, finalZ));
            row.put("final_speed_bps", finalSpeed);
            row.put("minimum_airborne_altitude", minimumAirborneAltitude);
            row.put("maximum_altitude", maximumAltitude);
            row.put("longest_unexpected_stall_ticks", longestUnexpectedStallTicks);
            row.put("missing_phases", missingPhases);
            return row;
        }
    }

    private record Arguments(Path profilePath, Path outputPath) {
        static Arguments parse(String[] args) {
            Path profiles = null;
            Path output = Paths.get("build", "reports", "flight-simulation", "report.json");
            for (int index = 0; index < args.length; index++) {
                if ("--profiles".equals(args[index]) && index + 1 < args.length) {
                    profiles = Paths.get(args[++index]);
                } else if ("--output".equals(args[index]) && index + 1 < args.length) {
                    output = Paths.get(args[++index]);
                }
            }
            return new Arguments(profiles, output);
        }
    }

    private static Double number(JsonObject object, String key) {
        if (!object.has(key) || object.get(key).isJsonNull()
                || !object.get(key).isJsonPrimitive()
                || !object.get(key).getAsJsonPrimitive().isNumber()) return null;
        double value = object.get(key).getAsDouble();
        return Double.isFinite(value) && value > 0.0 ? value : null;
    }

    private static String string(JsonObject object, String key, String fallback) {
        return object.has(key) && object.get(key).isJsonPrimitive()
                ? object.get(key).getAsString().toLowerCase(Locale.ROOT) : fallback;
    }
}