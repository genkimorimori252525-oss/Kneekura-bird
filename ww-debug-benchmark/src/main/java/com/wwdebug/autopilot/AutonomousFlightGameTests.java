package com.wwdebug.autopilot;

import com.google.gson.Gson;
import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.wwdebug.benchmark.BenchmarkCategory;
import com.wwdebug.benchmark.BenchmarkManager;
import com.wwdebug.benchmark.WWDebugBenchmarkMod;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.core.BlockPos;
import net.minecraft.gametest.framework.GameTest;
import net.minecraft.gametest.framework.GameTestAssertException;
import net.minecraft.gametest.framework.GameTestHelper;
import net.minecraft.gametest.framework.GameTestServer;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.levelgen.Heightmap;
import net.minecraft.world.level.storage.LevelResource;
import net.minecraft.world.phys.Vec2;
import net.minecraft.world.phys.Vec3;
import net.minecraftforge.gametest.GameTestHolder;
import net.minecraftforge.gametest.PrefixGameTestTemplate;
import net.minecraftforge.fml.loading.FMLPaths;

import java.io.IOException;
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.attribute.FileTime;
import java.util.Comparator;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;
import java.util.stream.Stream;

/**
 * Headless integration test using the real Forge server, real aircraft entities and real physics.
 *
 * <p>Set {@code -PflightTestAircraft=all} to execute every fighter sequentially, or pass one
 * supported aircraft id for a focused validation. If that aircraft has no staged measured profile,
 * the test first runs the matching real fixed-input category benchmark, installs its generated
 * profiles, and only then starts autonomous flight validation.</p>
 */
@GameTestHolder(WWDebugBenchmarkMod.MOD_ID)
@PrefixGameTestTemplate(false)
public final class AutonomousFlightGameTests {
    private static final Gson GSON = new Gson();
    private static final int RUNWAY_HALF_WIDTH = 40;
    private static final int RUNWAY_BEHIND = 260;
    private static final int RUNWAY_AHEAD = 800;
    private static final int RUNWAY_TERRAIN_MARGIN = 3;
    private static final int CLEAR_HEIGHT = 5;

    private AutonomousFlightGameTests() {
    }

    @GameTest(template = "empty", timeoutTicks = 260_000, batch = "autonomous_flight")
    public static void measuredProfileAutonomousFlight(GameTestHelper helper) {
        ServerLevel level = helper.getLevel();
        MinecraftServer server = level.getServer();
        // Reject a mistyped or mismatched opt-in before creating a validation scene.
        MutualDogfightUuidOrder.resolve(server instanceof GameTestServer,
                System.getProperty("wwdebug.flightGameTestScenario", "full"),
                System.getProperty("wwdebug.flightGameTestAircraft", "warfare_wings:a6m"),
                System.getProperty("wwdebug.mutualUuidOrder"));
        BlockPos templateOrigin = helper.absolutePos(BlockPos.ZERO);
        int highestTerrainY = highestTerrainInRunwayCorridor(level, templateOrigin);
        int runwayY = Math.min(level.getMaxBuildHeight() - CLEAR_HEIGHT - 2,
                highestTerrainY + RUNWAY_TERRAIN_MARGIN);
        BlockPos runwaySurface = new BlockPos(templateOrigin.getX(), runwayY, templateOrigin.getZ());
        buildRunway(level, runwaySurface);
        WWDebugBenchmarkMod.LOGGER.info(
                "Headless autonomous-flight runway surface={} highest_terrain_y={} width={} length={}",
                runwaySurface, highestTerrainY, RUNWAY_HALF_WIDTH * 2 + 1,
                RUNWAY_BEHIND + RUNWAY_AHEAD + 1);

        Vec3 aircraftAnchor = Vec3.atBottomCenterOf(runwaySurface.above());
        CommandSourceStack source = server.createCommandSourceStack()
                .withLevel(level)
                .withPosition(aircraftAnchor)
                .withRotation(new Vec2(0.0f, 0.0f))
                .withSuppressedOutput();

        Path worldRoot = server.getWorldPath(LevelResource.ROOT);
        Path summaryDirectory = worldRoot.resolve("wwdebug").resolve("autopilot");
        Path benchmarkDirectory = worldRoot.resolve("wwdebug").resolve("benchmarks");
        Path configuredProfile = FMLPaths.CONFIGDIR.get()
                .resolve("warfare_wings")
                .resolve("flight_profiles.json");

        String target = System.getProperty("wwdebug.flightGameTestAircraft", "warfare_wings:a6m");
        AtomicBoolean validationStarted = new AtomicBoolean(false);
        AtomicLong validationStartedAt = new AtomicLong(0L);
        long orchestrationStartedAt = System.currentTimeMillis();

        if (AutonomousProfileBootstrap.measuredProfileAvailable(server, configuredProfile, target)) {
            startValidation(source, target, validationStarted, validationStartedAt);
        } else {
            AutonomousProfileBootstrap.startMeasuredBenchmark(source, server, target);
        }

        helper.succeedWhen(() -> {
            if (!validationStarted.get()) {
                Path generatedProfile = newestProfile(benchmarkDirectory, orchestrationStartedAt)
                        .orElseThrow(() -> new GameTestAssertException(
                                "Measured aircraft benchmark is still running"));
                installProfile(generatedProfile, configuredProfile);
                AutopilotProfileRegistry.reload(server);
                startValidation(source, target, validationStarted, validationStartedAt);
                throw new GameTestAssertException("Measured profiles installed; autonomous-flight validation started");
            }

            Path summary = newestSummary(summaryDirectory, validationStartedAt.get())
                    .orElseThrow(() -> new GameTestAssertException(
                            "Autonomous-flight validation is still running for " + target));
            Summary result = readSummary(summary);
            if (!"complete".equals(result.state())) {
                throw new IllegalStateException("Autonomous-flight validation ended as "
                        + result.state() + "; summary=" + summary.toAbsolutePath());
            }
            if (result.passed() != result.total()) {
                throw new IllegalStateException("Autonomous-flight validation failed: "
                        + result.passed() + "/" + result.total() + " passed; first failure="
                        + result.firstFailure() + "; summary=" + summary.toAbsolutePath());
            }
            verifyRunwayStops(server, result.results());
        });
    }

    private static void startValidation(CommandSourceStack source, String target,
                                        AtomicBoolean started, AtomicLong startedAt) {
        int count = "all".equalsIgnoreCase(target)
                ? AutopilotValidationManager.startAll(source)
                : AutopilotValidationManager.startOne(source, target);
        if (count <= 0) {
            throw new IllegalStateException("Could not start autonomous-flight validation for " + target);
        }
        startedAt.set(System.currentTimeMillis());
        started.set(true);
    }

    private static void installProfile(Path generated, Path configured) {
        try {
            Files.createDirectories(configured.getParent());
            Files.copy(generated, configured, StandardCopyOption.REPLACE_EXISTING);
        } catch (IOException exception) {
            throw new IllegalStateException("Could not install measured flight profiles: "
                    + exception.getMessage(), exception);
        }
    }

    private static int highestTerrainInRunwayCorridor(ServerLevel level, BlockPos origin) {
        int highest = level.getMinBuildHeight();
        for (int z = -RUNWAY_BEHIND; z <= RUNWAY_AHEAD; z++) {
            int worldZ = origin.getZ() + z;
            for (int x = -RUNWAY_HALF_WIDTH; x <= RUNWAY_HALF_WIDTH; x++) {
                int worldX = origin.getX() + x;
                int surfaceY = level.getHeight(Heightmap.Types.MOTION_BLOCKING, worldX, worldZ) - 1;
                highest = Math.max(highest, surfaceY);
            }
        }
        return highest;
    }

    private static void buildRunway(ServerLevel level, BlockPos surfaceOrigin) {
        for (int z = -RUNWAY_BEHIND; z <= RUNWAY_AHEAD; z++) {
            for (int x = -RUNWAY_HALF_WIDTH; x <= RUNWAY_HALF_WIDTH; x++) {
                BlockPos surface = surfaceOrigin.offset(x, 0, z);
                level.setBlock(surface, Blocks.SMOOTH_STONE.defaultBlockState(), 2);
                for (int y = 1; y <= CLEAR_HEIGHT; y++) {
                    level.setBlock(surface.above(y), Blocks.AIR.defaultBlockState(), 2);
                }
            }
        }
    }

    private static Optional<Path> newestProfile(Path directory, long startedAt) {
        if (!Files.isDirectory(directory)) {
            return Optional.empty();
        }
        try (Stream<Path> stream = Files.walk(directory, 4)) {
            return stream
                    .filter(Files::isRegularFile)
                    .filter(path -> "flight_profiles.json".equals(path.getFileName().toString()))
                    .filter(path -> modified(path).toMillis() >= startedAt)
                    .max(Comparator.comparing(AutonomousFlightGameTests::modified));
        } catch (IOException exception) {
            throw new IllegalStateException("Could not scan measured benchmark profiles: "
                    + exception.getMessage(), exception);
        }
    }

    private static Optional<Path> newestSummary(Path directory, long startedAt) {
        if (!Files.isDirectory(directory)) {
            return Optional.empty();
        }
        try (Stream<Path> stream = Files.list(directory)) {
            return stream
                    .filter(Files::isRegularFile)
                    .filter(path -> path.getFileName().toString().startsWith("validation-summary-"))
                    .filter(path -> modified(path).toMillis() >= startedAt)
                    .max(Comparator.comparing(AutonomousFlightGameTests::modified));
        } catch (IOException exception) {
            throw new IllegalStateException("Could not scan autonomous-flight summaries: "
                    + exception.getMessage(), exception);
        }
    }

    private static FileTime modified(Path path) {
        try {
            return Files.getLastModifiedTime(path);
        } catch (IOException ignored) {
            return FileTime.fromMillis(0L);
        }
    }

    private static Summary readSummary(Path path) {
        try (Reader reader = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
            JsonObject root = GSON.fromJson(reader, JsonObject.class);
            String state = string(root, "state", "unknown");
            int total = integer(root, "total");
            int passed = 0;
            String firstFailure = "none";
            JsonArray results = root.has("results") && root.get("results").isJsonArray()
                    ? root.getAsJsonArray("results") : new JsonArray();
            for (JsonElement element : results) {
                if (!element.isJsonObject()) {
                    continue;
                }
                JsonObject row = element.getAsJsonObject();
                boolean rowPassed = row.has("passed") && row.get("passed").getAsBoolean();
                if (rowPassed) {
                    passed++;
                } else if ("none".equals(firstFailure)) {
                    firstFailure = string(row, "entity_id", "unknown") + ":"
                            + string(row, "final_phase", "unknown") + ":"
                            + string(row, "reason", "unknown");
                }
            }
            return new Summary(state, total, passed, firstFailure, results);
        } catch (IOException | RuntimeException exception) {
            throw new IllegalStateException("Could not read autonomous-flight summary " + path
                    + ": " + exception.getMessage(), exception);
        }
    }

    private static void verifyRunwayStops(MinecraftServer server, JsonArray results) {
        String directoryText = AutopilotLogManager.currentDirectory(server);
        if ("not-opened".equals(directoryText)) {
            throw new IllegalStateException("Autonomous-flight telemetry directory was not opened");
        }
        Path aircraftDirectory = Path.of(directoryText).resolve("aircraft");
        for (JsonElement element : results) {
            if (!element.isJsonObject()) {
                continue;
            }
            JsonObject row = element.getAsJsonObject();
            if (!row.has("passed") || !row.get("passed").getAsBoolean()) {
                continue;
            }
            String uuid = string(row, "aircraft_uuid", "none");
            Path logFile = findAircraftLog(aircraftDirectory, uuid)
                    .orElseThrow(() -> new IllegalStateException(
                            "Missing per-aircraft telemetry for " + uuid));
            JsonObject frame = lastFrame(logFile);
            JsonObject position = object(frame, "position");
            JsonObject home = object(frame, "home_position");
            JsonObject forward = object(frame, "runway_forward");

            double dx = number(position, "x") - number(home, "x");
            double dz = number(position, "z") - number(home, "z");
            double forwardX = number(forward, "x");
            double forwardZ = number(forward, "z");
            double lateral = Math.abs(dx * -forwardZ + dz * forwardX);
            double longitudinal = dx * forwardX + dz * forwardZ;
            String phase = string(frame, "phase", "unknown");

            if (!"PARKED".equals(phase)
                    || lateral > RUNWAY_HALF_WIDTH
                    || longitudinal < -RUNWAY_BEHIND
                    || longitudinal > RUNWAY_AHEAD) {
                throw new IllegalStateException("Aircraft stopped outside the runway corridor: uuid="
                        + uuid + ", phase=" + phase + ", lateral=" + lateral
                        + ", longitudinal=" + longitudinal + ", log=" + logFile.toAbsolutePath());
            }
        }
    }

    private static Optional<Path> findAircraftLog(Path directory, String uuid) {
        if (!Files.isDirectory(directory)) {
            return Optional.empty();
        }
        try (Stream<Path> stream = Files.list(directory)) {
            return stream
                    .filter(Files::isRegularFile)
                    .filter(path -> path.getFileName().toString().contains(uuid))
                    .findFirst();
        } catch (IOException exception) {
            throw new IllegalStateException("Could not scan per-aircraft telemetry: "
                    + exception.getMessage(), exception);
        }
    }

    private static JsonObject lastFrame(Path path) {
        try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
            String line = lines
                    .filter(value -> value.contains("\"event\":\"frame\""))
                    .reduce((first, second) -> second)
                    .orElseThrow(() -> new IllegalStateException(
                            "No telemetry frame found in " + path.toAbsolutePath()));
            return GSON.fromJson(line, JsonObject.class);
        } catch (IOException | RuntimeException exception) {
            throw new IllegalStateException("Could not read final telemetry frame " + path
                    + ": " + exception.getMessage(), exception);
        }
    }

    private static JsonObject object(JsonObject object, String key) {
        if (!object.has(key) || !object.get(key).isJsonObject()) {
            throw new IllegalStateException("Telemetry frame is missing object field " + key);
        }
        return object.getAsJsonObject(key);
    }

    private static double number(JsonObject object, String key) {
        if (!object.has(key) || !object.get(key).isJsonPrimitive()
                || !object.get(key).getAsJsonPrimitive().isNumber()) {
            throw new IllegalStateException("Telemetry frame is missing numeric field " + key);
        }
        return object.get(key).getAsDouble();
    }

    private static int integer(JsonObject object, String key) {
        return object.has(key) && object.get(key).isJsonPrimitive()
                ? object.get(key).getAsInt() : 0;
    }

    private static String string(JsonObject object, String key, String fallback) {
        return object.has(key) && object.get(key).isJsonPrimitive()
                ? object.get(key).getAsString() : fallback;
    }

    private record Summary(String state, int total, int passed,
                           String firstFailure, JsonArray results) {
    }
}
