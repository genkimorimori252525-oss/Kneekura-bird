package com.wwdebug.autopilot;

import com.wwdebug.benchmark.WWDebugBenchmarkMod;
import it.unimi.dsi.fastutil.longs.LongSet;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.gametest.framework.GameTestServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.level.ChunkPos;

import java.util.Set;
import java.util.UUID;

/** Observes only existing force-loop reads; never fetches a forced set or changes a ticket. */
final class MutualTicketObserver {
    private MutualTicketObserver() {
    }

    static final class Recorder {
        private String previous;

        Sample begin(ServerLevel level, Entity primary, Set<Long> owned, ChunkPos center) {
            try {
                if (!(level.getServer() instanceof GameTestServer)) return null;
                String option = System.getProperty("wwdebug.mutualObserveTickets");
                if (!"true".equals(option)) return null;
                var id = BuiltInRegistries.ENTITY_TYPE.getKey(primary.getType());
                if (!MutualTicketObservationPolicy.enabled(true,
                        System.getProperty("wwdebug.flightGameTestScenario", "full"),
                        System.getProperty("wwdebug.flightGameTestAircraft", "warfare_wings:a6m"),
                        id == null ? null : id.toString(), option)) return null;
                var target = MutualDogfightValidationManager.observationTarget(primary.getUUID());
                if (target == null) {
                    previous = null;
                    return null;
                }
                return new Sample(this, level, primary, owned, center, target);
            } catch (RuntimeException ignored) {
                // Failure to establish scope or capture a target is unobserved, not false.
                return null;
            }
        }
    }

    static final class Sample {
        private final Recorder recorder;
        private final ServerLevel level;
        private final Entity primary;
        private final Set<Long> owned;
        private final UUID opponentUuid;
        private final Entity reference;
        private final Long targetKey;
        private final ChunkPos center;
        private final Boolean sameLevel;
        private final Boolean removed;
        private final Boolean ownerBefore;
        private final Boolean rangeBefore;
        private Boolean firstRead;
        private Boolean lastRead;
        private Boolean targetForcedBefore;
        private Boolean setterResult;
        private boolean encountered;
        private boolean probeError;

        private Sample(Recorder recorder, ServerLevel level, Entity primary, Set<Long> owned, ChunkPos center,
                       MutualDogfightValidationManager.ObservationTarget target) {
            this.recorder = recorder;
            this.level = level;
            this.primary = primary;
            this.owned = owned;
            this.opponentUuid = target.opponentUuid();
            this.reference = target.reference();
            this.center = center;
            this.sameLevel = reference == null ? null : reference.level() == level;
            this.removed = reference == null ? null : reference.isRemoved();
            this.targetKey = Boolean.TRUE.equals(sameLevel) ? reference.chunkPosition().toLong() : null;
            this.ownerBefore = targetKey == null ? null : owned.contains(targetKey);
            this.rangeBefore = targetKey == null ? null : level.getChunkSource().chunkMap
                    .getDistanceManager().inEntityTickingRange(targetKey);
        }

        void read(LongSet existingView, long loopKey, boolean loopForced, int index) {
            try {
                if (targetKey == null) return;
                if (index == 0) firstRead = existingView.contains(targetKey.longValue());
                if (index == 48) lastRead = existingView.contains(targetKey.longValue());
                if (loopKey == targetKey.longValue()) {
                    encountered = true;
                    targetForcedBefore = loopForced;
                }
            } catch (RuntimeException ignored) {
                probeError = true;
            }
        }

        void attempted(long loopKey, boolean result) {
            if (targetKey != null && loopKey == targetKey.longValue()) setterResult = result;
        }

        void finish(boolean complete) {
            try {
                Boolean ownerAfter = targetKey == null ? null : owned.contains(targetKey);
                Boolean rangeAfter = targetKey == null ? null : level.getChunkSource().chunkMap
                        .getDistanceManager().inEntityTickingRange(targetKey);
                var current = MutualDogfightValidationManager.observationTarget(primary.getUUID());
                Entity endReference = current == null ? null : current.reference();
                String refAtEnd = current == null || reference == null || endReference == null ? "unknown"
                        : endReference == reference ? "same" : "different";
                ChunkPos target = targetKey == null ? null : new ChunkPos(targetKey);
                ChunkPos endChunk = endReference != null && endReference.level() == level
                        ? endReference.chunkPosition() : null;
                Boolean inRequest = target == null ? null : Math.abs((long) target.x - center.x) <= 3
                        && Math.abs((long) target.z - center.z) <= 3;
                String action = targetKey == null || probeError ? "unknown"
                        : MutualTicketObservationPolicy.action(encountered, complete, targetForcedBefore, setterResult);
                String details = "stage=end_force_loop:opponent_uuid=" + value(opponentUuid)
                        + ":reference_present=" + (reference != null)
                        + ":reference_uuid=" + (reference == null ? "unknown" : reference.getUUID())
                        + ":reference_same_level=" + MutualTicketObservationPolicy.state(sameLevel)
                        + ":reference_removed=" + MutualTicketObservationPolicy.state(removed)
                        + ":reference_at_end=" + refAtEnd
                        + ":target_chunk_x=" + (target == null ? "unknown" : target.x)
                        + ":target_chunk_z=" + (target == null ? "unknown" : target.z)
                        + ":end_reference_chunk_x=" + (endChunk == null ? "unknown" : endChunk.x)
                        + ":end_reference_chunk_z=" + (endChunk == null ? "unknown" : endChunk.z)
                        + ":primary_center_x=" + center.x + ":primary_center_z=" + center.z
                        + ":target_in_request=" + MutualTicketObservationPolicy.state(inRequest)
                        + ":owner_before=" + MutualTicketObservationPolicy.state(ownerBefore)
                        + ":owner_after=" + MutualTicketObservationPolicy.state(ownerAfter)
                        + ":forced_first_read=" + MutualTicketObservationPolicy.state(firstRead)
                        + ":forced_last_read_before_iteration_49=" + MutualTicketObservationPolicy.state(lastRead)
                        + ":forced_after_loop=unknown"
                        + ":range_before=" + MutualTicketObservationPolicy.state(rangeBefore)
                        + ":range_after=" + MutualTicketObservationPolicy.state(rangeAfter)
                        + ":target_action=" + action + ":loop_complete=" + complete
                        + ":probe_error=" + probeError;
                long tick = level.getServer().overworld().getGameTime();
                if (MutualTicketObservationPolicy.emit(recorder.previous, details, tick)) {
                    WWDebugBenchmarkMod.LOGGER.info("Mutual GameTest force observation server_tick={} primary_uuid={} {}",
                            tick, primary.getUUID(), details);
                    recorder.previous = details;
                }
            } catch (RuntimeException ignored) {
                // A missing observation is unknown; it must not change the validation loop.
            }
        }

        private static String value(UUID uuid) {
            return uuid == null ? "unknown" : uuid.toString();
        }
    }
}
