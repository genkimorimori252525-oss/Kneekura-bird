package com.wwdebug.autopilot;

import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.phys.Vec3;

import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/** Moves the neutral test entity out of the firing corridor after an initial inhibit period. */
final class CombatValidationSceneManager {
    private static final Map<UUID, Scene> SCENES = new ConcurrentHashMap<>();
    private static final long FRIENDLY_BLOCK_TICKS = 4L;

    private CombatValidationSceneManager() {
    }

    static void register(Entity aircraft, Entity neutral, Entity hostile, Vec3 lateralDirection) {
        SCENES.put(aircraft.getUUID(), new Scene(
                neutral.getUUID(), hostile.getUUID(), lateralDirection.normalize(),
                aircraft.level().getGameTime(), false));
    }

    static void tick(ServerLevel level, Entity aircraft) {
        Scene scene = SCENES.get(aircraft.getUUID());
        if (scene == null || scene.cleared
                || level.getGameTime() - scene.startedAt < FRIENDLY_BLOCK_TICKS) {
            return;
        }
        Entity neutral = level.getEntity(scene.neutralUuid);
        if (neutral != null) {
            Vec3 destination = neutral.position().add(scene.lateralDirection.scale(34.0));
            neutral.moveTo(destination.x, destination.y, destination.z,
                    neutral.getYRot(), neutral.getXRot());
        }
        scene.cleared = true;
        FlightPhase phase = AutonomousFlightManager.status(aircraft.getUUID())
                .map(AutonomousFlightManager.SessionStatus::phase)
                .orElse(FlightPhase.ABORTED);
        AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                "friendly_fire_corridor_cleared",
                "neutral_moved_after_ticks=" + FRIENDLY_BLOCK_TICKS
                        + ":hostile_uuid=" + scene.hostileUuid,
                phase);
    }

    static void clear(UUID aircraftUuid) {
        SCENES.remove(aircraftUuid);
    }

    private static final class Scene {
        private final UUID neutralUuid;
        private final UUID hostileUuid;
        private final Vec3 lateralDirection;
        private final long startedAt;
        private boolean cleared;

        private Scene(UUID neutralUuid, UUID hostileUuid, Vec3 lateralDirection,
                      long startedAt, boolean cleared) {
            this.neutralUuid = neutralUuid;
            this.hostileUuid = hostileUuid;
            this.lateralDirection = lateralDirection;
            this.startedAt = startedAt;
            this.cleared = cleared;
        }
    }
}
