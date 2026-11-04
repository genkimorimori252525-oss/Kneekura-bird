package com.wwdebug.autopilot;

import net.minecraft.util.Mth;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.level.ClipContext;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraft.world.phys.HitResult;
import net.minecraft.world.phys.Vec3;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Predicts collisions along a multi-ray flight corridor and selects a short-lived safe heading.
 *
 * <p>The planner intentionally remains independent from mission doctrine. It receives the current
 * mission command, searches climb and lateral detours, then returns a temporary safety route. The
 * original mission controller resumes automatically once its direct corridor has remained clear.</p>
 */
final class TerrainAvoidancePlanner {
    private static final double MIN_LOOK_AHEAD = 64.0;
    private static final double MAX_LOOK_AHEAD = 190.0;
    private static final double MIN_SAFE_CLEARANCE = 28.0;
    private static final int REPLAN_HOLD_TICKS = 32;
    private static final int CLEAR_RELEASE_TICKS = 12;
    private static final Map<UUID, Long> ACTIVE_UNTIL_GAME_TICK = new ConcurrentHashMap<>();

    private TerrainAvoidancePlanner() {
    }

    static Decision plan(Entity aircraft, FlightPhase phase, FlightSnapshot snapshot,
                         FlightControlOutput planned, State state) {
        if (!eligible(phase, snapshot)) {
            markClear(aircraft);
            return state.clear(false, 0.0, 0.0);
        }

        Vec3 intended = horizontal(planned.desiredDirection());
        if (intended.lengthSqr() < 1.0e-8) {
            intended = snapshot.horizontalForward();
        }
        intended = intended.normalize();

        double lookAhead = Mth.clamp(snapshot.horizontalSpeedBps() * 4.2,
                MIN_LOOK_AHEAD, MAX_LOOK_AHEAD);
        Probe direct = probe(aircraft, snapshot, intended, planned.targetAltitude(), lookAhead);
        boolean lowClearance = snapshot.altitudeAboveGround() < 30.0
                && phase != FlightPhase.ROTATE && phase != FlightPhase.CLIMB;
        boolean directRisk = direct.clearanceBlocks() < lookAhead * 0.92 || lowClearance;

        if (!directRisk) {
            if (state.active && state.clearTicks < CLEAR_RELEASE_TICKS) {
                state.clearTicks++;
                Probe held = probe(aircraft, snapshot, state.direction, state.targetAltitude, lookAhead);
                if (held.clearanceBlocks() >= Math.min(lookAhead * 0.55, 70.0)) {
                    return markActive(aircraft,
                            state.heldDecision(lookAhead, direct.clearanceBlocks(), held.clearanceBlocks()));
                }
            }
            markClear(aircraft);
            return state.clear(state.active, lookAhead, direct.clearanceBlocks());
        }

        state.clearTicks = 0;
        if (state.active && state.holdTicks > 0) {
            Probe held = probe(aircraft, snapshot, state.direction, state.targetAltitude, lookAhead);
            if (held.clearanceBlocks() >= MIN_SAFE_CLEARANCE) {
                state.holdTicks--;
                return markActive(aircraft,
                        state.heldDecision(lookAhead, direct.clearanceBlocks(), held.clearanceBlocks()));
            }
        }

        double climb = Mth.clamp(lookAhead * 0.32, 34.0, 62.0);
        double modestClimb = Mth.clamp(lookAhead * 0.16, 16.0, 34.0);
        List<Candidate> candidates = new ArrayList<>();
        candidates.add(candidate(aircraft, snapshot, intended, planned.targetAltitude(),
                lookAhead, 0.0, climb, "climb"));
        candidates.add(candidate(aircraft, snapshot, rotate(intended, -32.0), planned.targetAltitude(),
                lookAhead, -32.0, modestClimb, "left_detour"));
        candidates.add(candidate(aircraft, snapshot, rotate(intended, 32.0), planned.targetAltitude(),
                lookAhead, 32.0, modestClimb, "right_detour"));
        candidates.add(candidate(aircraft, snapshot, rotate(intended, -58.0), planned.targetAltitude(),
                lookAhead, -58.0, 10.0, "hard_left_detour"));
        candidates.add(candidate(aircraft, snapshot, rotate(intended, 58.0), planned.targetAltitude(),
                lookAhead, 58.0, 10.0, "hard_right_detour"));

        Candidate best = candidates.stream()
                .max(Comparator.comparingDouble(Candidate::score))
                .orElseThrow();

        boolean emergency = best.probe().clearanceBlocks() < MIN_SAFE_CLEARANCE;
        Vec3 selectedDirection = emergency ? intended : best.direction();
        double selectedAltitude = emergency
                ? Math.max(planned.targetAltitude(), snapshot.position().y + 68.0)
                : best.targetAltitude();
        String mode = emergency ? "emergency_climb" : best.mode();
        double selectedClearance = emergency ? direct.clearanceBlocks() : best.probe().clearanceBlocks();
        double headingOffset = emergency ? 0.0 : best.headingOffsetDeg();
        double climbBlocks = Math.max(0.0, selectedAltitude - snapshot.position().y);

        boolean changed = !state.active || !mode.equals(state.mode)
                || angleBetween(state.direction, selectedDirection) > 8.0;
        state.active = true;
        state.mode = mode;
        state.direction = selectedDirection.normalize();
        state.targetAltitude = selectedAltitude;
        state.headingOffsetDeg = headingOffset;
        state.climbBlocks = climbBlocks;
        state.holdTicks = REPLAN_HOLD_TICKS;

        return markActive(aircraft, new Decision(true, changed, mode, state.direction, selectedAltitude,
                lookAhead, direct.clearanceBlocks(), selectedClearance,
                headingOffset, climbBlocks, emergency));
    }

    static boolean active(Entity aircraft) {
        Long until = ACTIVE_UNTIL_GAME_TICK.get(aircraft.getUUID());
        long now = aircraft.level().getGameTime();
        if (until == null || until < now) {
            ACTIVE_UNTIL_GAME_TICK.remove(aircraft.getUUID());
            return false;
        }
        return true;
    }

    private static Decision markActive(Entity aircraft, Decision decision) {
        ACTIVE_UNTIL_GAME_TICK.put(aircraft.getUUID(), aircraft.level().getGameTime() + 2L);
        return decision;
    }

    private static void markClear(Entity aircraft) {
        ACTIVE_UNTIL_GAME_TICK.remove(aircraft.getUUID());
    }

    private static boolean eligible(FlightPhase phase, FlightSnapshot snapshot) {
        if (snapshot.onGround() || !phase.isAirborneMissionPhase()) {
            return false;
        }
        return switch (phase) {
            case STALL_ENTRY, STALL_RECOVERY, FINAL, FLARE, TOUCHDOWN, BRAKE, PARKED, ABORTED -> false;
            default -> true;
        };
    }

    private static Candidate candidate(Entity aircraft, FlightSnapshot snapshot, Vec3 direction,
                                       double plannedAltitude, double lookAhead,
                                       double headingOffsetDeg, double climbBlocks, String mode) {
        double targetAltitude = Math.max(plannedAltitude, snapshot.position().y + climbBlocks);
        Probe result = probe(aircraft, snapshot, direction, targetAltitude, lookAhead);
        double turnPenalty = Math.abs(headingOffsetDeg) * 0.18;
        double climbPenalty = Math.max(0.0, targetAltitude - plannedAltitude) * 0.05;
        double score = result.clearanceBlocks() - turnPenalty - climbPenalty;
        return new Candidate(mode, direction.normalize(), targetAltitude,
                headingOffsetDeg, result, score);
    }

    private static Probe probe(Entity aircraft, FlightSnapshot snapshot, Vec3 direction,
                               double targetAltitude, double lookAhead) {
        Vec3 horizontal = horizontal(direction);
        if (horizontal.lengthSqr() < 1.0e-8) {
            horizontal = snapshot.horizontalForward();
        }
        horizontal = horizontal.normalize();
        Vec3 right = new Vec3(-horizontal.z, 0.0, horizontal.x).normalize();
        double lateral = Math.max(2.0, aircraft.getBbWidth() * 0.75 + 1.5);
        double vertical = Math.max(1.8, aircraft.getBbHeight() * 0.55 + 0.8);
        Vec3 center = snapshot.position().add(0.0, aircraft.getBbHeight() * 0.50, 0.0);
        double verticalDelta = targetAltitude - snapshot.position().y;

        List<Vec3> offsets = List.of(
                Vec3.ZERO,
                right.scale(lateral),
                right.scale(-lateral),
                new Vec3(0.0, vertical, 0.0),
                new Vec3(0.0, -vertical * 0.65, 0.0)
        );

        double minimum = lookAhead;
        for (Vec3 offset : offsets) {
            Vec3 start = center.add(offset);
            Vec3 end = start.add(horizontal.scale(lookAhead)).add(0.0, verticalDelta, 0.0);
            BlockHitResult hit = aircraft.level().clip(new ClipContext(
                    start,
                    end,
                    ClipContext.Block.COLLIDER,
                    ClipContext.Fluid.NONE,
                    aircraft
            ));
            // lookAhead and every clearance threshold are horizontal distances.  A sloped
            // ray's 3D length is longer and would hide a hit inside that corridor.
            double clearance = lookAhead;
            if (hit.getType() != HitResult.Type.MISS) {
                Vec3 location = hit.getLocation();
                // Keeping the old value in the minimum also preserves existing strict
                // threshold decisions when hypot and distanceTo round differently.
                clearance = Math.min(start.distanceTo(location),
                        Math.hypot(location.x - start.x, location.z - start.z));
                if (!Double.isFinite(start.x) || !Double.isFinite(start.y) || !Double.isFinite(start.z)
                        || !Double.isFinite(location.x) || !Double.isFinite(location.y)
                        || !Double.isFinite(location.z) || !Double.isFinite(clearance)) {
                    clearance = 0.0; // A malformed hit must never turn the corridor clear.
                }
            }
            minimum = Math.min(minimum, clearance);
        }
        return new Probe(minimum);
    }

    private static Vec3 rotate(Vec3 vector, double degrees) {
        double radians = Math.toRadians(degrees);
        double cosine = Math.cos(radians);
        double sine = Math.sin(radians);
        return new Vec3(
                vector.x * cosine - vector.z * sine,
                0.0,
                vector.x * sine + vector.z * cosine
        ).normalize();
    }

    private static double angleBetween(Vec3 first, Vec3 second) {
        Vec3 a = horizontal(first);
        Vec3 b = horizontal(second);
        if (a.lengthSqr() < 1.0e-8 || b.lengthSqr() < 1.0e-8) {
            return 180.0;
        }
        double dot = Mth.clamp(a.normalize().dot(b.normalize()), -1.0, 1.0);
        return Math.toDegrees(Math.acos(dot));
    }

    private static Vec3 horizontal(Vec3 vector) {
        return new Vec3(vector.x, 0.0, vector.z);
    }

    static final class State {
        private boolean active;
        private String mode = "clear";
        private Vec3 direction = Vec3.ZERO;
        private double targetAltitude;
        private double headingOffsetDeg;
        private double climbBlocks;
        private int holdTicks;
        private int clearTicks;

        private Decision heldDecision(double lookAhead, double directClearance,
                                      double selectedClearance) {
            return new Decision(true, false, mode, direction, targetAltitude,
                    lookAhead, directClearance, selectedClearance,
                    headingOffsetDeg, climbBlocks, "emergency_climb".equals(mode));
        }

        private Decision clear(boolean changed, double lookAhead, double directClearance) {
            active = false;
            mode = "clear";
            direction = Vec3.ZERO;
            targetAltitude = 0.0;
            headingOffsetDeg = 0.0;
            climbBlocks = 0.0;
            holdTicks = 0;
            clearTicks = 0;
            return new Decision(false, changed, "clear", Vec3.ZERO, 0.0,
                    lookAhead, directClearance, directClearance, 0.0, 0.0, false);
        }
    }

    record Decision(
            boolean active,
            boolean changed,
            String mode,
            Vec3 desiredDirection,
            double targetAltitude,
            double lookAheadBlocks,
            double directClearanceBlocks,
            double selectedClearanceBlocks,
            double headingOffsetDeg,
            double climbBlocks,
            boolean emergency
    ) {
        String description() {
            return mode
                    + ":direct=" + round(directClearanceBlocks)
                    + ":selected=" + round(selectedClearanceBlocks)
                    + ":lookahead=" + round(lookAheadBlocks)
                    + ":heading_offset=" + round(headingOffsetDeg)
                    + ":climb=" + round(climbBlocks);
        }

        private static double round(double value) {
            return Math.rint(value * 10.0) / 10.0;
        }
    }

    private record Probe(double clearanceBlocks) {
    }

    private record Candidate(
            String mode,
            Vec3 direction,
            double targetAltitude,
            double headingOffsetDeg,
            Probe probe,
            double score
    ) {
    }
}
