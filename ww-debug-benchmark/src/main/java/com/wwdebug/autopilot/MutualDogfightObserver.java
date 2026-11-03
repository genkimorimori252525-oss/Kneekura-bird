package com.wwdebug.autopilot;

import net.minecraft.core.BlockPos;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.gametest.framework.GameTestServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.Mob;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.phys.Vec3;

import java.util.UUID;

/** Opt-in GameTest diagnostic; queries only and never requests or forces a chunk. */
final class MutualDogfightObserver {
    private MutualDogfightObserver() {
    }

    static void observe(ServerLevel level, Entity primary, Entity reference, UUID opponentUuid,
                        FlightPhase phase, boolean initial) {
        String option;
        try {
            if (!(level.getServer() instanceof GameTestServer)) return;
            option = System.getProperty("wwdebug.mutualObserveEntity");
        } catch (RuntimeException ignored) {
            // No opt-in can be established; leave the original scenario alone.
            return;
        }
        if (!"true".equals(option)) return;

        String actualAircraft;
        try {
            var id = BuiltInRegistries.ENTITY_TYPE.getKey(primary.getType());
            actualAircraft = id == null ? null : id.toString();
        } catch (RuntimeException ignored) {
            // An unavailable registry ID cannot establish that the primary is the A6M.
            return;
        }

        try {
            if (!MutualDogfightObservationPolicy.enabled(true,
                    System.getProperty("wwdebug.flightGameTestScenario", "full"),
                    System.getProperty("wwdebug.flightGameTestAircraft", "warfare_wings:a6m"),
                    actualAircraft, option)) return;
        } catch (RuntimeException ignored) {
            // The requested scope could not be established, so emit nothing.
            return;
        }

        try {
            long tick = level.getServer().overworld().getGameTime();
            if (!initial && !MutualDogfightObservationPolicy.sample(true, tick)) return;
            Entity visible = opponentUuid == null ? null : level.getEntity(opponentUuid);
            Vec3 primaryPosition = primary.position();
            StringBuilder reason = new StringBuilder("stage=")
                    .append(MutualDogfightObservationPolicy.stage(initial))
                    .append(":primary_tick_count=").append(primary.tickCount)
                    .append(":primary_x=").append(primaryPosition.x)
                    .append(":primary_y=").append(primaryPosition.y)
                    .append(":primary_z=").append(primaryPosition.z)
                    .append(":opponent_uuid=").append(opponentUuid == null ? "unknown" : opponentUuid)
                    .append(":lookup_present=").append(MutualDogfightObservationPolicy.state(
                            opponentUuid == null ? null : visible != null))
                    .append(":lookup_vs_reference=").append(opponentUuid == null ? "unknown"
                            : MutualDogfightObservationPolicy.lookup(reference, visible))
                    .append(":visible_uuid=").append(visible == null ? "unknown" : visible.getUUID());
            appendReference(reason, level, reference);
            AutopilotLogManager.writeEvent(level.getServer(), primary,
                    "mutual_dogfight_entity_observation", reason.toString(), phase);
        } catch (RuntimeException exception) {
            // Do not make diagnostic failures change the scenario; missing fields are unknown.
            try {
                AutopilotLogManager.writeEvent(level.getServer(), primary,
                        "mutual_dogfight_entity_observation_error",
                        "stage=" + MutualDogfightObservationPolicy.stage(initial)
                                + ":exception=" + exception.getClass().getSimpleName(), phase);
            } catch (RuntimeException ignored) {
                // A missing diagnostic is itself unverified; never alter the flight scenario.
            }
        }
    }

    private static void appendReference(StringBuilder reason, ServerLevel level, Entity reference) {
        if (reference == null) {
            reason.append(":reference_present=false:reference_same_level=unknown")
                    .append(":reference_uuid=unknown:reference_tick_count=unknown")
                    .append(":reference_removed=unknown:reference_added=unknown")
                    .append(":reference_x=unknown:reference_y=unknown:reference_z=unknown")
                    .append(":reference_chunk_x=unknown:reference_chunk_z=unknown")
                    .append(":controlling_passenger=unknown:passenger_uuid=unknown")
                    .append(":chunk_has_holder=unknown:chunk_entities_loaded=unknown")
                    .append(":position_entity_ticking=unknown:uuid_session_mission_ticks=unknown");
            return;
        }
        boolean sameLevel = reference.level() == level;
        Vec3 position = reference.position();
        BlockPos block = reference.blockPosition();
        int chunkX = block.getX() >> 4;
        int chunkZ = block.getZ() >> 4;
        Entity passenger = reference.getControllingPassenger();
        String passengerKind = passenger == null ? "none" : passenger instanceof Player ? "player"
                : passenger instanceof Mob ? "mob" : "other";
        var session = AutonomousFlightManager.status(reference.getUUID());
        reason.append(":reference_present=true:reference_same_level=").append(sameLevel)
                .append(":reference_uuid=").append(reference.getUUID())
                .append(":reference_tick_count=").append(reference.tickCount)
                .append(":reference_removed=").append(reference.isRemoved())
                .append(":reference_added=").append(reference.isAddedToWorld())
                .append(":reference_x=").append(position.x)
                .append(":reference_y=").append(position.y)
                .append(":reference_z=").append(position.z)
                .append(":reference_chunk_x=").append(chunkX)
                .append(":reference_chunk_z=").append(chunkZ)
                .append(":controlling_passenger=").append(passengerKind)
                .append(":passenger_uuid=").append(passenger == null ? "none" : passenger.getUUID())
                .append(":chunk_has_holder=").append(MutualDogfightObservationPolicy.state(
                        sameLevel ? level.getChunkSource().hasChunk(chunkX, chunkZ) : null))
                .append(":chunk_entities_loaded=").append(MutualDogfightObservationPolicy.state(
                        sameLevel ? level.areEntitiesLoaded(ChunkPos.asLong(chunkX, chunkZ)) : null))
                .append(":position_entity_ticking=").append(MutualDogfightObservationPolicy.state(
                        sameLevel ? level.isPositionEntityTicking(block) : null))
                .append(":uuid_session_mission_ticks=").append(session.isPresent()
                        ? Integer.toString(session.get().missionTicks()) : "unknown");
    }
}
