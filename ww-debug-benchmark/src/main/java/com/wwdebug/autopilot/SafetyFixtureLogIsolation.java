package com.wwdebug.autopilot;

import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParseException;
import com.google.gson.JsonParser;
import net.minecraft.server.MinecraftServer;

import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.lang.reflect.Field;
import java.nio.ByteBuffer;
import java.nio.channels.SeekableByteChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.stream.Stream;

/** Test-only cleanup; never suppresses or deletes fixture telemetry. */
final class SafetyFixtureLogIsolation {
    private SafetyFixtureLogIsolation() {
    }

    static void clearAuthority(UUID aircraftId) {
        try {
            Field field = ControlAuthorityArbiter.class.getDeclaredField("LAST_AUTHORITY");
            field.setAccessible(true);
            ((Map<?, ?>) field.get(null)).remove(aircraftId);
        } catch (ReflectiveOperationException exception) {
            throw new IllegalStateException("could not clear fixture control authority", exception);
        }
    }

    /** Close this fixture's writer, then preserve exactly one log outside aircraft/*.jsonl. */
    static void isolate(MinecraftServer server, UUID aircraftId) {
        synchronized (AutopilotLogManager.class) {
            try {
                Field runsField = AutopilotLogManager.class.getDeclaredField("RUNS");
                runsField.setAccessible(true);
                Object run = ((Map<?, ?>) runsField.get(null)).get(server);
                if (run == null) {
                    throw new IllegalStateException("fixture telemetry run is missing: " + aircraftId);
                }
                Field directoryField = run.getClass().getDeclaredField("directory");
                directoryField.setAccessible(true);
                Path runDirectory = (Path) directoryField.get(run);

                // A player handover may reopen a writer after its old session was stopped.
                // Close only this UUID; never close the shared run or another aircraft's writer.
                Field writersField = run.getClass().getDeclaredField("aircraftWriters");
                writersField.setAccessible(true);
                Map<?, ?> writers = (Map<?, ?>) writersField.get(run);
                Object aircraftWriter = writers.get(aircraftId);
                if (aircraftWriter != null) {
                    Field writerField = aircraftWriter.getClass().getDeclaredField("writer");
                    writerField.setAccessible(true);
                    ((BufferedWriter) writerField.get(aircraftWriter)).close();
                    writers.remove(aircraftId);
                }
                Field motionField = run.getClass().getDeclaredField("motionSamples");
                motionField.setAccessible(true);
                ((Map<?, ?>) motionField.get(run)).remove(aircraftId);

                Path aircraftDirectory = runDirectory.resolve("aircraft");
                List<Path> matches;
                try (Stream<Path> paths = Files.list(aircraftDirectory)) {
                    matches = paths.filter(Files::isRegularFile)
                            .filter(path -> path.getFileName().toString()
                                    .endsWith("-" + aircraftId + ".jsonl"))
                            .toList();
                }
                if (matches.size() != 1) {
                    throw new IllegalStateException("expected one fixture log for " + aircraftId
                            + ", found " + matches.size());
                }
                Path source = matches.get(0);
                // Both logs receive the same serialized rows. The production per-aircraft close
                // can log and swallow IOException, so a closed writer alone is not evidence that
                // its file contains all rows. Flush the shared combined stream before comparing.
                Field combinedField = run.getClass().getDeclaredField("combined");
                combinedField.setAccessible(true);
                ((BufferedWriter) combinedField.get(run)).flush();
                verifyComplete(runDirectory.resolve("combined.jsonl"), source, aircraftId);
                Path destinationDirectory = runDirectory.resolve("fixture-aircraft");
                Files.createDirectories(destinationDirectory);
                Path destination = destinationDirectory.resolve(source.getFileName());
                if (Files.exists(destination)) {
                    throw new IllegalStateException("fixture log destination already exists: " + destination);
                }
                Files.move(source, destination);
            } catch (ReflectiveOperationException | IOException exception) {
                throw new IllegalStateException("could not isolate fixture telemetry for " + aircraftId,
                        exception);
            }
        }
    }

    // This cross-check cannot detect events absent from both logs. It scans the combined log
    // once for each fixture, so its cost grows with both log size and fixture count.
    private static void verifyComplete(Path combinedPath, Path aircraftPath, UUID aircraftId)
            throws IOException {
        requireCompleteFinalLine(combinedPath);
        requireCompleteFinalLine(aircraftPath);
        int matchingRows = 0;
        try (BufferedReader combined = Files.newBufferedReader(combinedPath, StandardCharsets.UTF_8);
             BufferedReader aircraft = Files.newBufferedReader(aircraftPath, StandardCharsets.UTF_8)) {
            String line;
            while ((line = combined.readLine()) != null) {
                JsonObject row;
                try {
                    JsonElement parsed = JsonParser.parseString(line);
                    if (!parsed.isJsonObject()) {
                        throw new IllegalStateException("combined telemetry row is not an object");
                    }
                    row = parsed.getAsJsonObject();
                } catch (JsonParseException exception) {
                    throw new IllegalStateException("combined telemetry contains malformed JSON", exception);
                }
                JsonElement id = row.get("aircraft_uuid");
                if (id == null || !id.isJsonPrimitive() || !id.getAsJsonPrimitive().isString()) {
                    throw new IllegalStateException("combined telemetry row has no aircraft UUID");
                }
                if (!aircraftId.toString().equals(id.getAsString())) {
                    continue;
                }
                matchingRows++;
                if (!line.equals(aircraft.readLine())) {
                    throw new IllegalStateException("fixture telemetry differs from combined log: " + aircraftId);
                }
            }
            if (matchingRows == 0 || aircraft.readLine() != null) {
                throw new IllegalStateException("fixture telemetry is empty or incomplete: " + aircraftId);
            }
        }
    }

    private static void requireCompleteFinalLine(Path path) throws IOException {
        try (SeekableByteChannel channel = Files.newByteChannel(path)) {
            long size = channel.size();
            if (size == 0) {
                throw new IllegalStateException("telemetry log is empty: " + path);
            }
            channel.position(size - 1);
            ByteBuffer last = ByteBuffer.allocate(1);
            if (channel.read(last) != 1 || last.get(0) != (byte) '\n') {
                throw new IllegalStateException("telemetry log has an incomplete final line: " + path);
            }
        }
    }

    /** Run every registered cleanup even when an earlier one fails. */
    static final class Cleanup implements AutoCloseable {
        private final List<Runnable> actions = new ArrayList<>();

        void add(Runnable action) {
            actions.add(action);
        }

        @Override
        public void close() {
            Throwable first = null;
            for (Runnable action : actions) {
                try {
                    action.run();
                } catch (Throwable failure) {
                    if (first == null) {
                        first = failure;
                    } else if (failure != first) {
                        first.addSuppressed(failure);
                    }
                }
            }
            if (first instanceof Error error) {
                throw error;
            }
            if (first instanceof RuntimeException exception) {
                throw exception;
            }
            if (first != null) {
                throw new IllegalStateException("fixture cleanup failed", first);
            }
        }
    }
}
