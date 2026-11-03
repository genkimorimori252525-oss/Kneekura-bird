package com.wwdebug.autopilot;

import com.wwdebug.benchmark.WWDebugBenchmarkMod;
import it.unimi.dsi.fastutil.longs.LongSet;
import net.minecraft.SharedConstants;
import net.minecraft.core.BlockPos;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.gametest.framework.GameTestServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.level.ChunkPos;
import net.minecraftforge.versions.forge.ForgeVersion;

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
                boolean visibilityEnabled = false;
                try {
                    visibilityEnabled = MutualTicketObservationPolicy.visibilityEnabled(
                            System.getProperty("wwdebug.mutualObserveVisibility"));
                } catch (RuntimeException ignored) {
                    // Without a confirmed opt-in, retain the existing ticket observation.
                }
                boolean directRequested = false;
                if (visibilityEnabled) {
                    try {
                        directRequested = "true".equals(System.getProperty("wwdebug.mutualObserveDirectVisibility"));
                    } catch (RuntimeException ignored) {
                        // Without confirmed opt-in, retain the prior visibility observation.
                    }
                }
                return new Sample(this, level, primary, owned, center, target, visibilityEnabled, directRequested);
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
        private final boolean visibilityEnabled;
        private final BlockPos targetBlock;
        private final Boolean blockChunkMatches;
        private final Boolean compositeBefore;
        private final Long beforeQueryTick;
        private final Long beforeQueryEndTick;
        private final boolean directRequested;
        private final String directScope;
        private final String minecraftVersion;
        private final String forgeVersion;
        private final boolean exactLevel;
        private final Boolean directBeforeRaw;
        private final Long directBeforeTick;
        private final Long directBeforeEndTick;
        private boolean directProbeError;
        private boolean visibilityProbeError;
        private Boolean firstRead;
        private Boolean lastRead;
        private Boolean targetForcedBefore;
        private Boolean setterResult;
        private boolean encountered;
        private boolean probeError;

        private Sample(Recorder recorder, ServerLevel level, Entity primary, Set<Long> owned, ChunkPos center,
                       MutualDogfightValidationManager.ObservationTarget target, boolean visibilityEnabled,
                       boolean directRequested) {
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
            this.visibilityEnabled = visibilityEnabled;
            BlockPos block = null;
            Boolean matches = null;
            if (visibilityEnabled && targetKey != null) {
                try {
                    block = reference.blockPosition().immutable();
                    matches = ChunkPos.asLong(block) == targetKey.longValue();
                } catch (RuntimeException ignored) {
                    visibilityProbeError = true;
                }
            }
            this.targetBlock = block;
            this.blockChunkMatches = matches;
            this.directRequested = directRequested;
            this.exactLevel = directRequested && level.getClass() == ServerLevel.class;
            String minecraft = null;
            String forge = null;
            String scope = "unknown";
            if (directRequested) {
                try {
                    minecraft = SharedConstants.getCurrentVersion().getName();
                    forge = ForgeVersion.getVersion();
                    if (minecraft != null && forge != null) {
                        scope = MutualTicketObservationPolicy.directVisibilityEnabled(visibilityEnabled, "true",
                                exactLevel, minecraft, forge) ? "supported" : "unsupported";
                    }
                } catch (RuntimeException | LinkageError ignored) {
                    directProbeError = true;
                }
            }
            this.minecraftVersion = minecraft;
            this.forgeVersion = forge;
            this.directScope = scope;
            this.beforeQueryTick = visibilityEnabled ? queryTick() : null;
            this.rangeBefore = visibilityEnabled ? safeRange() : targetKey == null ? null : level.getChunkSource().chunkMap
                    .getDistanceManager().inEntityTickingRange(targetKey);
            this.compositeBefore = visibilityEnabled ? safeComposite() : null;
            this.beforeQueryEndTick = visibilityEnabled ? queryTick() : null;
            this.directBeforeTick = directRequested ? directTick() : null;
            this.directBeforeRaw = directRequested ? safeDirectVisibility() : null;
            this.directBeforeEndTick = directRequested ? directTick() : null;
        }

        private Boolean safeRange() {
            if (targetKey == null) return null;
            try {
                return level.getChunkSource().chunkMap.getDistanceManager().inEntityTickingRange(targetKey);
            } catch (RuntimeException ignored) {
                visibilityProbeError = true;
                return null;
            }
        }

        private Boolean safeComposite() {
            if (targetBlock == null || !Boolean.TRUE.equals(blockChunkMatches)) return null;
            try {
                return level.isPositionEntityTicking(targetBlock);
            } catch (RuntimeException ignored) {
                visibilityProbeError = true;
                return null;
            }
        }

        private Long queryTick() {
            try {
                return level.getServer().overworld().getGameTime();
            } catch (RuntimeException ignored) {
                visibilityProbeError = true;
                return null;
            }
        }

        private Boolean safeDirectVisibility() {
            if (!"supported".equals(directScope) || targetBlock == null
                    || !Boolean.TRUE.equals(blockChunkMatches)) return null;
            try {
                // In fixed 1.20.1 / Forge 47.4.20 this is the visibility.isTicking map read.
                return level.isNaturalSpawningAllowed(targetBlock);
            } catch (RuntimeException | LinkageError ignored) {
                directProbeError = true;
                return null;
            }
        }

        private Long directTick() {
            try {
                return level.getServer().overworld().getGameTime();
            } catch (RuntimeException ignored) {
                directProbeError = true;
                return null;
            }
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
                Long afterQueryTick = visibilityEnabled ? queryTick() : null;
                Boolean rangeAfter = visibilityEnabled ? safeRange() : targetKey == null ? null : level.getChunkSource().chunkMap
                        .getDistanceManager().inEntityTickingRange(targetKey);
                Boolean compositeAfter = visibilityEnabled ? safeComposite() : null;
                Long afterQueryEndTick = visibilityEnabled ? queryTick() : null;
                Long directAfterTick = directRequested ? directTick() : null;
                Boolean directAfterRaw = directRequested ? safeDirectVisibility() : null;
                Long directAfterEndTick = directRequested ? directTick() : null;
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
                String fingerprint = details;
                if (visibilityEnabled) {
                    String visibilityBefore = MutualTicketObservationPolicy.visibilityAtTicks(
                            rangeBefore, compositeBefore, beforeQueryTick, beforeQueryEndTick);
                    String visibilityAfter = MutualTicketObservationPolicy.visibilityAtTicks(
                            rangeAfter, compositeAfter, afterQueryTick, afterQueryEndTick);
                    fingerprint = MutualTicketObservationPolicy.visibilityFingerprint(details, blockChunkMatches,
                            compositeBefore, visibilityBefore, compositeAfter, visibilityAfter, visibilityProbeError);
                    details += ":visibility_probe=true"
                            + ":target_block_x=" + (targetBlock == null ? "unknown" : targetBlock.getX())
                            + ":target_block_y=" + (targetBlock == null ? "unknown" : targetBlock.getY())
                            + ":target_block_z=" + (targetBlock == null ? "unknown" : targetBlock.getZ())
                            + ":block_chunk_matches=" + MutualTicketObservationPolicy.state(blockChunkMatches)
                            + ":before_query_tick=" + number(beforeQueryTick)
                            + ":before_query_end_tick=" + number(beforeQueryEndTick)
                            + ":composite_before=" + MutualTicketObservationPolicy.state(compositeBefore)
                            + ":visibility_before=" + visibilityBefore
                            + ":after_query_tick=" + number(afterQueryTick)
                            + ":after_query_end_tick=" + number(afterQueryEndTick)
                            + ":composite_after=" + MutualTicketObservationPolicy.state(compositeAfter)
                            + ":visibility_after=" + visibilityAfter
                            + ":visibility_probe_error=" + visibilityProbeError;
                }
                if (directRequested) {
                    Boolean directBefore = MutualTicketObservationPolicy.directVisibilityAtTicks(
                            directBeforeRaw, directBeforeTick, directBeforeEndTick);
                    Boolean directAfter = MutualTicketObservationPolicy.directVisibilityAtTicks(
                            directAfterRaw, directAfterTick, directAfterEndTick);
                    fingerprint = MutualTicketObservationPolicy.directVisibilityFingerprint(
                            fingerprint, directScope, directBefore, directAfter, directProbeError);
                    details += ":direct_scope=" + directScope
                            + ":direct_level_exact=" + exactLevel
                            + ":direct_minecraft_version=" + string(minecraftVersion)
                            + ":direct_forge_version=" + string(forgeVersion)
                            + ":direct_before_tick=" + number(directBeforeTick)
                            + ":direct_before_end_tick=" + number(directBeforeEndTick)
                            + ":direct_before_raw=" + MutualTicketObservationPolicy.state(directBeforeRaw)
                            + ":direct_before=" + MutualTicketObservationPolicy.state(directBefore)
                            + ":direct_after_tick=" + number(directAfterTick)
                            + ":direct_after_end_tick=" + number(directAfterEndTick)
                            + ":direct_after_raw=" + MutualTicketObservationPolicy.state(directAfterRaw)
                            + ":direct_after=" + MutualTicketObservationPolicy.state(directAfter)
                            + ":direct_probe_error=" + directProbeError;
                }
                long tick = level.getServer().overworld().getGameTime();
                if (MutualTicketObservationPolicy.emit(recorder.previous, fingerprint, tick)) {
                    WWDebugBenchmarkMod.LOGGER.info("Mutual GameTest force observation server_tick={} primary_uuid={} {}",
                            tick, primary.getUUID(), details);
                    recorder.previous = fingerprint;
                }
            } catch (RuntimeException ignored) {
                // A missing observation is unknown; it must not change the validation loop.
            }
        }

        private static String value(UUID uuid) {
            return uuid == null ? "unknown" : uuid.toString();
        }

        private static String number(Long number) {
            return number == null ? "unknown" : number.toString();
        }

        private static String string(String value) {
            return value == null ? "unknown" : value;
        }
    }
}
