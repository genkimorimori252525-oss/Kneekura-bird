package com.wwdebug.autopilot;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.wwdebug.benchmark.AircraftMetadata;
import com.wwdebug.benchmark.AircraftMetadataResolver;
import com.wwdebug.benchmark.ReflectiveAircraft;
import com.wwdebug.benchmark.WWDebugBenchmarkMod;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.gametest.framework.GameTestServer;
import net.minecraft.network.chat.Component;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.entity.Mob;
import net.minecraft.world.entity.npc.Villager;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.storage.LevelResource;
import net.minecraft.world.phys.Vec3;

import javax.annotation.Nullable;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.Deque;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

public final class AutopilotValidationManager {
    private static final Gson GSON = new GsonBuilder().setPrettyPrinting().create();
    private static final Map<MinecraftServer, ValidationRun> RUNS = new ConcurrentHashMap<>();

    private AutopilotValidationManager() {
    }

    public static int startAll(CommandSourceStack source) {
        MinecraftServer server = source.getServer();
        if (RUNS.containsKey(server)) {
            source.sendFailure(Component.literal("An autonomous-flight validation is already running."));
            return 0;
        }

        AutopilotProfileRegistry.reload(server);
        List<Candidate> candidates = discoverFighters(source.getLevel());
        if (candidates.isEmpty()) {
            String reason = "No registered aircraft matched a measured fighter profile. profile_source="
                    + AutopilotProfileRegistry.sourceDescription();
            WWDebugBenchmarkMod.LOGGER.error("Could not start all-fighter autonomous-flight validation: {}", reason);
            source.sendFailure(Component.literal(reason));
            return 0;
        }

        ValidationRun run = new ValidationRun(source, candidates);
        RUNS.put(server, run);
        source.sendSuccess(() -> Component.literal(
                "Autonomous-flight validation started for " + candidates.size()
                        + " fighters. Aircraft run sequentially from your current runway heading."), false);
        WWDebugBenchmarkMod.LOGGER.info("Autonomous-flight validation accepted {} fighter candidates: {}",
                candidates.size(), candidates.stream().map(value -> value.id().toString()).toList());
        return candidates.size();
    }

    public static int startOne(CommandSourceStack source, String idText) {
        MinecraftServer server = source.getServer();
        if (RUNS.containsKey(server)) {
            source.sendFailure(Component.literal("An autonomous-flight validation is already running."));
            return 0;
        }

        ResourceLocation id = ResourceLocation.tryParse(idText);
        if (id == null) {
            source.sendFailure(Component.literal("Invalid aircraft id: " + idText));
            return 0;
        }

        AutopilotProfileRegistry.reload(server);
        CandidateLookup lookup = candidate(source.getLevel(), id);
        if (lookup.candidate() == null) {
            String message = "No compatible autonomous aircraft found for " + id + ": " + lookup.reason();
            WWDebugBenchmarkMod.LOGGER.error("{}; {}", message,
                    AutopilotProfileRegistry.resolutionDiagnostics(server, id));
            source.sendFailure(Component.literal(message));
            return 0;
        }

        ValidationRun run = new ValidationRun(source, List.of(lookup.candidate()));
        RUNS.put(server, run);
        source.sendSuccess(() -> Component.literal(
                "Autonomous-flight validation started for " + id + "."), false);
        WWDebugBenchmarkMod.LOGGER.info("Autonomous-flight validation accepted {} using profile {}",
                id, lookup.candidate().profileId());
        return 1;
    }

    public static int status(CommandSourceStack source) {
        ValidationRun run = RUNS.get(source.getServer());
        if (run == null) {
            source.sendSuccess(() -> Component.literal("No autonomous-flight validation is running."), false);
            return 0;
        }
        source.sendSuccess(() -> Component.literal(run.status()), false);
        return run.completedCount();
    }

    public static int stop(CommandSourceStack source) {
        ValidationRun run = RUNS.remove(source.getServer());
        if (run == null) {
            source.sendFailure(Component.literal("No autonomous-flight validation is running."));
            return 0;
        }
        run.abort("stopped_by_command");
        source.sendSuccess(() -> Component.literal("Autonomous-flight validation stopped."), false);
        return 1;
    }

    public static void tick(MinecraftServer server) {
        ValidationRun run = RUNS.get(server);
        if (run == null) {
            return;
        }
        try {
            run.tick();
            if (run.complete()) {
                run.finish();
                RUNS.remove(server, run);
            }
        } catch (RuntimeException exception) {
            WWDebugBenchmarkMod.LOGGER.error("Autonomous-flight validation failed", exception);
            run.abort("validation_exception:" + exception.getClass().getSimpleName());
            RUNS.remove(server, run);
        }
    }

    public static void stopSilently(MinecraftServer server) {
        ValidationRun run = RUNS.remove(server);
        if (run != null) {
            run.abort("server_stopping");
        }
    }

    private static List<Candidate> discoverFighters(ServerLevel level) {
        List<Candidate> candidates = new ArrayList<>();
        MinecraftServer server = level.getServer();

        for (FlightProfile profile : AutopilotProfileRegistry.fighterProfiles(server)) {
            ResourceLocation id = profile.profileId();
            EntityType<?> type = BuiltInRegistries.ENTITY_TYPE.getOptional(id).orElse(null);
            if (type == null) {
                WWDebugBenchmarkMod.LOGGER.warn(
                        "Skipping measured fighter profile {} because its entity type is not registered", id);
                continue;
            }
            AircraftMetadata metadata = AircraftMetadataResolver.resolve(server.getResourceManager(), id);
            String variantGroup = "unknown".equalsIgnoreCase(metadata.role())
                    ? profile.profileId().toString() : metadata.variantGroup();
            String doctrine = "unknown".equalsIgnoreCase(metadata.doctrine())
                    ? profile.doctrine() : metadata.doctrine();
            candidates.add(new Candidate(type, id, variantGroup, doctrine, profile.profileId()));
        }

        candidates.sort(Comparator.comparing(candidate -> candidate.id().toString()));
        return candidates;
    }

    private static CandidateLookup candidate(ServerLevel level, ResourceLocation id) {
        EntityType<?> type = BuiltInRegistries.ENTITY_TYPE.getOptional(id).orElse(null);
        if (type == null) {
            return new CandidateLookup(null, "entity_type_not_registered");
        }

        MinecraftServer server = level.getServer();
        FlightProfile profile = AutopilotProfileRegistry.resolve(server, id).orElse(null);
        if (profile == null) {
            return new CandidateLookup(null, "measured_profile_not_resolved");
        }
        if (!profile.supportsAutonomousFlight()) {
            return new CandidateLookup(null, "profile_role_not_supported_" + profile.role());
        }

        AircraftMetadata metadata = AircraftMetadataResolver.resolve(server.getResourceManager(), id);
        String variantGroup = "unknown".equalsIgnoreCase(metadata.role())
                ? profile.profileId().toString() : metadata.variantGroup();
        String doctrine = "unknown".equalsIgnoreCase(metadata.doctrine())
                ? profile.doctrine() : metadata.doctrine();

        return new CandidateLookup(
                new Candidate(type, id, variantGroup, doctrine, profile.profileId()),
                "accepted"
        );
    }

    private record Candidate(EntityType<?> type, ResourceLocation id, String variantGroup,
                             String doctrine, ResourceLocation profileId) {
    }

    private record CandidateLookup(@Nullable Candidate candidate, String reason) {
    }

    private static final class ValidationRun {
        private final CommandSourceStack source;
        private final MinecraftServer server;
        private final ServerLevel level;
        private final Vec3 requestedAnchor;
        private final float runwayYaw;
        private final Deque<Candidate> pending;
        private final List<Map<String, Object>> results = new ArrayList<>();
        private final int total;
        private final java.util.Set<Long> ownedForcedChunks = new java.util.HashSet<>();
        private final MutualTicketObserver.Recorder ticketObserver = new MutualTicketObserver.Recorder();

        private Candidate activeCandidate;
        private Entity activeAircraft;
        private Mob activePilot;
        private int activeTicks;
        private int elapsedTicks;

        private ValidationRun(CommandSourceStack source, List<Candidate> candidates) {
            this.source = source;
            this.server = source.getServer();
            this.level = source.getLevel();
            this.requestedAnchor = source.getPosition();
            this.runwayYaw = source.getRotation().y;
            this.pending = new ArrayDeque<>(candidates);
            this.total = candidates.size();
        }

        private void tick() {
            elapsedTicks++;
            if (activeAircraft == null) {
                spawnNext();
                return;
            }

            activeTicks++;
            keepChunksLoaded();
            if (activeAircraft.isRemoved() || activePilot == null || activePilot.isRemoved()
                    || !activePilot.isPassengerOfSameVehicle(activeAircraft)) {
                record(false, "aircraft_or_mob_pilot_removed", null);
                cleanupActive();
                return;
            }

            var status = AutonomousFlightManager.status(activeAircraft.getUUID());
            if (status.isEmpty()) {
                if (activeTicks > 240) {
                    String diagnostics = "autopilot_session_not_started:class="
                            + activeAircraft.getClass().getName()
                            + ",airplane=" + ReflectiveAircraft.isAirplane(activeAircraft)
                            + ",controllable=" + ReflectiveAircraft.isControllable(activeAircraft)
                            + ",pilot=" + activePilot.getType()
                            + ",profile=" + AutopilotProfileRegistry.resolve(server, activeAircraft)
                            .map(value -> value.profileId().toString()).orElse("none");
                    WWDebugBenchmarkMod.LOGGER.error("{}", diagnostics);
                    record(false, diagnostics, null);
                    cleanupActive();
                }
                return;
            }

            AutonomousFlightManager.SessionStatus value = status.get();
            if (value.complete()) {
                record(true, "completed_full_mission", value);
                cleanupActive();
            } else if (value.failed()) {
                record(false, value.transitionReason(), value);
                cleanupActive();
            } else if (activeTicks > 16500) {
                record(false, "aircraft_validation_timeout", value);
                cleanupActive();
            }
        }

        private void spawnNext() {
            if (pending.isEmpty()) {
                return;
            }
            Candidate candidate = pending.removeFirst();
            Entity aircraft = null;
            Villager pilot = null;
            try {
                Vec3 anchor = requestedAnchor;

                aircraft = candidate.type().create(level);
                if (aircraft == null) {
                    results.add(failedBeforeSpawn(candidate, "entity_type_create_returned_null"));
                    WWDebugBenchmarkMod.LOGGER.error("Could not create validation aircraft {}", candidate.id());
                    return;
                }
                if (!ReflectiveAircraft.isAirplane(aircraft)) {
                    String reason = "created_entity_is_not_airplane:class=" + aircraft.getClass().getName();
                    results.add(failedBeforeSpawn(candidate, reason));
                    WWDebugBenchmarkMod.LOGGER.error("Rejected validation aircraft {}: {}", candidate.id(), reason);
                    aircraft.discard();
                    return;
                }
                if (!ReflectiveAircraft.isControllable(aircraft)) {
                    String reason = "created_airplane_missing_control_surface:class=" + aircraft.getClass().getName();
                    results.add(failedBeforeSpawn(candidate, reason));
                    WWDebugBenchmarkMod.LOGGER.error("Rejected validation aircraft {}: {}", candidate.id(), reason);
                    aircraft.discard();
                    return;
                }

                FlightProfile resolvedProfile = AutopilotProfileRegistry.resolve(server, aircraft).orElse(null);
                if (resolvedProfile == null) {
                    String reason = "spawned_aircraft_profile_not_resolved:"
                            + AutopilotProfileRegistry.resolutionDiagnostics(server, candidate.id());
                    results.add(failedBeforeSpawn(candidate, reason));
                    WWDebugBenchmarkMod.LOGGER.error("Rejected validation aircraft {}: {}", candidate.id(), reason);
                    aircraft.discard();
                    return;
                }

                aircraft.moveTo(anchor.x, anchor.y, anchor.z, runwayYaw, 0.0f);
                aircraft.setInvulnerable(true);
                aircraft.setCustomName(Component.literal("AUTOPILOT TEST " + candidate.id()));
                aircraft.setCustomNameVisible(true);

                pilot = EntityType.VILLAGER.create(level);
                if (pilot == null) {
                    aircraft.discard();
                    results.add(failedBeforeSpawn(candidate, "could_not_create_mob_pilot"));
                    return;
                }
                pilot.moveTo(anchor.x, anchor.y, anchor.z, runwayYaw, 0.0f);
                pilot.setNoAi(true);
                pilot.setSilent(true);
                pilot.setInvulnerable(true);
                pilot.setPersistenceRequired();
                pilot.setCustomName(Component.literal("WW autonomous-flight test pilot"));

                var uuidPlan = MutualDogfightUuidOrder.resolve(server instanceof GameTestServer,
                        System.getProperty("wwdebug.flightGameTestScenario", "full"),
                        System.getProperty("wwdebug.flightGameTestAircraft", "warfare_wings:a6m"),
                        System.getProperty("wwdebug.mutualUuidOrder"));
                if (uuidPlan.isPresent()) {
                    var plan = uuidPlan.get();
                    if (!"warfare_wings:a6m".equals(candidate.id().toString())
                            || level.getEntity(plan.primaryAircraft()) != null
                            || level.getEntity(plan.primaryPilot()) != null) {
                        throw new IllegalStateException("mutual UUID fixture conflicts with validation state");
                    }
                    aircraft.setUUID(plan.primaryAircraft());
                    pilot.setUUID(plan.primaryPilot());
                    WWDebugBenchmarkMod.LOGGER.info(
                            "Mutual GameTest UUID fixture order={} primary={} primary_pilot={}",
                            plan.order(), plan.primaryAircraft(), plan.primaryPilot());
                }
                if (uuidPlan.isPresent()) {
                    MutualDogfightUuidFixture.add(level, aircraft, uuidPlan.get().primaryAircraft(), "primary_aircraft");
                    MutualDogfightUuidFixture.add(level, pilot, uuidPlan.get().primaryPilot(), "primary_pilot");
                } else {
                    level.addFreshEntity(aircraft);
                    level.addFreshEntity(pilot);
                }
                if (!pilot.startRiding(aircraft, true)) {
                    pilot.discard();
                    aircraft.discard();
                    results.add(failedBeforeSpawn(candidate, "mob_pilot_could_not_mount"));
                    return;
                }
                ReflectiveAircraft.fillFuel(aircraft);
                this.activeCandidate = candidate;
                this.activeAircraft = aircraft;
                this.activePilot = pilot;
                this.activeTicks = 0;
                keepChunksLoaded();
                WWDebugBenchmarkMod.LOGGER.info(
                        "Spawned autonomous-flight validation aircraft {} uuid={} class={} profile={} pilot_uuid={}",
                        candidate.id(), aircraft.getUUID(), aircraft.getClass().getName(),
                        resolvedProfile.profileId(), pilot.getUUID());
                source.sendSuccess(() -> Component.literal(
                        "Testing " + candidate.id() + " (" + (results.size() + 1) + "/" + total + ")"), false);
            } catch (Throwable throwable) {
                if (pilot != null) {
                    pilot.discard();
                }
                if (aircraft != null) {
                    aircraft.discard();
                }
                String reason = "spawn_exception:" + throwable.getClass().getName() + ":" + throwable.getMessage();
                results.add(failedBeforeSpawn(candidate, reason));
                WWDebugBenchmarkMod.LOGGER.error("Validation aircraft spawn failed for {}", candidate.id(), throwable);
            }
        }

        private void record(boolean passed, String reason,
                            @Nullable AutonomousFlightManager.SessionStatus status) {
            Map<String, Object> result = new LinkedHashMap<>();
            result.put("entity_id", activeCandidate.id().toString());
            result.put("variant_group", activeCandidate.variantGroup());
            result.put("doctrine", activeCandidate.doctrine());
            result.put("profile_id", activeCandidate.profileId().toString());
            result.put("passed", passed);
            result.put("reason", reason);
            result.put("elapsed_ticks", activeTicks);
            result.put("final_phase", status == null ? "none" : status.phase().name());
            result.put("mission_ticks", status == null ? 0 : status.missionTicks());
            result.put("last_transition_reason", status == null ? "none" : status.transitionReason());
            result.put("aircraft_uuid", activeAircraft == null ? "none" : activeAircraft.getUUID().toString());
            results.add(result);
        }

        private Map<String, Object> failedBeforeSpawn(Candidate candidate, String reason) {
            Map<String, Object> result = new LinkedHashMap<>();
            result.put("entity_id", candidate.id().toString());
            result.put("variant_group", candidate.variantGroup());
            result.put("doctrine", candidate.doctrine());
            result.put("profile_id", candidate.profileId().toString());
            result.put("passed", false);
            result.put("reason", reason);
            result.put("elapsed_ticks", 0);
            result.put("final_phase", "not_started");
            return result;
        }

        private void cleanupActive() {
            releaseOwnedChunks();
            if (activeAircraft != null) {
                UUID uuid = activeAircraft.getUUID();
                AutonomousFlightManager.forceStop(uuid, "validation_aircraft_cleanup");
            }
            if (activePilot != null && !activePilot.isRemoved()) {
                activePilot.stopRiding();
                activePilot.discard();
            }
            if (activeAircraft != null && !activeAircraft.isRemoved()) {
                activeAircraft.discard();
            }
            activeCandidate = null;
            activeAircraft = null;
            activePilot = null;
            activeTicks = 0;
        }

        private void keepChunksLoaded() {
            if (activeAircraft == null || !(activeAircraft.level() instanceof ServerLevel serverLevel)) {
                return;
            }
            ChunkPos center = activeAircraft.chunkPosition();
            var observation = ticketObserver.begin(serverLevel, activeAircraft, ownedForcedChunks, center);
            boolean complete = false;
            int index = 0;
            try {
                for (int dx = -3; dx <= 3; dx++) {
                    for (int dz = -3; dz <= 3; dz++) {
                        int chunkX = center.x + dx;
                        int chunkZ = center.z + dz;
                        long key = ChunkPos.asLong(chunkX, chunkZ);
                        var forced = serverLevel.getForcedChunks();
                        boolean alreadyForced = forced.contains(key);
                        if (observation != null) observation.read(forced, key, alreadyForced, index);
                        if (!alreadyForced) {
                            boolean result = serverLevel.setChunkForced(chunkX, chunkZ, true);
                            ownedForcedChunks.add(key);
                            if (observation != null) observation.attempted(key, result);
                        }
                        index++;
                    }
                }
                complete = true;
            } finally {
                if (observation != null) observation.finish(complete);
            }
        }

        private void releaseOwnedChunks() {
            for (long key : ownedForcedChunks) {
                ChunkPos chunk = new ChunkPos(key);
                level.setChunkForced(chunk.x, chunk.z, false);
            }
            ownedForcedChunks.clear();
        }

        private boolean complete() {
            return pending.isEmpty() && activeAircraft == null && results.size() >= total;
        }

        private int completedCount() {
            return results.size();
        }

        private String status() {
            String active = activeCandidate == null ? "none" : activeCandidate.id().toString();
            String phase = activeAircraft == null
                    ? "none"
                    : AutonomousFlightManager.status(activeAircraft.getUUID())
                    .map(value -> value.phase().name())
                    .orElse("waiting_for_autopilot");
            return "Autonomous-flight validation " + results.size() + "/" + total
                    + " complete; active=" + active
                    + "; phase=" + phase
                    + "; queued=" + pending.size()
                    + "; elapsed=" + elapsedTicks + " ticks"
                    + "; logs=" + AutopilotLogManager.currentDirectory(server);
        }

        private void finish() {
            Path output = writeSummary("complete");
            long passed = results.stream().filter(row -> Boolean.TRUE.equals(row.get("passed"))).count();
            source.sendSuccess(() -> Component.literal(
                    "Autonomous-flight validation complete: " + passed + "/" + total
                            + " passed. Summary: " + output.toAbsolutePath()), false);
            WWDebugBenchmarkMod.LOGGER.info("Autonomous-flight validation complete: {}/{} passed; summary={}",
                    passed, total, output.toAbsolutePath());
        }

        private void abort(String reason) {
            if (activeCandidate != null) {
                record(false, reason, activeAircraft == null ? null
                        : AutonomousFlightManager.status(activeAircraft.getUUID()).orElse(null));
            }
            cleanupActive();
            pending.clear();
            writeSummary(reason);
        }

        private Path writeSummary(String state) {
            Path directory = server.getWorldPath(LevelResource.ROOT)
                    .resolve("wwdebug")
                    .resolve("autopilot");
            Path output = directory.resolve("validation-summary-" + Instant.now().toEpochMilli() + ".json");
            Map<String, Object> summary = new LinkedHashMap<>();
            summary.put("state", state);
            summary.put("timestamp_utc", Instant.now().toString());
            summary.put("total", total);
            summary.put("completed", results.size());
            summary.put("profile_source", AutopilotProfileRegistry.sourceDescription());
            summary.put("runway_anchor", List.of(requestedAnchor.x, requestedAnchor.y, requestedAnchor.z));
            summary.put("runway_yaw", runwayYaw);
            summary.put("results", results);
            try {
                Files.createDirectories(directory);
                Files.writeString(output, GSON.toJson(summary), StandardCharsets.UTF_8);
            } catch (IOException exception) {
                WWDebugBenchmarkMod.LOGGER.error("Could not write autonomous-flight validation summary", exception);
            }
            return output;
        }
    }
}
