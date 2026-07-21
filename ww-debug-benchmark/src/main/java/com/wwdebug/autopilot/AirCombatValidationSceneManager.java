package com.wwdebug.autopilot;

import com.wwdebug.benchmark.ReflectiveArmament;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.entity.monster.Zombie;
import net.minecraft.world.phys.Vec3;

import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/** Injects a finite moving air target into the dogfight GameTest and then releases the mission. */
final class AirCombatValidationSceneManager {
    private static final String SCENARIO_PROPERTY = "wwdebug.flightGameTestScenario";
    private static final String SCENARIO = "dogfight";
    private static final String TEST_NAME_PREFIX = "AUTOPILOT TEST ";
    private static final String AIR_TARGET_TAG = "wwcombat:air_target";
    private static final int COMBAT_WINDOW_TICKS = 620;
    private static final int TARGET_LOOKUP_GRACE_TICKS = 30;
    private static final Map<UUID, Scene> SCENES = new ConcurrentHashMap<>();

    private AirCombatValidationSceneManager() {
    }

    static void tick(ServerLevel level, Entity aircraft, FlightPhase phase) {
        if (!SCENARIO.equalsIgnoreCase(System.getProperty(SCENARIO_PROPERTY, ""))
                || !aircraft.getName().getString().startsWith(TEST_NAME_PREFIX)) {
            return;
        }
        Scene scene = SCENES.computeIfAbsent(aircraft.getUUID(), ignored -> new Scene());
        if (scene.completed) {
            return;
        }
        if (!scene.started) {
            if (phase != FlightPhase.CRUISE_OUTBOUND) {
                return;
            }
            start(level, aircraft, scene, phase);
            return;
        }

        Entity target = level.getEntity(scene.targetUuid);
        if (target == null || target.isRemoved()) {
            scene.missingTicks++;
            if (scene.missingTicks >= TARGET_LOOKUP_GRACE_TICKS) {
                finish(level, aircraft, scene, phase, "moving_target_missing_after_grace");
            }
            return;
        }
        scene.missingTicks = 0;
        scene.ageTicks++;
        // Preserve a predictable straight target during the first doctrine milestone. A tiny
        // vertical sine wave later exercises lead prediction without turning this into evasion AI.
        double vertical = scene.ageTicks > 220 ? Math.sin(scene.ageTicks * 0.055) * 0.018 : 0.0;
        target.setDeltaMovement(scene.direction.scale(scene.speedBps / 20.0).add(0.0, vertical, 0.0));
        target.setNoGravity(true);
        target.fallDistance = 0.0f;

        if (scene.ageTicks % 40 == 0) {
            AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                    "dogfight_validation_target_status",
                    "target_uuid=" + target.getUUID()
                            + ":age_ticks=" + scene.ageTicks
                            + ":distance=" + round(aircraft.distanceTo(target))
                            + ":target_speed_bps=" + round(target.getDeltaMovement().length() * 20.0),
                    phase);
        }
        if (scene.ageTicks >= COMBAT_WINDOW_TICKS) {
            target.discard();
            finish(level, aircraft, scene, phase, "combat_window_complete");
        }
    }

    private static void start(ServerLevel level, Entity aircraft, Scene scene, FlightPhase phase) {
        FlightProfile profile = AutopilotProfileRegistry.resolve(level.getServer(), aircraft).orElse(null);
        if (profile == null || !ReflectiveArmament.equipTestMachineGun(aircraft, 32)) {
            scene.completed = true;
            AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                    "dogfight_validation_setup_failed",
                    profile == null ? "missing_profile" : "could_not_equip_machine_gun",
                    phase);
            return;
        }
        Vec3 forward = horizontal(aircraft.getLookAngle());
        if (forward.lengthSqr() < 1.0e-8) {
            forward = horizontal(aircraft.getDeltaMovement());
        }
        if (forward.lengthSqr() < 1.0e-8) {
            forward = new Vec3(0.0, 0.0, 1.0);
        }
        forward = forward.normalize();
        Vec3 right = new Vec3(-forward.z, 0.0, forward.x).normalize();
        Vec3 position = aircraft.position().add(forward.scale(180.0))
                .add(right.scale(18.0)).add(0.0, 6.0, 0.0);

        Zombie target = EntityType.ZOMBIE.create(level);
        if (target == null) {
            scene.completed = true;
            AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                    "dogfight_validation_setup_failed", "could_not_create_air_target", phase);
            return;
        }
        target.setNoAi(true);
        target.setNoGravity(true);
        target.setSilent(true);
        target.setInvulnerable(true);
        target.addTag(AIR_TARGET_TAG);
        target.moveTo(position.x, position.y, position.z, aircraft.getYRot(), 0.0f);
        double targetSpeed = Math.max(profile.stallGuardSpeedBps() * 1.35,
                profile.cruiseSpeedBps() * 0.72);
        target.setDeltaMovement(forward.scale(targetSpeed / 20.0));
        level.addFreshEntity(target);

        scene.started = true;
        scene.targetUuid = target.getUUID();
        scene.direction = forward;
        scene.speedBps = targetSpeed;
        scene.ageTicks = 0;
        scene.missingTicks = 0;
        AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                "dogfight_validation_started",
                "target_uuid=" + target.getUUID()
                        + ":initial_distance=" + round(aircraft.distanceTo(target))
                        + ":lateral_offset=18.0"
                        + ":vertical_offset=6.0"
                        + ":target_speed_bps=" + round(targetSpeed),
                phase);
    }

    private static void finish(ServerLevel level, Entity aircraft, Scene scene,
                               FlightPhase phase, String reason) {
        scene.completed = true;
        AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                "dogfight_validation_completed",
                reason + ":age_ticks=" + scene.ageTicks, phase);
    }

    static void clear(UUID aircraftUuid) {
        SCENES.remove(aircraftUuid);
    }

    private static Vec3 horizontal(Vec3 vector) {
        return new Vec3(vector.x, 0.0, vector.z);
    }

    private static double round(double value) {
        return Math.rint(value * 100.0) / 100.0;
    }

    private static final class Scene {
        private UUID targetUuid;
        private Vec3 direction = Vec3.ZERO;
        private double speedBps;
        private int ageTicks;
        private int missingTicks;
        private boolean started;
        private boolean completed;
    }
}
