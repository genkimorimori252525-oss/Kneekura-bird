package com.wwdebug.autopilot;

import com.wwdebug.benchmark.ReflectiveAircraft;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.util.Mth;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.Vec3;

import java.util.List;

/**
 * The single separation predicate.
 *
 * <p>Two callers depend on this agreeing with itself, and they are not obviously connected:
 * {@code FighterCombatFacade} asks {@link #collisionRisk(Entity)} to decide whether to
 * <em>suppress</em> combat, while {@code FormationFlightManager} runs the same arithmetic to decide
 * whether to <em>write</em> an avoidance manoeuvre. The arbiter reports a terrain dispatch first;
 * otherwise it can report {@code COLLISION_AVOIDANCE} on risk alone even when no avoidance input
 * was written.</p>
 *
 * <p>Both used to carry their own copy of the five constants and their own copy of the danger
 * expression. They agreed exactly, so nothing was broken — but changing one and not the other would
 * have made the arbiter report an authority no layer was exercising, and no test could have noticed.
 * The arithmetic now exists once, here.</p>
 */
public final class AirspaceSafetyProbe {
    static final double SEARCH_HORIZONTAL = 110.0;
    static final double SEARCH_VERTICAL = 48.0;
    static final double HARD_CURRENT_SEPARATION = 9.0;
    static final double HARD_PREDICTED_SEPARATION = 13.0;
    static final double PREDICTION_TICKS = 60.0;

    private AirspaceSafetyProbe() {
    }

    /**
     * Closest-approach geometry between two aircraft.
     *
     * @param currentSeparation   separation right now, in blocks
     * @param predictedSeparation separation at closest approach within the prediction horizon
     * @param closestTicks        ticks until closest approach, clamped to the horizon; 0 when the
     *                            pair is not closing
     * @param dangerous           whether either separation breaches its hard floor
     */
    public record Prediction(double currentSeparation, double predictedSeparation,
                             double closestTicks, boolean dangerous) {
    }

    /** Whether any nearby aircraft breaches separation. Read-only; writes no control. */
    public static boolean collisionRisk(Entity aircraft) {
        if (!(aircraft.level() instanceof ServerLevel level)) {
            return false;
        }
        return nearbyAircraft(level, aircraft).stream()
                .anyMatch(other -> predict(aircraft, other).dangerous());
    }

    /**
     * The one closest-approach computation. Every separation decision must come through here.
     *
     * <p>A pair that is not closing yields {@code closestTicks == 0}, and only the current
     * separation can then make it dangerous — a receding pair must never trip the predicted
     * floor.</p>
     */
    public static Prediction predict(Entity aircraft, Entity other) {
        Vec3 relativePosition = other.position().subtract(aircraft.position());
        Vec3 relativeVelocity = other.getDeltaMovement().subtract(aircraft.getDeltaMovement());
        double velocitySquared = relativeVelocity.lengthSqr();
        double closestTicks = velocitySquared < 1.0e-8 ? 0.0
                : Mth.clamp(-relativePosition.dot(relativeVelocity) / velocitySquared,
                0.0, PREDICTION_TICKS);
        double current = relativePosition.length();
        double predicted = relativePosition.add(relativeVelocity.scale(closestTicks)).length();
        boolean dangerous = current < HARD_CURRENT_SEPARATION
                || (closestTicks > 0.0 && predicted < HARD_PREDICTED_SEPARATION);
        return new Prediction(current, predicted, closestTicks, dangerous);
    }

    /** Candidate aircraft within the shared search volume, excluding {@code aircraft} itself. */
    public static List<Entity> nearbyAircraft(ServerLevel level, Entity aircraft) {
        AABB area = aircraft.getBoundingBox().inflate(
                SEARCH_HORIZONTAL, SEARCH_VERTICAL, SEARCH_HORIZONTAL);
        return level.getEntities(aircraft, area,
                other -> !other.isRemoved() && ReflectiveAircraft.isAirplane(other));
    }
}
