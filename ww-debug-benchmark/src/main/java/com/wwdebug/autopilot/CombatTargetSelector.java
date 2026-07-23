package com.wwdebug.autopilot;

import net.minecraft.server.level.ServerLevel;
import net.minecraft.util.Mth;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.Mob;
import net.minecraft.world.entity.TamableAnimal;
import net.minecraft.world.entity.monster.Enemy;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.level.ClipContext;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraft.world.phys.HitResult;
import net.minecraft.world.phys.Vec3;

import java.util.Comparator;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

/**
 * Conservative target acquisition shared by fighter weapon doctrines.
 *
 * <p>This layer never fires a weapon. It excludes players, neutral entities, passengers, tame
 * animals, scoreboard allies and same-faction entities. When either aircraft side declares a
 * combat faction, only an explicit directional hostile-faction tag permits acquisition. Unfactioned
 * ordinary mobs retain the legacy Enemy/active-attacker fallback.</p>
 */
final class CombatTargetSelector {
    private static final double HORIZONTAL_RANGE = 320.0;
    private static final double VERTICAL_RANGE = 96.0;
    private static final int RESCAN_TICKS = 10;
    private static final int LOST_GRACE_TICKS = 30;

    private CombatTargetSelector() {
    }

    static Update update(ServerLevel level, Entity aircraft, FlightPhase phase, State state) {
        if (!eligiblePhase(phase)) {
            return state.clear("combat_disabled_in_" + phase.name().toLowerCase());
        }

        LivingEntity pilot = aircraft.getControllingPassenger();
        if (pilot == null) {
            return state.clear("no_living_pilot");
        }

        state.rescanTicks--;
        if (state.targetUuid != null) {
            Entity current = level.getEntity(state.targetUuid);
            if (current instanceof LivingEntity living && validTarget(aircraft, pilot, living)) {
                Solution solution = solve(aircraft, pilot, living);
                if (solution.lineOfSight() && solution.distanceBlocks() <= HORIZONTAL_RANGE * 1.15) {
                    state.lostTicks = 0;
                    if (state.rescanTicks > 0) {
                        return new Update(Optional.of(solution), false, false, "target_tracked");
                    }
                } else if (++state.lostTicks <= LOST_GRACE_TICKS && state.rescanTicks > 0) {
                    return new Update(Optional.of(solution), false, false, "target_temporarily_obscured");
                }
            }
        }

        if (state.rescanTicks > 0) {
            return new Update(Optional.empty(), false, false, "awaiting_rescan");
        }
        state.rescanTicks = RESCAN_TICKS;

        AABB search = aircraft.getBoundingBox().inflate(HORIZONTAL_RANGE, VERTICAL_RANGE, HORIZONTAL_RANGE);
        List<LivingEntity> candidates = level.getEntitiesOfClass(
                LivingEntity.class,
                search,
                candidate -> validTarget(aircraft, pilot, candidate)
        );
        Optional<Solution> selected = candidates.stream()
                .map(candidate -> solve(aircraft, pilot, candidate))
                .filter(solution -> solution.lineOfSight() || solution.distanceBlocks() < 48.0)
                .max(Comparator.comparingDouble(Solution::score));

        UUID previous = state.targetUuid;
        if (selected.isPresent()) {
            Solution solution = selected.get();
            state.targetUuid = solution.targetUuid();
            state.lostTicks = 0;
            return new Update(selected, !solution.targetUuid().equals(previous), false,
                    previous == null ? "hostile_target_acquired" : "hostile_target_changed");
        }

        state.targetUuid = null;
        state.lostTicks = 0;
        return new Update(Optional.empty(), false, previous != null, "no_eligible_hostile_target");
    }

    private static boolean eligiblePhase(FlightPhase phase) {
        if (!phase.isAirborneMissionPhase() || phase.isLandingPhase()) {
            return false;
        }
        return phase != FlightPhase.STALL_ENTRY && phase != FlightPhase.STALL_RECOVERY;
    }

    private static boolean validTarget(Entity aircraft, LivingEntity pilot, LivingEntity candidate) {
        if (!candidate.isAlive() || candidate == pilot || candidate == aircraft
                || candidate instanceof Player || aircraft.hasPassenger(candidate)
                || candidate.getVehicle() == aircraft) {
            return false;
        }
        if (candidate instanceof TamableAnimal tame && tame.isTame()) {
            return false;
        }
        if (aircraft.isAlliedTo(candidate) || pilot.isAlliedTo(candidate)
                || candidate.isAlliedTo(pilot)
                || CombatFactionRelations.sameFaction(aircraft, candidate)
                || CombatFactionRelations.sameFaction(pilot, candidate)) {
            return false;
        }
        if (CombatFactionRelations.relationshipDefined(aircraft, pilot, candidate)) {
            return CombatFactionRelations.explicitlyHostile(aircraft, pilot, candidate);
        }
        if (candidate instanceof Enemy) {
            return true;
        }
        return candidate instanceof Mob mob && mob.getTarget() == pilot;
    }

    private static Solution solve(Entity aircraft, LivingEntity pilot, LivingEntity target) {
        Vec3 origin = aircraft.getBoundingBox().getCenter();
        Vec3 aim = target.getEyePosition();
        Vec3 delta = aim.subtract(origin);
        double distance = delta.length();
        Vec3 direction = distance > 1.0e-8 ? delta.scale(1.0 / distance) : Vec3.ZERO;
        Vec3 forward = aircraft.getLookAngle().normalize();
        double dot = Mth.clamp(forward.dot(direction), -1.0, 1.0);
        double angle = Math.toDegrees(Math.acos(dot));
        boolean lineOfSight = clearLine(aircraft, origin, aim);
        boolean attackingPilot = target instanceof Mob mob && mob.getTarget() == pilot;
        boolean explicitFactionHostile =
                CombatFactionRelations.explicitlyHostile(aircraft, pilot, target);

        double score = 220.0 - distance;
        score += Math.max(0.0, 100.0 - angle * 2.0);
        score += lineOfSight ? 60.0 : -80.0;
        score += attackingPilot ? 120.0 : 0.0;
        score += explicitFactionHostile ? 180.0 : target instanceof Enemy ? 40.0 : 0.0;
        return new Solution(
                target.getUUID(),
                target.getType().toString(),
                target.getName().getString(),
                aim,
                direction,
                distance,
                angle,
                lineOfSight,
                attackingPilot,
                explicitFactionHostile,
                CombatFactionRelations.faction(target).orElse("none"),
                score
        );
    }

    private static boolean clearLine(Entity aircraft, Vec3 origin, Vec3 aim) {
        BlockHitResult hit = aircraft.level().clip(new ClipContext(
                origin,
                aim,
                ClipContext.Block.COLLIDER,
                ClipContext.Fluid.NONE,
                aircraft
        ));
        return hit.getType() == HitResult.Type.MISS
                || hit.getLocation().distanceToSqr(aim) <= 2.25;
    }

    static final class State {
        private UUID targetUuid;
        private int rescanTicks;
        private int lostTicks;

        private Update clear(String reason) {
            boolean lost = targetUuid != null;
            targetUuid = null;
            rescanTicks = 0;
            lostTicks = 0;
            return new Update(Optional.empty(), false, lost, reason);
        }
    }

    record Update(
            Optional<Solution> solution,
            boolean acquiredOrChanged,
            boolean lost,
            String reason
    ) {
    }

    record Solution(
            UUID targetUuid,
            String targetType,
            String targetName,
            Vec3 aimPoint,
            Vec3 direction,
            double distanceBlocks,
            double angleOffNoseDeg,
            boolean lineOfSight,
            boolean attackingPilot,
            boolean explicitFactionHostile,
            String targetFaction,
            double score
    ) {
        String description() {
            return targetType
                    + ":uuid=" + targetUuid
                    + ":distance=" + round(distanceBlocks)
                    + ":angle=" + round(angleOffNoseDeg)
                    + ":los=" + lineOfSight
                    + ":attacking_pilot=" + attackingPilot
                    + ":explicit_faction_hostile=" + explicitFactionHostile
                    + ":target_faction=" + targetFaction
                    + ":score=" + round(score);
        }

        private static double round(double value) {
            return Math.rint(value * 10.0) / 10.0;
        }
    }
}
