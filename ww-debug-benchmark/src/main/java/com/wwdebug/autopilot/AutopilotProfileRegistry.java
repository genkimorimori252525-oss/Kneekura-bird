package com.wwdebug.autopilot;

import com.google.gson.Gson;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.wwdebug.benchmark.AircraftMetadata;
import com.wwdebug.benchmark.AircraftMetadataResolver;
import com.wwdebug.benchmark.WWDebugBenchmarkMod;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.MinecraftServer;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.level.storage.LevelResource;
import net.minecraftforge.fml.loading.FMLPaths;

import javax.annotation.Nullable;
import java.io.IOException;
import java.io.Reader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

public final class AutopilotProfileRegistry {
    private static final Gson GSON = new Gson();
    private static final Object LOCK = new Object();
    private static volatile Map<String, FlightProfile> profiles = Map.of();
    private static volatile Path loadedPath;
    private static volatile boolean loadAttempted;

    private AutopilotProfileRegistry() {
    }

    public static Optional<FlightProfile> resolve(MinecraftServer server, Entity aircraft) {
        ensureLoaded(server);
        ResourceLocation entityId = BuiltInRegistries.ENTITY_TYPE.getKey(aircraft.getType());
        AircraftMetadata metadata = AircraftMetadataResolver.resolve(server.getResourceManager(), entityId);
        ResourceLocation baseId = AircraftMetadataResolver.baseEntityId(entityId);

        List<String> keys = List.of(
                metadata.variantGroup(),
                entityId.toString(),
                entityId.getPath(),
                baseId.toString(),
                baseId.getPath()
        );
        for (String key : keys) {
            FlightProfile profile = profiles.get(key);
            if (profile != null) {
                return Optional.of(profile);
            }
        }
        return Optional.empty();
    }

    public static int reload(MinecraftServer server) {
        synchronized (LOCK) {
            loadAttempted = true;
            Path source = locateProfileFile(server);
            if (source == null) {
                profiles = Map.of();
                loadedPath = null;
                WWDebugBenchmarkMod.LOGGER.warn("No measured flight_profiles.json was found; mob autopilot remains disabled");
                return 0;
            }

            try (Reader reader = Files.newBufferedReader(source)) {
                JsonObject root = GSON.fromJson(reader, JsonObject.class);
                if (root == null) {
                    throw new IOException("Profile root is empty");
                }
                Map<String, FlightProfile> loaded = new LinkedHashMap<>();
                for (Map.Entry<String, JsonElement> entry : root.entrySet()) {
                    if (!entry.getValue().isJsonObject()) {
                        continue;
                    }
                    FlightProfile profile = parse(entry.getKey(), entry.getValue().getAsJsonObject());
                    if (profile == null) {
                        continue;
                    }
                    loaded.put(entry.getKey(), profile);
                    loaded.put(profile.profileId().toString(), profile);
                    loaded.put(profile.profileId().getPath(), profile);
                }
                profiles = Map.copyOf(loaded);
                loadedPath = source;
                WWDebugBenchmarkMod.LOGGER.info("Loaded {} autonomous-flight profile keys from {}", loaded.size(), source);
                return loaded.size();
            } catch (IOException | RuntimeException exception) {
                profiles = Map.of();
                loadedPath = null;
                WWDebugBenchmarkMod.LOGGER.error("Could not load measured flight profiles from {}", source, exception);
                return 0;
            }
        }
    }

    public static String sourceDescription() {
        Path path = loadedPath;
        return path == null ? "none" : path.toAbsolutePath().toString();
    }

    public static int profileKeyCount() {
        return profiles.size();
    }

    private static void ensureLoaded(MinecraftServer server) {
        if (!loadAttempted) {
            reload(server);
        }
    }

    @Nullable
    private static Path locateProfileFile(MinecraftServer server) {
        Path configured = FMLPaths.CONFIGDIR.get().resolve("warfare_wings").resolve("flight_profiles.json");
        if (Files.isRegularFile(configured)) {
            return configured;
        }

        Path benchmarkRoot = server.getWorldPath(LevelResource.ROOT)
                .resolve("wwdebug")
                .resolve("benchmarks");
        if (!Files.isDirectory(benchmarkRoot)) {
            return null;
        }

        List<Path> candidates = new ArrayList<>();
        try (var stream = Files.walk(benchmarkRoot, 4)) {
            stream.filter(Files::isRegularFile)
                    .filter(path -> "flight_profiles.json".equals(path.getFileName().toString()))
                    .forEach(candidates::add);
        } catch (IOException exception) {
            WWDebugBenchmarkMod.LOGGER.warn("Could not scan benchmark profiles under {}", benchmarkRoot, exception);
            return null;
        }

        return candidates.stream().max(Comparator.comparingLong(AutopilotProfileRegistry::modifiedTime)).orElse(null);
    }

    private static long modifiedTime(Path path) {
        try {
            return Files.getLastModifiedTime(path).toMillis();
        } catch (IOException ignored) {
            return Long.MIN_VALUE;
        }
    }

    @Nullable
    private static FlightProfile parse(String key, JsonObject object) {
        Double stall = number(object, "stall_guard_speed_bps");
        Double cruise = number(object, "cruise_speed_bps");
        Double climb = number(object, "climb_target_speed_bps");
        Double turn = number(object, "turn_speed_floor_bps");
        Double top = number(object, "measured_top_speed_bps");
        if (stall == null || cruise == null || climb == null || turn == null || top == null) {
            WWDebugBenchmarkMod.LOGGER.warn("Skipping incomplete autonomous-flight profile {}", key);
            return null;
        }

        ResourceLocation id = key.contains(":")
                ? ResourceLocation.tryParse(key)
                : ResourceLocation.tryParse("warfare_wings:" + key);
        if (id == null) {
            return null;
        }

        try {
            return new FlightProfile(
                    id,
                    string(object, "role", "unknown"),
                    string(object, "doctrine", "unknown"),
                    stall,
                    cruise,
                    climb,
                    turn,
                    number(object, "brake_lead_blocks"),
                    number(object, "brake_distance_lower_bound_blocks"),
                    top
            );
        } catch (IllegalArgumentException exception) {
            WWDebugBenchmarkMod.LOGGER.warn("Skipping invalid autonomous-flight profile {}: {}", key, exception.getMessage());
            return null;
        }
    }

    @Nullable
    private static Double number(JsonObject object, String key) {
        if (!object.has(key) || object.get(key).isJsonNull() || !object.get(key).isJsonPrimitive()
                || !object.get(key).getAsJsonPrimitive().isNumber()) {
            return null;
        }
        double value = object.get(key).getAsDouble();
        return Double.isFinite(value) ? value : null;
    }

    private static String string(JsonObject object, String key, String fallback) {
        return object.has(key) && object.get(key).isJsonPrimitive()
                ? object.get(key).getAsString() : fallback;
    }
}