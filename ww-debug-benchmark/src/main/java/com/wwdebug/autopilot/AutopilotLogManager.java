package com.wwdebug.autopilot;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonObject;
import com.wwdebug.benchmark.WWDebugBenchmarkMod;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.MinecraftServer;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.level.storage.LevelResource;

import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.HashMap;
import java.util.IdentityHashMap;
import java.util.Map;
import java.util.UUID;

public final class AutopilotLogManager {
    private static final Gson GSON = new GsonBuilder().disableHtmlEscaping().create();
    private static final DateTimeFormatter FILE_TIME = DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss")
            .withZone(ZoneOffset.UTC);
    private static final Map<MinecraftServer, RunLog> RUNS = new IdentityHashMap<>();

    private AutopilotLogManager() {
    }

    public static synchronized void writeFrame(MinecraftServer server, Entity aircraft, JsonObject frame) {
        try {
            RunLog run = RUNS.computeIfAbsent(server, AutopilotLogManager::openRun);
            frame.addProperty("run_id", run.runId);
            frame.addProperty("event", "frame");
            frame.addProperty("server_tick", server.overworld().getGameTime());
            addIdentity(frame, aircraft);
            run.write(aircraft, GSON.toJson(frame));
        } catch (RuntimeException | IOException exception) {
            WWDebugBenchmarkMod.LOGGER.error("Could not write autonomous-flight telemetry", exception);
        }
    }

    public static synchronized void writeEvent(MinecraftServer server, Entity aircraft, String event,
                                                String reason, FlightPhase phase) {
        JsonObject row = new JsonObject();
        row.addProperty("event", event);
        row.addProperty("reason", reason);
        row.addProperty("phase", phase.name());
        row.addProperty("server_tick", server.overworld().getGameTime());
        addIdentity(row, aircraft);
        try {
            RunLog run = RUNS.computeIfAbsent(server, AutopilotLogManager::openRun);
            row.addProperty("run_id", run.runId);
            run.write(aircraft, GSON.toJson(row));
        } catch (RuntimeException | IOException exception) {
            WWDebugBenchmarkMod.LOGGER.error("Could not write autonomous-flight event", exception);
        }
    }

    public static synchronized void closeAircraft(MinecraftServer server, Entity aircraft,
                                                   FlightPhase finalPhase, String reason) {
        RunLog run = RUNS.get(server);
        if (run == null) {
            return;
        }
        writeEvent(server, aircraft, "session_end", reason, finalPhase);
        run.closeAircraft(aircraft.getUUID());
    }

    public static synchronized void closeServer(MinecraftServer server) {
        RunLog run = RUNS.remove(server);
        if (run != null) {
            run.close();
        }
    }

    public static synchronized String currentDirectory(MinecraftServer server) {
        RunLog run = RUNS.get(server);
        return run == null ? "not-opened" : run.directory.toAbsolutePath().toString();
    }

    private static RunLog openRun(MinecraftServer server) {
        try {
            String runId = FILE_TIME.format(Instant.now());
            Path directory = server.getWorldPath(LevelResource.ROOT)
                    .resolve("wwdebug")
                    .resolve("autopilot")
                    .resolve(runId);
            Files.createDirectories(directory.resolve("aircraft"));
            return new RunLog(runId, directory);
        } catch (IOException exception) {
            throw new IllegalStateException("Could not create autonomous-flight log directory", exception);
        }
    }

    private static void addIdentity(JsonObject row, Entity aircraft) {
        ResourceLocation id = BuiltInRegistries.ENTITY_TYPE.getKey(aircraft.getType());
        row.addProperty("aircraft_entity_id", id.toString());
        row.addProperty("aircraft_uuid", aircraft.getUUID().toString());
        row.addProperty("aircraft_name", aircraft.getName().getString());
        Entity pilot = aircraft.getControllingPassenger();
        row.addProperty("pilot_entity_id", pilot == null
                ? "none" : BuiltInRegistries.ENTITY_TYPE.getKey(pilot.getType()).toString());
        row.addProperty("pilot_uuid", pilot == null ? "none" : pilot.getUUID().toString());
    }

    private static final class RunLog {
        private final String runId;
        private final Path directory;
        private final BufferedWriter combined;
        private final Map<UUID, AircraftWriter> aircraftWriters = new HashMap<>();
        private int pendingCombined;

        private RunLog(String runId, Path directory) throws IOException {
            this.runId = runId;
            this.directory = directory;
            this.combined = writer(directory.resolve("combined.jsonl"));
        }

        private void write(Entity aircraft, String line) throws IOException {
            combined.write(line);
            combined.newLine();
            pendingCombined++;

            AircraftWriter writer = aircraftWriters.computeIfAbsent(aircraft.getUUID(), ignored -> {
                ResourceLocation id = BuiltInRegistries.ENTITY_TYPE.getKey(aircraft.getType());
                String fileName = id.getNamespace() + "-" + id.getPath() + "-" + aircraft.getUUID() + ".jsonl";
                try {
                    return new AircraftWriter(writer(directory.resolve("aircraft").resolve(fileName)));
                } catch (IOException exception) {
                    throw new IllegalStateException(exception);
                }
            });
            writer.write(line);

            if (pendingCombined >= 20) {
                combined.flush();
                pendingCombined = 0;
            }
        }

        private void closeAircraft(UUID uuid) {
            AircraftWriter writer = aircraftWriters.remove(uuid);
            if (writer != null) {
                writer.close();
            }
        }

        private void close() {
            for (AircraftWriter writer : aircraftWriters.values()) {
                writer.close();
            }
            aircraftWriters.clear();
            try {
                combined.flush();
                combined.close();
            } catch (IOException exception) {
                WWDebugBenchmarkMod.LOGGER.warn("Could not close combined autonomous-flight log", exception);
            }
        }

        private static BufferedWriter writer(Path path) throws IOException {
            return Files.newBufferedWriter(path, StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE, StandardOpenOption.APPEND);
        }
    }

    private static final class AircraftWriter {
        private final BufferedWriter writer;
        private int pending;

        private AircraftWriter(BufferedWriter writer) {
            this.writer = writer;
        }

        private void write(String line) throws IOException {
            writer.write(line);
            writer.newLine();
            pending++;
            if (pending >= 20) {
                writer.flush();
                pending = 0;
            }
        }

        private void close() {
            try {
                writer.flush();
                writer.close();
            } catch (IOException exception) {
                WWDebugBenchmarkMod.LOGGER.warn("Could not close autonomous-flight aircraft log", exception);
            }
        }
    }
}