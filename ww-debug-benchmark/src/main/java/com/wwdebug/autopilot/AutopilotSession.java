package com.wwdebug.autopilot;

import com.google.gson.JsonObject;
import net.minecraft.server.MinecraftServer;
import net.minecraft.util.Mth;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.phys.Vec3;

import java.util.UUID;

final class AutopilotSession {
    private static final double SAFE_ALTITUDE = 80.0;
    private static final double CRUISE_ALTITUDE = 100.0;
    private static final double STALL_TEST_ALTITUDE = 125.0;

    private final UUID aircraftUuid;
    private final FlightProfile profile;
    private final Vec3 homePoint;
    private final Vec3 runwayForward;
    private final Vec3 runwayRight;

    private FlightPhase phase = FlightPhase.STARTUP;
    private int phaseTicks;
    private int missionTicks;
    private int stableTicks;
    private int fallingTicks;
    private float phaseTargetYaw;
    private Vec3 phaseDirection;
    private boolean recoveryPullOut;
    private String transitionReason = "mob_pilot_session_started";
    private FlightControlOutput lastOutput;

    AutopilotSession(Entity aircraft, FlightProfile profile) {
        this.aircraftUuid = aircraft.getUUID();
        this.profile = profile;
        this.homePoint = aircraft.position();
        Vec3 forward = horizontal(aircraft.getLookAngle());
        if (forward.lengthSqr() < 1.0e-8) {
            forward = horizontal(Vec3.directionFromRotation(0.0f, aircraft.getYRot()));
        }
        this.runwayForward = forward.normalize();
        this.runwayRight = new Vec3(-runwayForward.z, 0.0, runwayForward.x).normalize();
        this.phaseDirection = runwayForward;
    }

    FlightControlOutput tick(MinecraftServer server, Entity aircraft) {
        FlightSnapshot snapshot = FlightSnapshot.capture(aircraft);
        missionTicks++;
        phaseTicks++;

        if (missionTicks > 16000 && !phase.isTerminal()) {
            transition(server, aircraft, snapshot, FlightPhase.ABORTED, "mission_timeout");
        }

        if (phase.isTerminal()) {
            FlightControlOutput terminal = terminalOutput(aircraft, snapshot);
            logFrame(server, aircraft, snapshot, terminal);
            lastOutput = terminal;
            return terminal;
        }

        if (shouldRecoverFromUnexpectedStall(snapshot)) {
            transition(server, aircraft, snapshot, FlightPhase.STALL_RECOVERY,
                    "unexpected_stall_guard_breach");
        }

        if ((phase == FlightPhase.FINAL || phase == FlightPhase.FLARE)
                && snapshot.altitudeAboveGround() > 8.0
                && snapshot.speedBps() < profile.stallGuardSpeedBps() * 0.95) {
            transition(server, aircraft, snapshot, FlightPhase.GO_AROUND,
                    "approach_speed_below_stall_guard");
        }

        FlightControlOutput output = plan(server, aircraft, snapshot);
        if (phase.isAirborneMissionPhase() && !phase.isLandingPhase()
                && phase != FlightPhase.STALL_ENTRY && phase != FlightPhase.STALL_RECOVERY
                && snapshot.altitudeAboveGround() < 24.0) {
            output = control(aircraft, snapshot, output.desiredDirection(),
                    homePoint.y + SAFE_ALTITUDE, profile.climbTargetSpeedBps(), 1.0f,
                    -12.0, false, "terrain_clearance_emergency_climb", "terrain_recovery");
        }

        logFrame(server, aircraft, snapshot, output);
        lastOutput = output;
        return output;
    }

    private FlightControlOutput plan(MinecraftServer server, Entity aircraft, FlightSnapshot snapshot) {
        return switch (phase) {
            case STARTUP -> startup(server, aircraft, snapshot);
            case TAKEOFF_ROLL -> takeoffRoll(server, aircraft, snapshot);
            case ROTATE -> rotate(server, aircraft, snapshot);
            case CLIMB -> climb(server, aircraft, snapshot);
            case CRUISE_OUTBOUND -> cruiseOutbound(server, aircraft, snapshot);
            case TURN_LEFT -> turn(server, aircraft, snapshot, true);
            case CRUISE_CROSS -> cruiseCross(server, aircraft, snapshot);
            case TURN_RIGHT -> turn(server, aircraft, snapshot, false);
            case STALL_SETUP -> stallSetup(server, aircraft, snapshot);
            case STALL_ENTRY -> stallEntry(server, aircraft, snapshot);
            case STALL_RECOVERY -> stallRecovery(server, aircraft, snapshot);
            case RETURN_TO_PATTERN -> returnToPattern(server, aircraft, snapshot);
            case DOWNWIND -> downwind(server, aircraft, snapshot);
            case BASE -> base(server, aircraft, snapshot);
            case FINAL -> finalApproach(server, aircraft, snapshot);
            case FLARE -> flare(server, aircraft, snapshot);
            case TOUCHDOWN -> touchdown(server, aircraft, snapshot);
            case BRAKE -> brake(server, aircraft, snapshot);
            case GO_AROUND -> goAround(server, aircraft, snapshot);
            case PARKED, ABORTED -> terminalOutput(aircraft, snapshot);
        };
    }

    private FlightControlOutput startup(MinecraftServer server, Entity aircraft, FlightSnapshot snapshot) {
        boolean engineReady = !Double.isFinite(snapshot.enginePower()) || snapshot.enginePower() >= 0.65;
        if (phaseTicks > 20 && engineReady) {
            transition(server, aircraft, snapshot, FlightPhase.TAKEOFF_ROLL, "engine_power_ready");
        } else if (phaseTicks > 120) {
            transition(server, aircraft, snapshot, FlightPhase.TAKEOFF_ROLL, "startup_timeout_fail_open");
        }
        return control(aircraft, snapshot, runwayForward, homePoint.y,
                0.0, 1.0f, 0.0, true,
                "hold_brakes_while_engine_reaches_takeoff_power", "none");
    }

    private FlightControlOutput takeoffRoll(MinecraftServer server, Entity aircraft, FlightSnapshot snapshot) {
        if (snapshot.speedBps() >= profile.rotateSpeedBps() && phaseTicks > 20) {
            transition(server, aircraft, snapshot, FlightPhase.ROTATE, "measured_rotate_speed_reached");
        } else if (!snapshot.onGround()
                && snapshot.speedBps() >= profile.stallGuardSpeedBps() * 1.05) {
            transition(server, aircraft, snapshot, FlightPhase.ROTATE, "airborne_with_safe_speed");
        } else if (phaseTicks > 500) {
            transition(server, aircraft, snapshot, FlightPhase.ABORTED, "takeoff_roll_timeout");
        }
        return control(aircraft, snapshot, runwayForward, homePoint.y,
                profile.rotateSpeedBps(), 1.0f, 0.0, false,
                "accelerate_straight_until_measured_rotate_speed", "none");
    }

    private FlightControlOutput rotate(MinecraftServer server, Entity aircraft, FlightSnapshot snapshot) {
        if (snapshot.altitudeAboveGround() >= 8.0) {
            transition(server, aircraft, snapshot, FlightPhase.CLIMB, "positive_climb_confirmed");
        } else if (phaseTicks > 220 && snapshot.onGround()) {
            transition(server, aircraft, snapshot, FlightPhase.ABORTED, "rotation_failed_to_lift_off");
        }
        return control(aircraft, snapshot, runwayForward, homePoint.y + 20.0,
                profile.climbTargetSpeedBps(), 1.0f, -10.0, false,
                "rotate_gently_after_safe_takeoff_speed", "none");
    }

    private FlightControlOutput climb(MinecraftServer server, Entity aircraft, FlightSnapshot snapshot) {
        double targetAltitude = homePoint.y + SAFE_ALTITUDE;
        if (snapshot.altitudeAboveGround() >= SAFE_ALTITUDE - 5.0
                && snapshot.speedBps() >= profile.stallGuardSpeedBps() * 1.15) {
            stableTicks++;
            if (stableTicks >= 30) {
                transition(server, aircraft, snapshot, FlightPhase.CRUISE_OUTBOUND,
                        "safe_altitude_and_speed_stable");
            }
        } else {
            stableTicks = 0;
        }
        if (phaseTicks > 1400) {
            transition(server, aircraft, snapshot, FlightPhase.ABORTED, "climb_timeout");
        }
        double desiredPitch = altitudePitch(snapshot, targetAltitude, 11.0, 6.0);
        if (snapshot.speedBps() < profile.climbTargetSpeedBps() * 0.90) {
            desiredPitch = Math.max(desiredPitch, -5.0);
        }
        return control(aircraft, snapshot, runwayForward, targetAltitude,
                profile.climbTargetSpeedBps(), 1.0f, desiredPitch, false,
                "climb_to_common_safe_altitude_without_crossing_stall_guard", "none");
    }

    private FlightControlOutput cruiseOutbound(MinecraftServer server, Entity aircraft,
                                                FlightSnapshot snapshot) {
        if (phaseTicks >= 240) {
            transition(server, aircraft, snapshot, FlightPhase.TURN_LEFT,
                    "outbound_cruise_sample_complete");
        }
        double targetAltitude = homePoint.y + CRUISE_ALTITUDE;
        return control(aircraft, snapshot, runwayForward, targetAltitude,
                profile.cruiseSpeedBps(), cruiseThrottle(snapshot, profile.cruiseSpeedBps()),
                altitudePitch(snapshot, targetAltitude, 8.0, 7.0), false,
                "hold_measured_cruise_speed_and_altitude", "none");
    }

    private FlightControlOutput turn(MinecraftServer server, Entity aircraft,
                                     FlightSnapshot snapshot, boolean left) {
        Vec3 desired = Vec3.directionFromRotation(0.0f, phaseTargetYaw);
        double headingError = Math.abs(Mth.wrapDegrees(phaseTargetYaw - snapshot.yawDeg()));
        if (headingError <= 10.0 && phaseTicks > 45) {
            transition(server, aircraft, snapshot,
                    left ? FlightPhase.CRUISE_CROSS : FlightPhase.STALL_SETUP,
                    left ? "left_turn_heading_reached" : "right_turn_heading_reached");
        } else if (phaseTicks > 440) {
            transition(server, aircraft, snapshot, FlightPhase.ABORTED,
                    left ? "left_turn_timeout" : "right_turn_timeout");
        }

        double targetAltitude = homePoint.y + CRUISE_ALTITUDE;
        double targetSpeed = Math.max(profile.turnSpeedFloorBps(), profile.cruiseSpeedBps() * 0.82);
        FlightControlOutput output = control(aircraft, snapshot, desired, targetAltitude,
                targetSpeed, cruiseThrottle(snapshot, targetSpeed),
                altitudePitch(snapshot, targetAltitude, 7.0, 7.0), false,
                left ? "turn_left_toward_target_heading" : "turn_right_toward_target_heading", "none");

        if (snapshot.speedBps() < profile.turnSpeedFloorBps()) {
            return new FlightControlOutput(
                    output.x() * 0.45f,
                    output.y(),
                    Math.max(output.z(), -0.15f),
                    1.0f,
                    output.desiredDirection(),
                    output.targetAltitude(),
                    output.targetSpeedBps(),
                    output.headingErrorDeg(),
                    output.altitudeError(),
                    output.speedErrorBps(),
                    true,
                    output.terrainRisk(),
                    "reduce_bank_and_restore_speed_below_measured_turn_floor",
                    "turn_speed_recovery"
            );
        }
        return output;
    }

    private FlightControlOutput cruiseCross(MinecraftServer server, Entity aircraft,
                                             FlightSnapshot snapshot) {
        if (phaseTicks >= 120) {
            transition(server, aircraft, snapshot, FlightPhase.TURN_RIGHT,
                    "between_turns_stabilization_complete");
        }
        double targetAltitude = homePoint.y + CRUISE_ALTITUDE;
        return control(aircraft, snapshot, phaseDirection, targetAltitude,
                profile.cruiseSpeedBps(), cruiseThrottle(snapshot, profile.cruiseSpeedBps()),
                altitudePitch(snapshot, targetAltitude, 8.0, 7.0), false,
                "stabilize_speed_and_altitude_between_turns", "none");
    }

    private FlightControlOutput stallSetup(MinecraftServer server, Entity aircraft,
                                            FlightSnapshot snapshot) {
        double targetAltitude = homePoint.y + STALL_TEST_ALTITUDE;
        if (snapshot.altitudeAboveGround() >= STALL_TEST_ALTITUDE - 10.0
                && snapshot.speedBps() >= profile.climbTargetSpeedBps()) {
            stableTicks++;
            if (stableTicks >= 30) {
                transition(server, aircraft, snapshot, FlightPhase.STALL_ENTRY,
                        "stall_test_altitude_and_speed_ready");
            }
        } else {
            stableTicks = 0;
        }
        if (phaseTicks > 1000) {
            transition(server, aircraft, snapshot, FlightPhase.ABORTED, "stall_setup_timeout");
        }
        return control(aircraft, snapshot, phaseDirection, targetAltitude,
                profile.climbTargetSpeedBps(), 1.0f,
                altitudePitch(snapshot, targetAltitude, 9.0, 6.0), false,
                "gain_safety_margin_before_controlled_stall_test", "none");
    }

    private FlightControlOutput stallEntry(MinecraftServer server, Entity aircraft,
                                            FlightSnapshot snapshot) {
        if (snapshot.verticalSpeedBps() < -1.0) {
            fallingTicks++;
        } else {
            fallingTicks = 0;
        }
        if (snapshot.altitudeAboveGround() < 65.0) {
            transition(server, aircraft, snapshot, FlightPhase.STALL_RECOVERY,
                    "stall_test_cancelled_for_low_altitude");
        } else if (snapshot.speedBps() <= profile.stallGuardSpeedBps()) {
            transition(server, aircraft, snapshot, FlightPhase.STALL_RECOVERY,
                    "measured_stall_guard_reached");
        } else if (fallingTicks >= 8) {
            transition(server, aircraft, snapshot, FlightPhase.STALL_RECOVERY,
                    "sustained_descent_detected_during_stall_entry");
        } else if (phaseTicks > 320) {
            transition(server, aircraft, snapshot, FlightPhase.STALL_RECOVERY,
                    "stall_entry_safety_timeout");
        }
        return control(aircraft, snapshot, phaseDirection, homePoint.y + STALL_TEST_ALTITUDE,
                profile.stallGuardSpeedBps(), 0.0f, -7.0, false,
                "reduce_power_until_measured_stall_guard_or_descent_is_detected",
                "controlled_stall_entry");
    }

    private FlightControlOutput stallRecovery(MinecraftServer server, Entity aircraft,
                                               FlightSnapshot snapshot) {
        if (snapshot.onGround() && phaseTicks > 40) {
            transition(server, aircraft, snapshot, FlightPhase.ABORTED,
                    "stall_recovery_ground_contact");
            return terminalOutput(aircraft, snapshot);
        }
        if (phaseTicks > 1200) {
            transition(server, aircraft, snapshot, FlightPhase.ABORTED,
                    "stall_recovery_timeout");
            return terminalOutput(aircraft, snapshot);
        }

        double recoverySpeed = profile.recoverySpeedBps();
        if (!recoveryPullOut && (snapshot.speedBps() >= recoverySpeed * 0.92
                || snapshot.altitudeAboveGround() < 70.0)) {
            recoveryPullOut = true;
        }

        if (snapshot.speedBps() >= recoverySpeed * 0.98
                && snapshot.verticalSpeedBps() >= -0.5 && phaseTicks > 20) {
            stableTicks++;
            if (stableTicks >= 20) {
                transition(server, aircraft, snapshot, FlightPhase.RETURN_TO_PATTERN,
                        "recovery_speed_and_vertical_control_restored");
            }
        } else {
            stableTicks = 0;
        }

        double desiredPitch;
        double targetAltitude;
        String reason;
        String override;
        if (recoveryPullOut) {
            desiredPitch = snapshot.verticalSpeedBps() < -0.5 ? -7.0 : 0.0;
            targetAltitude = Math.max(homePoint.y + SAFE_ALTITUDE, snapshot.position().y + 20.0);
            reason = snapshot.verticalSpeedBps() < -0.5
                    ? "pull_out_after_recovery_speed_margin"
                    : "stabilize_after_stall_pull_out";
            override = "stall_recovery_pull_out";
        } else {
            desiredPitch = 8.0;
            targetAltitude = Math.max(homePoint.y + SAFE_ALTITUDE, snapshot.position().y - 20.0);
            reason = "lower_nose_level_wings_and_accelerate";
            override = "stall_recovery_acceleration";
        }

        FlightControlOutput output = control(aircraft, snapshot, phaseDirection,
                targetAltitude, recoverySpeed, 1.0f, desiredPitch, false, reason, override);
        return new FlightControlOutput(
                output.x() * 0.40f,
                output.y(),
                output.z(),
                output.engineTarget(),
                output.desiredDirection(),
                output.targetAltitude(),
                output.targetSpeedBps(),
                output.headingErrorDeg(),
                output.altitudeError(),
                output.speedErrorBps(),
                true,
                output.terrainRisk(),
                output.reason(),
                output.safetyOverride()
        );
    }

    private FlightControlOutput returnToPattern(MinecraftServer server, Entity aircraft,
                                                FlightSnapshot snapshot) {
        Vec3 waypoint = downwindPoint();
        if (horizontalDistance(snapshot.position(), waypoint) < 30.0) {
            transition(server, aircraft, snapshot, FlightPhase.DOWNWIND,
                    "downwind_entry_waypoint_reached");
        } else if (phaseTicks > 1800) {
            transition(server, aircraft, snapshot, FlightPhase.ABORTED,
                    "return_to_pattern_timeout");
        }
        return waypointControl(aircraft, snapshot, waypoint,
                Math.max(profile.approachSpeedBps() * 1.25, profile.climbTargetSpeedBps()),
                "return_to_home_landing_pattern");
    }

    private FlightControlOutput downwind(MinecraftServer server, Entity aircraft,
                                         FlightSnapshot snapshot) {
        Vec3 waypoint = basePoint();
        if (horizontalDistance(snapshot.position(), waypoint) < 26.0) {
            transition(server, aircraft, snapshot, FlightPhase.BASE,
                    "base_turn_waypoint_reached");
        } else if (phaseTicks > 1200) {
            transition(server, aircraft, snapshot, FlightPhase.ABORTED,
                    "downwind_timeout");
        }
        return waypointControl(aircraft, snapshot, waypoint,
                profile.approachSpeedBps() * 1.18,
                "fly_downwind_leg_at_safe_approach_margin");
    }

    private FlightControlOutput base(MinecraftServer server, Entity aircraft,
                                     FlightSnapshot snapshot) {
        Vec3 waypoint = finalStartPoint();
        if (horizontalDistance(snapshot.position(), waypoint) < 24.0) {
            transition(server, aircraft, snapshot, FlightPhase.FINAL,
                    "final_approach_start_reached");
        } else if (phaseTicks > 1000) {
            transition(server, aircraft, snapshot, FlightPhase.ABORTED, "base_timeout");
        }
        return waypointControl(aircraft, snapshot, waypoint,
                profile.approachSpeedBps() * 1.10,
                "align_with_final_approach_path");
    }

    private FlightControlOutput finalApproach(MinecraftServer server, Entity aircraft,
                                              FlightSnapshot snapshot) {
        Vec3 touchdown = touchdownPoint();
        double horizontalDistance = horizontalDistance(snapshot.position(), touchdown);
        double targetAltitude = homePoint.y + Mth.clamp(horizontalDistance * 0.20, 2.0, 38.0);
        double passedRunway = snapshot.position().subtract(homePoint).dot(runwayForward);
        if (passedRunway > 55.0 && !snapshot.onGround()) {
            transition(server, aircraft, snapshot, FlightPhase.GO_AROUND,
                    "runway_threshold_passed_without_touchdown");
        } else if (snapshot.altitudeAboveGround() <= 8.0 || horizontalDistance <= 35.0) {
            transition(server, aircraft, snapshot, FlightPhase.FLARE,
                    "flare_height_or_distance_reached");
        } else if (phaseTicks > 1400) {
            transition(server, aircraft, snapshot, FlightPhase.GO_AROUND,
                    "final_approach_timeout");
        }
        return control(aircraft, snapshot, touchdown.subtract(snapshot.position()), targetAltitude,
                profile.approachSpeedBps(), cruiseThrottle(snapshot, profile.approachSpeedBps()),
                altitudePitch(snapshot, targetAltitude, 6.0, 9.0), false,
                "descend_on_final_while_holding_measured_approach_speed", "none");
    }

    private FlightControlOutput flare(MinecraftServer server, Entity aircraft,
                                      FlightSnapshot snapshot) {
        if (snapshot.onGround()) {
            stableTicks++;
            if (stableTicks >= 4) {
                transition(server, aircraft, snapshot, FlightPhase.TOUCHDOWN,
                        "ground_contact_confirmed");
            }
        } else {
            stableTicks = 0;
        }
        if (phaseTicks > 220 && !snapshot.onGround()) {
            transition(server, aircraft, snapshot, FlightPhase.GO_AROUND,
                    "flare_timeout_without_ground_contact");
        }
        Vec3 aim = touchdownPoint().add(runwayForward.scale(25.0));
        return control(aircraft, snapshot, aim.subtract(snapshot.position()), homePoint.y + 1.0,
                profile.approachSpeedBps() * 0.92, 0.20f, -1.5, false,
                "reduce_descent_rate_and_power_for_touchdown", "none");
    }

    private FlightControlOutput touchdown(MinecraftServer server, Entity aircraft,
                                          FlightSnapshot snapshot) {
        if (!snapshot.onGround() && phaseTicks > 15) {
            transition(server, aircraft, snapshot, FlightPhase.GO_AROUND,
                    "aircraft_bounced_after_touchdown");
        } else if (snapshot.onGround() && phaseTicks >= 10) {
            transition(server, aircraft, snapshot, FlightPhase.BRAKE,
                    "touchdown_stable_begin_explicit_braking");
        }
        return control(aircraft, snapshot, runwayForward, homePoint.y,
                0.0, 0.0f, 0.0, true,
                "keep_runway_heading_and_begin_deceleration", "touchdown_braking");
    }

    private FlightControlOutput brake(MinecraftServer server, Entity aircraft,
                                      FlightSnapshot snapshot) {
        if (snapshot.onGround() && snapshot.horizontalSpeedBps() < 0.25) {
            stableTicks++;
            if (stableTicks >= 40) {
                transition(server, aircraft, snapshot, FlightPhase.PARKED,
                        "complete_stop_stable_for_40_ticks");
            }
        } else {
            stableTicks = 0;
        }
        if (phaseTicks > 1400) {
            transition(server, aircraft, snapshot, FlightPhase.ABORTED, "brake_timeout");
        }
        return control(aircraft, snapshot, runwayForward, homePoint.y,
                0.0, 0.0f, 0.0, true,
                "send_explicit_negative_input_until_complete_stop", "explicit_ground_brake");
    }

    private FlightControlOutput goAround(MinecraftServer server, Entity aircraft,
                                         FlightSnapshot snapshot) {
        if (snapshot.altitudeAboveGround() >= 55.0
                && snapshot.speedBps() >= profile.climbTargetSpeedBps()) {
            transition(server, aircraft, snapshot, FlightPhase.RETURN_TO_PATTERN,
                    "go_around_safe_altitude_and_speed_reached");
        } else if (phaseTicks > 1200) {
            transition(server, aircraft, snapshot, FlightPhase.ABORTED, "go_around_timeout");
        }
        return control(aircraft, snapshot, runwayForward, homePoint.y + SAFE_ALTITUDE,
                profile.climbTargetSpeedBps(), 1.0f, -10.0, false,
                "abort_landing_climb_straight_ahead_and_rejoin_pattern", "go_around");
    }

    private FlightControlOutput waypointControl(Entity aircraft, FlightSnapshot snapshot,
                                                Vec3 waypoint, double targetSpeed, String reason) {
        Vec3 delta = waypoint.subtract(snapshot.position());
        return control(aircraft, snapshot, delta, waypoint.y, targetSpeed,
                cruiseThrottle(snapshot, targetSpeed),
                altitudePitch(snapshot, waypoint.y, 9.0, 9.0), false, reason, "none");
    }

    private FlightControlOutput terminalOutput(Entity aircraft, FlightSnapshot snapshot) {
        if (phase == FlightPhase.PARKED || snapshot.onGround()) {
            return control(aircraft, snapshot, runwayForward, homePoint.y,
                    0.0, 0.0f, 0.0, true,
                    phase == FlightPhase.PARKED
                            ? "mission_complete_hold_parked" : "abort_hold_ground_brake",
                    phase == FlightPhase.PARKED ? "none" : "aborted");
        }
        return control(aircraft, snapshot, snapshot.horizontalForward(), snapshot.position().y,
                profile.cruiseSpeedBps(), 0.70f, 0.0, false,
                "abort_airborne_hold_level_flight_for_manual_recovery", "aborted");
    }

    private FlightControlOutput control(Entity aircraft, FlightSnapshot snapshot,
                                        Vec3 desiredDirection, double targetAltitude,
                                        double targetSpeed, float engineTarget,
                                        double desiredPitchDeg, boolean brake,
                                        String reason, String safetyOverride) {
        Vec3 horizontalDesired = horizontal(desiredDirection);
        if (horizontalDesired.lengthSqr() < 1.0e-8) {
            horizontalDesired = snapshot.horizontalForward();
        }
        horizontalDesired = horizontalDesired.normalize();
        double desiredYaw = Math.toDegrees(Math.atan2(-horizontalDesired.x, horizontalDesired.z));
        double headingError = Mth.wrapDegrees((float) (desiredYaw - snapshot.yawDeg()));
        double altitudeError = targetAltitude - snapshot.position().y;
        double speedError = targetSpeed - snapshot.speedBps();

        float x = (float) Mth.clamp(headingError / 38.0, -0.78, 0.78);
        if (phase == FlightPhase.TAKEOFF_ROLL) {
            x = Mth.clamp(x, -0.35f, 0.35f);
        }
        float z = (float) Mth.clamp((desiredPitchDeg - snapshot.pitchDeg()) / 18.0,
                -0.78, 0.78);
        float y = brake ? -1.0f : 0.0f;
        if (!brake && targetSpeed > 0.0 && snapshot.speedBps() < targetSpeed * 0.90) {
            engineTarget = 1.0f;
        }

        boolean stallRisk = !snapshot.onGround()
                && snapshot.speedBps() < profile.stallGuardSpeedBps();
        boolean terrainRisk = !snapshot.onGround()
                && snapshot.altitudeAboveGround() < 24.0;
        return new FlightControlOutput(
                x, y, z, engineTarget, horizontalDesired, targetAltitude, targetSpeed,
                headingError, altitudeError, speedError, stallRisk, terrainRisk,
                reason, safetyOverride
        );
    }

    private double altitudePitch(FlightSnapshot snapshot, double targetAltitude,
                                 double maximumNoseUp, double maximumNoseDown) {
        double error = targetAltitude - snapshot.position().y;
        return Mth.clamp(-error * 0.24 + snapshot.verticalSpeedBps() * 0.32,
                -maximumNoseUp, maximumNoseDown);
    }

    private float cruiseThrottle(FlightSnapshot snapshot, double targetSpeed) {
        if (snapshot.speedBps() < targetSpeed * 0.93) {
            return 1.0f;
        }
        if (snapshot.speedBps() > targetSpeed * 1.08) {
            return 0.35f;
        }
        return 0.68f;
    }

    private boolean shouldRecoverFromUnexpectedStall(FlightSnapshot snapshot) {
        return phase.isAirborneMissionPhase()
                && phase != FlightPhase.STALL_ENTRY
                && phase != FlightPhase.STALL_RECOVERY
                && phase != FlightPhase.FINAL
                && phase != FlightPhase.FLARE
                && phase != FlightPhase.TOUCHDOWN
                && snapshot.speedBps() < profile.stallGuardSpeedBps() * 0.95;
    }

    private void transition(MinecraftServer server, Entity aircraft, FlightSnapshot snapshot,
                            FlightPhase next, String reason) {
        if (phase == next) {
            return;
        }
        FlightPhase previous = phase;
        phase = next;
        phaseTicks = 0;
        stableTicks = 0;
        fallingTicks = 0;
        recoveryPullOut = next == FlightPhase.STALL_RECOVERY ? false : recoveryPullOut;
        transitionReason = reason;
        phaseDirection = snapshot.horizontalForward();
        if (next == FlightPhase.TURN_LEFT) {
            phaseTargetYaw = Mth.wrapDegrees(snapshot.yawDeg() - 170.0f);
        } else if (next == FlightPhase.TURN_RIGHT) {
            phaseTargetYaw = Mth.wrapDegrees(snapshot.yawDeg() + 170.0f);
        }
        AutopilotLogManager.writeEvent(server, aircraft, "phase_transition",
                previous.name() + "->" + next.name() + ":" + reason, next);
    }

    private void logFrame(MinecraftServer server, Entity aircraft,
                          FlightSnapshot snapshot, FlightControlOutput output) {
        JsonObject frame = new JsonObject();
        frame.addProperty("phase", phase.name());
        frame.addProperty("phase_ticks", phaseTicks);
        frame.addProperty("mission_ticks", missionTicks);
        frame.addProperty("transition_reason", transitionReason);
        frame.addProperty("action_reason", output.reason());
        frame.addProperty("safety_override", output.safetyOverride());
        frame.addProperty("profile_id", profile.profileId().toString());
        frame.addProperty("role", profile.role());
        frame.addProperty("doctrine", profile.doctrine());

        addVec(frame, "position", snapshot.position());
        addVec(frame, "velocity_bpt", snapshot.velocity());
        addVec(frame, "aircraft_forward", snapshot.forward());
        addVec(frame, "desired_direction", output.desiredDirection());
        addVec(frame, "home_position", homePoint);
        addVec(frame, "runway_forward", runwayForward);

        frame.addProperty("speed_bps", snapshot.speedBps());
        frame.addProperty("horizontal_speed_bps", snapshot.horizontalSpeedBps());
        frame.addProperty("vertical_speed_bps", snapshot.verticalSpeedBps());
        frame.addProperty("movement_yaw_deg", snapshot.movementYawDeg());
        frame.addProperty("movement_direction", snapshot.movementDirection());
        frame.addProperty("yaw_deg", snapshot.yawDeg());
        frame.addProperty("pitch_deg", snapshot.pitchDeg());
        frame.addProperty("altitude_above_ground", snapshot.altitudeAboveGround());
        frame.addProperty("on_ground", snapshot.onGround());
        frame.addProperty("engine_power", finite(snapshot.enginePower()));

        frame.addProperty("target_speed_bps", output.targetSpeedBps());
        frame.addProperty("target_altitude", output.targetAltitude());
        frame.addProperty("heading_error_deg", output.headingErrorDeg());
        frame.addProperty("altitude_error", output.altitudeError());
        frame.addProperty("speed_error_bps", output.speedErrorBps());
        frame.addProperty("control_x", output.x());
        frame.addProperty("control_y", output.y());
        frame.addProperty("control_z", output.z());
        frame.addProperty("engine_target_command", output.engineTarget());
        frame.addProperty("stall_risk", output.stallRisk());
        frame.addProperty("terrain_risk", output.terrainRisk());

        frame.addProperty("profile_stall_guard_speed_bps", profile.stallGuardSpeedBps());
        frame.addProperty("profile_cruise_speed_bps", profile.cruiseSpeedBps());
        frame.addProperty("profile_climb_target_speed_bps", profile.climbTargetSpeedBps());
        frame.addProperty("profile_turn_speed_floor_bps", profile.turnSpeedFloorBps());
        frame.addProperty("profile_measured_top_speed_bps", profile.measuredTopSpeedBps());
        if (profile.brakeLeadBlocks() != null) {
            frame.addProperty("profile_brake_lead_blocks", profile.brakeLeadBlocks());
        }
        if (profile.brakeDistanceLowerBoundBlocks() != null) {
            frame.addProperty("profile_brake_distance_lower_bound_blocks",
                    profile.brakeDistanceLowerBoundBlocks());
        }

        AutopilotLogManager.writeFrame(server, aircraft, frame);
    }

    private Vec3 downwindPoint() {
        return homePoint.add(runwayForward.scale(80.0))
                .add(runwayRight.scale(90.0)).add(0.0, 70.0, 0.0);
    }

    private Vec3 basePoint() {
        return homePoint.subtract(runwayForward.scale(90.0))
                .add(runwayRight.scale(90.0)).add(0.0, 58.0, 0.0);
    }

    private Vec3 finalStartPoint() {
        return homePoint.subtract(runwayForward.scale(150.0)).add(0.0, 36.0, 0.0);
    }

    private Vec3 touchdownPoint() {
        return homePoint.add(runwayForward.scale(16.0)).add(0.0, 1.0, 0.0);
    }

    private static double horizontalDistance(Vec3 first, Vec3 second) {
        double dx = first.x - second.x;
        double dz = first.z - second.z;
        return Math.sqrt(dx * dx + dz * dz);
    }

    private static Vec3 horizontal(Vec3 vector) {
        return new Vec3(vector.x, 0.0, vector.z);
    }

    private static void addVec(JsonObject root, String name, Vec3 value) {
        JsonObject vector = new JsonObject();
        vector.addProperty("x", value.x);
        vector.addProperty("y", value.y);
        vector.addProperty("z", value.z);
        root.add(name, vector);
    }

    private static double finite(double value) {
        return Double.isFinite(value) ? value : 0.0;
    }

    UUID aircraftUuid() {
        return aircraftUuid;
    }

    FlightPhase phase() {
        return phase;
    }

    int phaseTicks() {
        return phaseTicks;
    }

    int missionTicks() {
        return missionTicks;
    }

    String transitionReason() {
        return transitionReason;
    }

    FlightControlOutput lastOutput() {
        return lastOutput;
    }

    FlightProfile profile() {
        return profile;
    }
}
