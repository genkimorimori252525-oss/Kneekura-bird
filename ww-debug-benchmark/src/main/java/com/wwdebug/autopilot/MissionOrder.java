package com.wwdebug.autopilot;

import net.minecraft.world.phys.Vec3;

import javax.annotation.Nullable;
import java.util.Collections;
import java.util.EnumSet;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;

/**
 * Immutable mission intent. This class deliberately contains no flight-control behavior: it is the
 * stable data boundary between future command/persistence code and role-specific policies.
 */
public record MissionOrder(
        UUID orderId,
        Type type,
        @Nullable UUID targetEntity,
        @Nullable Vec3 targetPosition,
        double targetRadius,
        @Nullable Vec3 homePosition,
        @Nullable Vec3 runwayDirection,
        @Nullable UUID formationId,
        @Nullable UUID leaderAircraft,
        int remainingAttackRuns,
        double minimumReturnFuelFraction,
        boolean weaponsFree,
        @Nullable Double missionAltitude,
        @Nullable Vec3 ingressDirection,
        Set<AbortCondition> abortConditions
) {
    public MissionOrder {
        orderId = Objects.requireNonNull(orderId, "orderId");
        type = Objects.requireNonNull(type, "type");
        if (!Double.isFinite(targetRadius) || targetRadius < 0.0) {
            throw new IllegalArgumentException("targetRadius must be finite and non-negative");
        }
        if (remainingAttackRuns < 0) {
            throw new IllegalArgumentException("remainingAttackRuns must be non-negative");
        }
        if (!Double.isFinite(minimumReturnFuelFraction)
                || minimumReturnFuelFraction < 0.0 || minimumReturnFuelFraction > 1.0) {
            throw new IllegalArgumentException("minimumReturnFuelFraction must be between 0 and 1");
        }
        if (missionAltitude != null && (!Double.isFinite(missionAltitude) || missionAltitude < 0.0)) {
            throw new IllegalArgumentException("missionAltitude must be finite and non-negative");
        }
        runwayDirection = normalizedHorizontal(runwayDirection, "runwayDirection");
        ingressDirection = normalizedHorizontal(ingressDirection, "ingressDirection");
        abortConditions = immutableConditions(abortConditions);

        if (type.requiresTarget() && targetEntity == null && targetPosition == null) {
            throw new IllegalArgumentException(type + " requires a target entity or position");
        }
        if (type.requiresHome() && homePosition == null) {
            throw new IllegalArgumentException(type + " requires a home position");
        }
        if (type == Type.LAND && runwayDirection == null) {
            throw new IllegalArgumentException("LAND requires a runway direction");
        }
        if (type.isStrike() && remainingAttackRuns <= 0) {
            throw new IllegalArgumentException(type + " requires at least one attack run");
        }
        if (weaponsFree && !type.supportsEngagement()) {
            throw new IllegalArgumentException(type + " cannot enable weapon authority");
        }
    }

    public MissionOrder withRemainingAttackRuns(int remaining) {
        return new MissionOrder(orderId, type, targetEntity, targetPosition, targetRadius,
                homePosition, runwayDirection, formationId, leaderAircraft, remaining,
                minimumReturnFuelFraction, weaponsFree, missionAltitude, ingressDirection,
                abortConditions);
    }

    public boolean hasTarget() {
        return targetEntity != null || targetPosition != null;
    }

    public static Builder builder(Type type) {
        return new Builder(type);
    }

    private static Set<AbortCondition> immutableConditions(Set<AbortCondition> values) {
        if (values == null || values.isEmpty()) {
            return Collections.emptySet();
        }
        return Collections.unmodifiableSet(EnumSet.copyOf(values));
    }

    @Nullable
    private static Vec3 normalizedHorizontal(@Nullable Vec3 value, String name) {
        if (value == null) {
            return null;
        }
        Vec3 horizontal = new Vec3(value.x, 0.0, value.z);
        if (horizontal.lengthSqr() < 1.0e-8) {
            throw new IllegalArgumentException(name + " must have a horizontal direction");
        }
        return horizontal.normalize();
    }

    public enum Type {
        PATROL,
        CAP,
        INTERCEPT,
        ESCORT,
        BOMB_TARGET,
        DIVE_BOMB,
        GROUND_ATTACK,
        TORPEDO_ATTACK,
        RETURN_TO_BASE,
        LAND,
        HOLD_POSITION;

        public boolean requiresTarget() {
            return switch (this) {
                case INTERCEPT, ESCORT, BOMB_TARGET, DIVE_BOMB, GROUND_ATTACK, TORPEDO_ATTACK -> true;
                default -> false;
            };
        }

        public boolean requiresHome() {
            return this == RETURN_TO_BASE || this == LAND;
        }

        public boolean isStrike() {
            return this == BOMB_TARGET || this == DIVE_BOMB
                    || this == GROUND_ATTACK || this == TORPEDO_ATTACK;
        }

        public boolean supportsEngagement() {
            return this == CAP || this == INTERCEPT || this == ESCORT || isStrike();
        }
    }

    public enum AbortCondition {
        PLAYER_TAKES_CONTROL,
        PILOT_LOST,
        AIRCRAFT_DESTROYED,
        CRITICAL_DAMAGE,
        FUEL_BELOW_RESERVE,
        AMMUNITION_DEPLETED,
        TARGET_LOST,
        TARGET_DESTROYED,
        TERRAIN_UNSAFE,
        FRIENDLY_FIRE_RISK,
        MAXIMUM_RETRIES_REACHED
    }

    public static final class Builder {
        private final Type type;
        private UUID orderId = UUID.randomUUID();
        private UUID targetEntity;
        private Vec3 targetPosition;
        private double targetRadius;
        private Vec3 homePosition;
        private Vec3 runwayDirection;
        private UUID formationId;
        private UUID leaderAircraft;
        private int remainingAttackRuns;
        private double minimumReturnFuelFraction;
        private boolean weaponsFree;
        private Double missionAltitude;
        private Vec3 ingressDirection;
        private Set<AbortCondition> abortConditions = EnumSet.noneOf(AbortCondition.class);

        private Builder(Type type) {
            this.type = Objects.requireNonNull(type, "type");
        }

        public Builder orderId(UUID value) { orderId = value; return this; }
        public Builder targetEntity(UUID value) { targetEntity = value; return this; }
        public Builder targetPosition(Vec3 value, double radius) { targetPosition = value; targetRadius = radius; return this; }
        public Builder home(Vec3 position, Vec3 runway) { homePosition = position; runwayDirection = runway; return this; }
        public Builder formation(UUID id, UUID leader) { formationId = id; leaderAircraft = leader; return this; }
        public Builder attackRuns(int value) { remainingAttackRuns = value; return this; }
        public Builder minimumReturnFuelFraction(double value) { minimumReturnFuelFraction = value; return this; }
        public Builder weaponsFree(boolean value) { weaponsFree = value; return this; }
        public Builder missionAltitude(double value) { missionAltitude = value; return this; }
        public Builder ingressDirection(Vec3 value) { ingressDirection = value; return this; }
        public Builder abortOn(AbortCondition... values) {
            Collections.addAll(abortConditions, values);
            return this;
        }

        public MissionOrder build() {
            return new MissionOrder(orderId, type, targetEntity, targetPosition, targetRadius,
                    homePosition, runwayDirection, formationId, leaderAircraft,
                    remainingAttackRuns, minimumReturnFuelFraction, weaponsFree,
                    missionAltitude, ingressDirection, abortConditions);
        }
    }
}
