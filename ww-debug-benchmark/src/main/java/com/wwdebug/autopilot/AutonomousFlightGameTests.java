package com.wwdebug.autopilot;

import com.google.gson.Gson;
import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.wwdebug.benchmark.WWDebugBenchmarkMod;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.core.BlockPos;
import net.minecraft.gametest.framework.GameTest;
import net.minecraft.gametest.framework.GameTestAssertException;
import net.minecraft.gametest.framework.GameTestHelper;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.phys.Vec2;
import net.minecraft.world.phys.Vec3;
import net.minecraftforge.gametest.GameTestHolder;
import net.minecraftforge.gametest.PrefixGameTestTemplate;

import java.io.IOException;
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.FileTime;
import java.util.Comparator;
import java.util.Optional;

/**
 * Headless integration test using the real Forge server, real aircraft entities and real physics.
 *
 * <p>Set {@code -PflightTestAircraft=all} to execute every fighter sequentially. The default smoke
 * test executes the A6M only. Runtime mod jars and the measured profile file are staged by
 * {@code prepareFlightGameTestRuntime}.</p>
 */
@GameTestHolder(WWDebugBenchmarkMod.MOD_ID)
@PrefixGameTestTemplate(false)
public final class AutonomousFlightGameTests {
    private static final Gson GSON = new Gson();
    private static final int RUNWAY_HALF_WIDTH = 14;
    private static final int RUNWAY_BEHIND = 210;
    private static final int RUNWAY_AHEAD = 720;

    private AutonomousFlightGameTests() {
    }

    @GameTest(template = "empty", timeoutTicks = 260_000, batch = "autonomous_flight")
    public static void measuredProfileAutonomousFlight(GameTestHelper helper) {
        ServerLevel level = helper.getLevel();
        MinecraftServer server = level.getServer();
        BlockPos templateOrigin = helper.absolutePos(BlockPos.ZERO);
        BlockPos runwaySurface = templateOrigin.offset(0, -1, 0);
        buildRunway(level, runwaySurface);

        Vec3 aircraftAnchor = Vec3.atBottomCenterOf(runwaySurface.above());
        CommandSourceStack source = server.createCommandSourceStack()
                .withLevel(level)
                .withPosition(aircraftAnchor)
                .withRotation(new Vec2(0.0f, 0.0f))
                .withSuppressedOutput();

        Path summaryDirectory = server.getWorldPath(net.minecraft.world.level.storage.LevelResource.ROOT)
                .resolve("wwdebug")
                .resolve("autopilot");
        long startedAt = System.currentTimeMillis();
        String target = System.getProperty("wwdebug.flightGameTestAircraft", "warfare_wings:a6m");
        int started = "all".equalsIgnoreCase(target)
                ? AutopilotValidationManager.startAll(source)
                : AutopilotValidationManager.startOne(source, target);
        if (started <= 0) {
            throw new GameTestAssertException("Could not start autonomous-flight validation for " + target);
        }

        helper.succeedWhen(() -> {
            Path summary = newestSummary(summaryDirectory, startedAt)
                    .orElseThrow(() -> new GameTestAssertException(
                            "Autonomous-flight validation is still running for " + target));
            Summary result = readSummary(summary);
            if (!"complete".equals(result.state())) {
                throw new GameTestAssertException("Autonomous-flight validation ended as "
                        + result.state() + "; summary=" + summary.toAbsolutePath());
            }
            if (result.passed() != result.total()) {
                throw new GameTestAssertException("Autonomous-flight validation failed: "
                        + result.passed() + "/" + result.total() + " passed; first failure="
                        + result.firstFailure() + "; summary=" + summary.toAbsolutePath());
            }
        });
    }

    private static void buildRunway(ServerLevel level, BlockPos surfaceOrigin) {
        for (int z = -RUNWAY_BEHIND; z <= RUNWAY_AHEAD; z++) {
            for (int x = -RUNWAY_HALF_WIDTH; x <= RUNWAY_HALF_WIDTH; x++) {
                BlockPos surface = surfaceOrigin.offset(x, 0, z);
                level.setBlockAndUpdate(surface, Blocks.SMOOTH_STONE.defaultBlockState());
                // Keep the immediate aircraft corridor deterministic even if the GameTest world
                // generator or a previous failed run left blocks behind.
                for (int y = 1; y <= 8; y++) {
                    level.setBlockAndUpdate(surface.above(y), Blocks.AIR.defaultBlockState());
                }
            }
        }
    }

    private static Optional<Path> newestSummary(Path directory, long startedAt) {
        if (!Files.isDirectory(directory)) {
            return Optional.empty();
        }
        try (var stream = Files.list(directory)) {
            return stream
                    .filter(Files::isRegularFile)
                    .filter(path -> path.getFileName().toString().startsWith("validation-summary-"))
                    .filter(path -> modified(path).toMillis() >= startedAt)
                    .max(Comparator.comparing(AutonomousFlightGameTests::modified));
        } catch (IOException exception) {
            throw new GameTestAssertException("Could not scan autonomous-flight summaries: "
                    + exception.getMessage());
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
            return new Summary(state, total, passed, firstFailure);
        } catch (IOException | RuntimeException exception) {
            throw new GameTestAssertException("Could not read autonomous-flight summary " + path
                    + ": " + exception.getMessage());
        }
    }

    private static int integer(JsonObject object, String key) {
        return object.has(key) && object.get(key).isJsonPrimitive()
                ? object.get(key).getAsInt() : 0;
    }

    private static String string(JsonObject object, String key, String fallback) {
        return object.has(key) && object.get(key).isJsonPrimitive()
                ? object.get(key).getAsString() : fallback;
    }

    private record Summary(String state, int total, int passed, String firstFailure) {
    }
}
