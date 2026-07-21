package com.wwdebug.autopilot;

import com.wwdebug.benchmark.ReflectiveAircraft;
import com.wwdebug.benchmark.ReflectiveArmament;
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

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/** Records the exact fixed-gun gate inputs without changing weapon behavior. */
public final class CombatWeaponGateTelemetry {
    private static final double MIN_RANGE_BLOCKS = 18.0;
    private static final double MAX_RANGE_BLOCKS = 135.0;
    private static final double MAX_ANGLE_OFF_NOSE_DEG = 3.0;
    private static final double MAX_RAW_TARGET_ANGLE_DEG = 45.0;
    private static final Map<UUID, State> STATES = new ConcurrentHashMap<>();

    private CombatWeaponGateTelemetry() {
    }

    public static void tick(Entity aircraft) {
        if (aircraft.level().isClientSide || !(aircraft.level() instanceof ServerLevel level)
                || !ReflectiveAircraft.isAirplane(aircraft)) {
            STATES.remove(aircraft.getUUID());
            return;
        }
        Optional<AutonomousFlightManager.SessionStatus> status =
                AutonomousFlightManager.status(aircraft.getUUID());
        Optional<CombatTargetSelector.Solution> selected =
                CombatAwarenessManager.currentSolution(aircraft.getUUID());
        if (status.isEmpty() || selected.isEmpty()) {
            STATES.remove(aircraft.getUUID());
            return;
        }

        CombatTargetSelector.Solution solution = selected.get();
        Optional<AirCombatManeuverManager.AimSolution> tacticalAim =
                AirCombatManeuverManager.currentAim(aircraft.getUUID(), solution.targetUuid());
        double firingDistance = tacticalAim
                .map(AirCombatManeuverManager.AimSolution::distanceBlocks)
                .orElse(solution.distanceBlocks());
        double firingAngle = tacticalAim
                .map(AirCombatManeuverManager.AimSolution::angleOffNoseDeg)
                .orElse(solution.angleOffNoseDeg());
        Entity targetEntity = level.getEntity(solution.targetUuid());
        LivingEntity target = targetEntity instanceof LivingEntity living ? living : null;
        Optional<LivingEntity> blocker = target == null
                ? Optional.empty() : protectedEntityInCorridor(level, aircraft, target);
        int weaponCount = ReflectiveArmament.machineGuns(aircraft).stream()
                .filter(weapon -> weapon.gunnerOffset() == 0).toList().size();
        int shotsRemaining = ReflectiveArmament.estimatedShotsRemaining(aircraft);
        boolean terrainConflict = unsafeTerrainAhead(aircraft);

        String gate = firstFailedGate(status.get().phase(), solution, firingDistance,
                firingAngle, terrainConflict, target, blocker, weaponCount, shotsRemaining);
        State state = STATES.computeIfAbsent(aircraft.getUUID(), ignored -> new State());
        boolean interesting = firingDistance <= 180.0 || firingAngle <= 20.0;
        boolean changed = !gate.equals(state.lastGate);
        if ((interesting && state.statusTicks++ % 5 == 0) || changed) {
            state.lastGate = gate;
            String description = "gate=" + gate
                    + ":tactical_aim=" + tacticalAim.isPresent()
                    + ":firing_distance=" + round(firingDistance)
                    + ":firing_angle=" + round(firingAngle)
                    + ":raw_distance=" + round(solution.distanceBlocks())
                    + ":raw_angle=" + round(solution.angleOffNoseDeg())
                    + ":line_of_sight=" + solution.lineOfSight()
                    + ":terrain_conflict=" + terrainConflict
                    + ":target_alive=" + (target != null && target.isAlive())
                    + ":protected_blocker=" + blocker
                    .map(entity -> entity.getType().toString()).orElse("none")
                    + ":pilot_weapon_count=" + weaponCount
                    + ":shots_remaining=" + shotsRemaining;
            AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                    "weapon_gate_status", description, status.get().phase());
        }
    }

    private static String firstFailedGate(FlightPhase phase,
                                          CombatTargetSelector.Solution solution,
                                          double firingDistance, double firingAngle,
                                          boolean terrainConflict, LivingEntity target,
                                          Optional<LivingEntity> blocker,
                                          int weaponCount, int shotsRemaining) {
        if (!combatPhase(phase)) {
            return "weapons_disabled_in_flight_phase";
        }
        if (terrainConflict) {
            return "immediate_terrain_conflict_has_priority";
        }
        if (!solution.lineOfSight()) {
            return "target_line_of_sight_blocked";
        }
        if (firingDistance < MIN_RANGE_BLOCKS || firingDistance > MAX_RANGE_BLOCKS) {
            return "target_outside_machine_gun_range";
        }
        if (firingAngle > MAX_ANGLE_OFF_NOSE_DEG) {
            return "target_outside_nose_firing_cone";
        }
        if (solution.angleOffNoseDeg() > MAX_RAW_TARGET_ANGLE_DEG) {
            return "target_currently_outside_forward_gun_hemisphere";
        }
        if (target == null || !target.isAlive()) {
            return "selected_target_missing";
        }
        if (blocker.isPresent()) {
            return "friendly_fire_corridor_blocked";
        }
        if (weaponCount <= 0) {
            return "no_pilot_controlled_machine_gun";
        }
        if (shotsRemaining <= 0) {
            return "out_of_ammo";
        }
        return "ready_to_fire";
    }

    private static boolean combatPhase(FlightPhase phase) {
        return phase.isAirborneMissionPhase()
                && !phase.isLandingPhase()
                && phase != FlightPhase.STALL_ENTRY
                && phase != FlightPhase.STALL_RECOVERY;
    }

    private static boolean unsafeTerrainAhead(Entity aircraft) {
        Vec3 start = aircraft.getBoundingBox().getCenter();
        Vec3 forward = aircraft.getLookAngle().normalize();
        double lookAhead = Mth.clamp(
                aircraft.getDeltaMovement().horizontalDistance() * 20.0 * 2.5,
                36.0, 96.0);
        Vec3 end = start.add(forward.scale(lookAhead));
        BlockHitResult hit = aircraft.level().clip(new ClipContext(
                start, end, ClipContext.Block.COLLIDER, ClipContext.Fluid.NONE, aircraft));
        return hit.getType() != HitResult.Type.MISS;
    }

    private static Optional<LivingEntity> protectedEntityInCorridor(ServerLevel level,
                                                                     Entity aircraft,
                                                                     LivingEntity target) {
        Vec3 start = aircraft.getBoundingBox().getCenter();
        Vec3 end = target.getEyePosition();
        AABB corridor = new AABB(start, end).inflate(3.0);
        LivingEntity pilot = aircraft.getControllingPassenger();
        List<LivingEntity> candidates = new ArrayList<>(level.getEntitiesOfClass(
                LivingEntity.class,
                corridor,
                candidate -> candidate.isAlive() && candidate != target && candidate != pilot
                        && candidate != aircraft && !aircraft.hasPassenger(candidate)
        ));
        for (LivingEntity candidate : candidates) {
            if (!protectedFromFire(aircraft, pilot, candidate)) {
                continue;
            }
            double radius = Math.max(1.25, candidate.getBbWidth() * 0.5 + 0.8);
            if (distanceToSegment(candidate.getBoundingBox().getCenter(), start, end) <= radius) {
                return Optional.of(candidate);
            }
        }
        return Optional.empty();
    }

    private static boolean protectedFromFire(Entity aircraft, LivingEntity pilot,
                                              LivingEntity candidate) {
        if (candidate instanceof Player) {
            return true;
        }
        if (candidate instanceof TamableAnimal tame && tame.isTame()) {
            return true;
        }
        if (aircraft.isAlliedTo(candidate) || pilot.isAlliedTo(candidate)
                || candidate.isAlliedTo(pilot)
                || CombatFactionRelations.protectedFromFire(aircraft, pilot, candidate)) {
            return true;
        }
        return !(candidate instanceof Enemy)
                && !(candidate instanceof Mob mob && mob.getTarget() == pilot);
    }

    private static double distanceToSegment(Vec3 point, Vec3 start, Vec3 end) {
        Vec3 segment = end.subtract(start);
        double lengthSquared = segment.lengthSqr();
        if (lengthSquared < 1.0e-8) {
            return point.distanceTo(start);
        }
        double t = Mth.clamp(point.subtract(start).dot(segment) / lengthSquared, 0.0, 1.0);
        return point.distanceTo(start.add(segment.scale(t)));
    }

    private static double round(double value) {
        return Math.rint(value * 100.0) / 100.0;
    }

    private static final class State {
        private String lastGate = "";
        private int statusTicks;
    }
}
