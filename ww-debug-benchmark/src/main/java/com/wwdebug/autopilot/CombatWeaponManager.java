package com.wwdebug.autopilot;

import com.wwdebug.benchmark.ReflectiveArmament;
import com.wwdebug.benchmark.ReflectiveAircraft;
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

/**
 * Server-side fighter weapon policy using the installed aircraft's normal fireWeapon API.
 *
 * <p>Firing requires a hostile solution, line of sight, a narrow nose angle, a safe range,
 * no protected living entity in the shot corridor, no immediate terrain conflict and available
 * ammunition. The policy uses two-volley bursts at the same four-tick cadence as the native
 * Warfare Wings machine-gun client logic.</p>
 */
public final class CombatWeaponManager {
    private static final Map<UUID, State> STATES = new ConcurrentHashMap<>();
    private static final int SHOT_INTERVAL_TICKS = 4;
    private static final int VOLLEYS_PER_BURST = 2;
    private static final int BURST_COOLDOWN_TICKS = 18;
    private static final double MIN_RANGE_BLOCKS = 18.0;
    private static final double MAX_RANGE_BLOCKS = 135.0;
    private static final double MAX_ANGLE_OFF_NOSE_DEG = 3.0;
    private static final double MAX_RAW_TARGET_ANGLE_DEG = 45.0;

    private CombatWeaponManager() {
    }

    public static void tick(Entity aircraft) {
        if (aircraft.level().isClientSide) {
            return;
        }
        if (!ReflectiveAircraft.isAirplane(aircraft)
                || !(aircraft.level() instanceof ServerLevel level)) {
            clear(aircraft.getUUID());
            return;
        }
        if (!MobPilotGate.isMobPiloted(aircraft)
                || AutonomousFlightManager.status(aircraft.getUUID()).isEmpty()) {
            clear(aircraft.getUUID());
            return;
        }

        State state = STATES.computeIfAbsent(aircraft.getUUID(), ignored -> new State());
        if (state.cooldownTicks > 0) {
            state.cooldownTicks--;
        }
        if (state.shotDelayTicks > 0) {
            state.shotDelayTicks--;
        }

        Optional<CombatTargetSelector.Solution> selected =
                CombatAwarenessManager.currentSolution(aircraft.getUUID());
        if (selected.isEmpty()) {
            state.cancelBurst();
            state.inhibit(level, aircraft, "no_hostile_target");
            return;
        }
        CombatTargetSelector.Solution solution = selected.get();
        Optional<AirCombatManeuverManager.AimSolution> tacticalAim =
                AirCombatManeuverManager.currentAim(aircraft.getUUID(), solution.targetUuid());
        Vec3 firingDirection = tacticalAim.map(AirCombatManeuverManager.AimSolution::direction)
                .orElse(solution.direction());
        double firingDistance = tacticalAim.map(AirCombatManeuverManager.AimSolution::distanceBlocks)
                .orElse(solution.distanceBlocks());
        double firingAngle = tacticalAim.map(AirCombatManeuverManager.AimSolution::angleOffNoseDeg)
                .orElse(solution.angleOffNoseDeg());

        Optional<AutonomousFlightManager.SessionStatus> status =
                AutonomousFlightManager.status(aircraft.getUUID());
        if (status.isEmpty() || !combatPhase(status.get().phase())) {
            state.cancelBurst();
            state.inhibit(level, aircraft, "weapons_disabled_in_flight_phase");
            return;
        }
        if (unsafeTerrainAhead(aircraft)) {
            state.cancelBurst();
            state.inhibit(level, aircraft, "immediate_terrain_conflict_has_priority");
            return;
        }
        if (!solution.lineOfSight()) {
            state.cancelBurst();
            state.inhibit(level, aircraft, "target_line_of_sight_blocked");
            return;
        }
        if (firingDistance < MIN_RANGE_BLOCKS || firingDistance > MAX_RANGE_BLOCKS) {
            state.cancelBurst();
            state.inhibit(level, aircraft, "target_outside_machine_gun_range");
            return;
        }
        if (firingAngle > MAX_ANGLE_OFF_NOSE_DEG) {
            state.cancelBurst();
            state.inhibit(level, aircraft, "target_outside_nose_firing_cone");
            return;
        }
        // A valid projectile intercept can mathematically lie ahead even after the target has
        // crossed behind a fixed-gun fighter. Do not fire through that solution unless the actual
        // target is still inside a broad forward hemisphere; the aircraft must first turn back in.
        if (solution.angleOffNoseDeg() > MAX_RAW_TARGET_ANGLE_DEG) {
            state.cancelBurst();
            state.inhibit(level, aircraft, "target_currently_outside_forward_gun_hemisphere");
            return;
        }

        Entity targetEntity = level.getEntity(solution.targetUuid());
        if (!(targetEntity instanceof LivingEntity target) || !target.isAlive()) {
            state.cancelBurst();
            state.inhibit(level, aircraft, "selected_target_missing");
            return;
        }
        Optional<LivingEntity> protectedEntity = protectedEntityInCorridor(level, aircraft, target);
        if (protectedEntity.isPresent()) {
            state.cancelBurst();
            LivingEntity blocker = protectedEntity.get();
            state.inhibit(level, aircraft,
                    "friendly_fire_corridor_blocked_by=" + blocker.getType());
            return;
        }

        List<ReflectiveArmament.MountedWeapon> weapons = ReflectiveArmament.machineGuns(aircraft).stream()
                .filter(weapon -> weapon.gunnerOffset() == 0)
                .toList();
        if (weapons.isEmpty()) {
            state.cancelBurst();
            state.inhibit(level, aircraft, "no_pilot_controlled_machine_gun");
            return;
        }
        int shotsRemaining = ReflectiveArmament.estimatedShotsRemaining(aircraft);
        if (shotsRemaining <= 0) {
            state.cancelBurst();
            if (!state.outOfAmmoLogged) {
                state.outOfAmmoLogged = true;
                AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                        "weapon_out_of_ammo",
                        "machine_guns=" + weapons.size(), status.get().phase());
            }
            return;
        }
        state.outOfAmmoLogged = false;
        state.lastInhibitReason = null;

        if (state.volleysRemaining <= 0) {
            if (state.cooldownTicks > 0) {
                return;
            }
            state.volleysRemaining = VOLLEYS_PER_BURST;
            state.shotDelayTicks = 0;
            AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                    "weapon_burst_start",
                    solution.description() + ":weapons=" + weapons.size()
                            + ":estimated_shots=" + shotsRemaining
                            + ":lead=" + tacticalAim.isPresent(),
                    status.get().phase());
        }
        if (state.shotDelayTicks > 0) {
            return;
        }

        int fired = 0;
        int loadedBefore = 0;
        int loadedAfter = 0;
        int reserveBefore = ReflectiveArmament.reserveGunpowder(aircraft);
        int reserveAfter = reserveBefore;
        for (ReflectiveArmament.MountedWeapon weapon : weapons) {
            ReflectiveArmament.FireResult result = ReflectiveArmament.fire(
                    aircraft, weapon, firingDirection);
            loadedBefore += Math.max(0, result.loadedAmmoBefore());
            loadedAfter += Math.max(0, result.loadedAmmoAfter());
            reserveAfter = result.reserveAfter();
            boolean ammunitionChanged = result.reserveAfter() < result.reserveBefore()
                    || (result.loadedAmmoBefore() >= 0
                    && result.loadedAmmoAfter() >= 0
                    && result.loadedAmmoAfter() < result.loadedAmmoBefore());
            if (result.invoked() && ammunitionChanged) {
                fired++;
            }
        }

        if (fired <= 0) {
            state.cancelBurst();
            state.inhibit(level, aircraft, "weapon_api_invoked_without_ammunition_consumption");
            return;
        }

        AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                "weapon_fire",
                "target_uuid=" + solution.targetUuid()
                        + ":distance=" + round(firingDistance)
                        + ":angle=" + round(firingAngle)
                        + ":raw_distance=" + round(solution.distanceBlocks())
                        + ":raw_angle=" + round(solution.angleOffNoseDeg())
                        + ":lead_seconds=" + tacticalAim
                        .map(AirCombatManeuverManager.AimSolution::timeSeconds).map(CombatWeaponManager::round)
                        .orElse(0.0)
                        + ":weapons_fired=" + fired
                        + ":loaded_before=" + loadedBefore
                        + ":loaded_after=" + loadedAfter
                        + ":reserve_before=" + reserveBefore
                        + ":reserve_after=" + reserveAfter,
                status.get().phase());

        state.volleysRemaining--;
        state.shotDelayTicks = SHOT_INTERVAL_TICKS;
        if (state.volleysRemaining <= 0) {
            state.cooldownTicks = BURST_COOLDOWN_TICKS;
            AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                    "weapon_burst_end",
                    "cooldown_ticks=" + BURST_COOLDOWN_TICKS,
                    status.get().phase());
        }
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
        double lookAhead = Mth.clamp(aircraft.getDeltaMovement().horizontalDistance() * 20.0 * 2.5,
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
        return Math.rint(value * 10.0) / 10.0;
    }

    public static void clear(UUID aircraftUuid) {
        STATES.remove(aircraftUuid);
    }

    private static final class State {
        private int volleysRemaining;
        private int shotDelayTicks;
        private int cooldownTicks;
        private String lastInhibitReason;
        private boolean outOfAmmoLogged;

        private void cancelBurst() {
            volleysRemaining = 0;
            shotDelayTicks = 0;
        }

        private void inhibit(ServerLevel level, Entity aircraft, String reason) {
            if (reason.equals(lastInhibitReason)) {
                return;
            }
            lastInhibitReason = reason;
            FlightPhase phase = AutonomousFlightManager.status(aircraft.getUUID())
                    .map(AutonomousFlightManager.SessionStatus::phase)
                    .orElse(FlightPhase.ABORTED);
            AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                    "weapon_fire_inhibited", reason, phase);
        }
    }
}
