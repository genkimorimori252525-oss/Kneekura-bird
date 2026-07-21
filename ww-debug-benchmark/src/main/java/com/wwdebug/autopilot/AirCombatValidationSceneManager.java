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

/** Injects finite moving air targets into the straight and crossing dogfight GameTests. */
final class AirCombatValidationSceneManager {
    private static final String SCENARIO_PROPERTY = "wwdebug.flightGameTestScenario";
    private static final String STRAIGHT_SCENARIO = "dogfight";
    private static final String CROSSING_SCENARIO = "dogfight_crossing";
    private static final String TEST_NAME_PREFIX = "AUTOPILOT TEST ";
    private static final String AIR_TARGET_TAG = "wwcombat:air_target";
    private static final int STRAIGHT_COMBAT_WINDOW_TICKS = 620;
    private static final int CROSSING_COMBAT_WINDOW_TICKS = 300;
    private static final Map<UUID, Scene> SCENES = new ConcurrentHashMap<>();

    private AirCombatValidationSceneManager() {
    }

    static void tick(ServerLevel level, Entity aircraft, FlightPhase phase) {
        String requested = System.getProperty(SCENARIO_PROPERTY, "").trim().toLowerCase();
        Geometry geometry = switch (requested) {
            case STRAIGHT_SCENARIO -> Geometry.STRAIGHT;
            case CROSSING_SCENARIO -> Geometry.CROSSING;
            default -> null;
        };
        if (geometry == null || !aircraft.getName().getString().startsWith(TEST_NAME_PREFIX)) {
            return;
        }
        Scene scene = SCENES.computeIfAbsent(aircraft.getUUID(), ignored -> new Scene(geometry));
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

        Entity target = scene.target;
        if (target == null || target.isRemoved()) {
            finish(level, aircraft, scene, phase, "moving_target_removed_before_window_end");
            return;
        }
        scene.ageTicks++;
        double vertical = scene.geometry == Geometry.STRAIGHT && scene.ageTicks > 220
                ? Math.sin(scene.ageTicks * 0.055) * 0.018 : 0.0;
        Vec3 commandedVelocity = scene.direction.scale(scene.speedBps / 20.0)
                .add(0.0, vertical, 0.0);
        // No-AI living targets retain delta movement for lead calculation but do not reliably
        // advance their world coordinates. Move every qualification target explicitly so the
        // visible path and the velocity used by the interceptor describe the same aircraft.
        target.moveTo(target.getX() + commandedVelocity.x,
                target.getY() + commandedVelocity.y,
                target.getZ() + commandedVelocity.z,
                yaw(scene.direction), 0.0f);
        target.setDeltaMovement(commandedVelocity);
        target.setNoGravity(true);
        target.fallDistance = 0.0f;

        int statusInterval = scene.geometry == Geometry.CROSSING ? 20 : 40;
        if (scene.ageTicks % statusInterval == 0) {
            Vec3 relativeToOrigin = target.position().subtract(scene.origin);
            double crossTrack = relativeToOrigin.dot(scene.rightAxis);
            double downrange = relativeToOrigin.dot(scene.forwardAxis);
            AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                    event(scene, "target_status"),
                    "target_uuid=" + target.getUUID()
                            + ":geometry=" + scene.geometry.logName
                            + ":age_ticks=" + scene.ageTicks
                            + ":distance=" + round(aircraft.distanceTo(target))
                            + ":cross_track=" + round(crossTrack)
                            + ":downrange=" + round(downrange)
                            + ":target_speed_bps=" + round(target.getDeltaMovement().length() * 20.0),
                    phase);
        }
        if (scene.ageTicks >= scene.combatWindowTicks) {
            target.discard();
            finish(level, aircraft, scene, phase, "combat_window_complete");
        }
    }

    private static void start(ServerLevel level, Entity aircraft, Scene scene, FlightPhase phase) {
        FlightProfile profile = AutopilotProfileRegistry.resolve(level.getServer(), aircraft).orElse(null);
        if (profile == null || !ReflectiveArmament.equipTestMachineGun(aircraft, 32)) {
            scene.completed = true;
            AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                    event(scene, "setup_failed"),
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

        Vec3 position;
        Vec3 direction;
        double targetSpeed;
        if (scene.geometry == Geometry.CROSSING) {
            position = aircraft.position().add(forward.scale(78.0))
                    .subtract(right.scale(44.0)).add(0.0, 5.0, 0.0);
            direction = forward.scale(0.32).add(right.scale(0.95)).normalize();
            targetSpeed = Math.max(profile.stallGuardSpeedBps() * 1.38,
                    profile.cruiseSpeedBps() * 0.66);
        } else {
            position = aircraft.position().add(forward.scale(96.0))
                    .add(right.scale(2.0)).add(0.0, 1.0, 0.0);
            direction = forward;
            targetSpeed = Math.max(profile.stallGuardSpeedBps() * 1.35,
                    profile.cruiseSpeedBps() * 0.72);
        }

        Zombie target = EntityType.ZOMBIE.create(level);
        if (target == null) {
            scene.completed = true;
            AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                    event(scene, "setup_failed"), "could_not_create_air_target", phase);
            return;
        }
        target.setNoAi(true);
        target.setNoGravity(true);
        target.setSilent(true);
        target.setInvulnerable(true);
        target.addTag(AIR_TARGET_TAG);
        target.moveTo(position.x, position.y, position.z, yaw(direction), 0.0f);
        target.setDeltaMovement(direction.scale(targetSpeed / 20.0));
        level.addFreshEntity(target);

        scene.started = true;
        scene.target = target;
        scene.direction = direction;
        scene.speedBps = targetSpeed;
        scene.ageTicks = 0;
        scene.origin = aircraft.position();
        scene.forwardAxis = forward;
        scene.rightAxis = right;
        AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                event(scene, "started"),
                "target_uuid=" + target.getUUID()
                        + ":geometry=" + scene.geometry.logName
                        + ":initial_distance=" + round(aircraft.distanceTo(target))
                        + ":initial_cross_track=" + round(position.subtract(scene.origin).dot(right))
                        + ":initial_downrange=" + round(position.subtract(scene.origin).dot(forward))
                        + ":crossing_angle_deg=" + round(angleDegrees(forward, direction))
                        + ":target_speed_bps=" + round(targetSpeed),
                phase);
    }

    private static void finish(ServerLevel level, Entity aircraft, Scene scene,
                               FlightPhase phase, String reason) {
        scene.completed = true;
        scene.target = null;
        AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                event(scene, "completed"),
                reason + ":geometry=" + scene.geometry.logName + ":age_ticks=" + scene.ageTicks,
                phase);
    }

    static void clear(UUID aircraftUuid) {
        Scene scene = SCENES.remove(aircraftUuid);
        if (scene != null && scene.target != null && !scene.target.isRemoved()) {
            scene.target.discard();
        }
    }

    private static String event(Scene scene, String suffix) {
        return scene.geometry == Geometry.CROSSING
                ? "crossing_dogfight_validation_" + suffix
                : "dogfight_validation_" + suffix;
    }

    private static float yaw(Vec3 direction) {
        return (float) Math.toDegrees(Math.atan2(-direction.x, direction.z));
    }

    private static double angleDegrees(Vec3 first, Vec3 second) {
        double dot = first.normalize().dot(second.normalize());
        return Math.toDegrees(Math.acos(Math.max(-1.0, Math.min(1.0, dot))));
    }

    private static Vec3 horizontal(Vec3 vector) {
        return new Vec3(vector.x, 0.0, vector.z);
    }

    private static double round(double value) {
        return Math.rint(value * 100.0) / 100.0;
    }

    private enum Geometry {
        STRAIGHT("straight", STRAIGHT_COMBAT_WINDOW_TICKS),
        CROSSING("crossing", CROSSING_COMBAT_WINDOW_TICKS);

        private final String logName;
        private final int combatWindowTicks;

        Geometry(String logName, int combatWindowTicks) {
            this.logName = logName;
            this.combatWindowTicks = combatWindowTicks;
        }
    }

    private static final class Scene {
        private final Geometry geometry;
        private final int combatWindowTicks;
        private Entity target;
        private Vec3 direction = Vec3.ZERO;
        private Vec3 origin = Vec3.ZERO;
        private Vec3 forwardAxis = new Vec3(0.0, 0.0, 1.0);
        private Vec3 rightAxis = new Vec3(1.0, 0.0, 0.0);
        private double speedBps;
        private int ageTicks;
        private boolean started;
        private boolean completed;

        private Scene(Geometry geometry) {
            this.geometry = geometry;
            this.combatWindowTicks = geometry.combatWindowTicks;
        }
    }
}
