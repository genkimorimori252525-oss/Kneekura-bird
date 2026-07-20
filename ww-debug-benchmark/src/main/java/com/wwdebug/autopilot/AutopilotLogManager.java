package com.wwdebug.autopilot;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonObject;
import com.wwdebug.benchmark.ReflectiveAircraft;
import com.wwdebug.benchmark.WWDebugBenchmarkMod;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.MinecraftServer;
import net.minecraft.util.Mth;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.level.storage.LevelResource;
import net.minecraft.world.phys.Vec3;

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
            run.enrichMotion(server, aircraft, frame);
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
        private final Map<UUID, MotionSample> motionSamples = new HashMap<>();
        private int pendingCombined;

        private RunLog(String runId, Path directory) throws IOException {
            this.runId = runId;
            this.directory = directory;
            this.combined = writer(directory.resolve("combined.jsonl"));
        }

        private void enrichMotion(MinecraftServer server, Entity aircraft, JsonObject frame) {
            long tick = server.overworld().getGameTime();
            MotionSample current = new MotionSample(
                    tick,
                    aircraft.position(),
                    aircraft.getDeltaMovement(),
                    Mth.wrapDegrees(aircraft.getYRot()),
                    Mth.wrapDegrees(aircraft.getXRot()),
                    ReflectiveAircraft.rollDegrees(aircraft)
            );
            MotionSample previous = motionSamples.put(aircraft.getUUID(), current);
            if (previous == null || tick <= previous.tick()) {
                frame.addProperty("motion_sample_ticks", 0);
                frame.addProperty("acceleration_bps2", 0.0);
                addVector(frame, "acceleration_vector_bps2", Vec3.ZERO);
                frame.addProperty("displacement_blocks_since_sample", 0.0);
                frame.addProperty("yaw_rate_deg_s", 0.0);
                frame.addProperty("pitch_rate_deg_s", 0.0);
                frame.addProperty("roll_rate_deg_s", 0.0);
                return;
            }

            long tickDelta = tick - previous.tick();
            double seconds = tickDelta / 20.0;
            Vec3 currentVelocityBps = current.velocityBpt().scale(20.0);
            Vec3 previousVelocityBps = previous.velocityBpt().scale(20.0);
            Vec3 acceleration = currentVelocityBps.subtract(previousVelocityBps).scale(1.0 / seconds);
            double scalarAcceleration = (currentVelocityBps.length() - previousVelocityBps.length()) / seconds;

            frame.addProperty("motion_sample_ticks", tickDelta);
            frame.addProperty("acceleration_bps2", scalarAcceleration);
            addVector(frame, "acceleration_vector_bps2", acceleration);
            frame.addProperty("displacement_blocks_since_sample",
                    current.position().distanceTo(previous.position()));
            frame.addProperty("yaw_rate_deg_s",
                    Mth.wrapDegrees(current.yawDeg() - previous.yawDeg()) / seconds);
            frame.addProperty("pitch_rate_deg_s",
                    Mth.wrapDegrees(current.pitchDeg() - previous.pitchDeg()) / seconds);
            if (Double.isFinite(current.rollDeg()) && Double.isFinite(previous.rollDeg())) {
                frame.addProperty("roll_rate_deg_s",
                        Mth.wrapDegrees((float) (current.rollDeg() - previous.rollDeg())) / seconds);
            }
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
            motionSamples.remove(uuid);
            AircraftWriter writer = aircraftWriters.remove(uuid);
            if (writer != null) {
                writer.close();
            }
        }

        private void close() {
            motionSamples.clear();
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

    private static void addVector(JsonObject root, String name, Vec3 value) {
        JsonObject vector = new JsonObject();
        vector.addProperty("x", value.x);
        vector.addProperty("y", value.y);
        vector.addProperty("z", value.z);
        root.add(name, vector);
    }

    private record MotionSample(
            long tick,
            Vec3 position,
            Vec3 velocityBpt,
            float yawDeg,
            float pitchDeg,
            double rollDeg
    ) {
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