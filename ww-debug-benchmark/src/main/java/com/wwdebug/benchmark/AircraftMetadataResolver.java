package com.wwdebug.benchmark;

import com.google.gson.Gson;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.packs.resources.Resource;
import net.minecraft.server.packs.resources.ResourceManager;

import java.io.IOException;
import java.io.Reader;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import java.util.regex.Pattern;

public final class AircraftMetadataResolver {
    private static final Gson GSON = new Gson();
    private static final Pattern SCHEME_SUFFIX = Pattern.compile("_scheme\\d+$", Pattern.CASE_INSENSITIVE);

    private AircraftMetadataResolver() {
    }

    public static AircraftMetadata resolve(ResourceManager resources, ResourceLocation entityId) {
        ResourceLocation exactDataId = dataId(entityId);
        ResourceLocation baseEntityId = baseEntityId(entityId);
        ResourceLocation baseDataId = dataId(baseEntityId);

        ParsedMetadata parsed = read(resources, exactDataId)
                .or(() -> read(resources, baseDataId))
                .orElseGet(() -> infer(entityId));

        BenchmarkCategory category = BenchmarkCategory.fromRole(parsed.role());
        if (category == BenchmarkCategory.OTHER) {
            category = inferCategory(entityId.getPath());
        }

        // Released aircraft data may predate the optional ai block. The JSON still contains the
        // authoritative physical properties, so keep it, but fill only the missing classification
        // from the stable registry id. This avoids replacing the aircraft data with a test-only
        // resource pack and keeps old releases compatible with measured-profile AI validation.
        String resolvedRole = parsed.role();
        if (isUnknown(resolvedRole) && category != BenchmarkCategory.OTHER) {
            resolvedRole = category.id();
        }

        return new AircraftMetadata(
                entityId,
                parsed.dataId() == null ? exactDataId : parsed.dataId(),
                baseEntityId.toString(),
                resolvedRole,
                parsed.faction(),
                parsed.doctrine(),
                category,
                parsed.properties()
        );
    }

    public static ResourceLocation baseEntityId(ResourceLocation id) {
        String basePath = SCHEME_SUFFIX.matcher(id.getPath()).replaceFirst("");
        return new ResourceLocation(id.getNamespace(), basePath);
    }

    private static ResourceLocation dataId(ResourceLocation entityId) {
        return new ResourceLocation(entityId.getNamespace(), "aircraft/" + entityId.getPath() + ".json");
    }

    private static Optional<ParsedMetadata> read(ResourceManager resources, ResourceLocation dataId) {
        Optional<Resource> resource = resources.getResource(dataId);
        if (resource.isEmpty()) {
            return Optional.empty();
        }

        try (Reader reader = resource.get().openAsReader()) {
            JsonObject root = GSON.fromJson(reader, JsonObject.class);
            if (root == null) {
                return Optional.empty();
            }

            JsonObject ai = root.has("ai") && root.get("ai").isJsonObject()
                    ? root.getAsJsonObject("ai")
                    : new JsonObject();
            String role = string(ai, "role", "unknown");
            String faction = string(ai, "faction", "unknown");
            String doctrine = string(ai, "doctrine", "unknown");

            Map<String, Double> properties = new LinkedHashMap<>();
            if (root.has("properties") && root.get("properties").isJsonObject()) {
                for (Map.Entry<String, JsonElement> entry : root.getAsJsonObject("properties").entrySet()) {
                    if (entry.getValue().isJsonPrimitive() && entry.getValue().getAsJsonPrimitive().isNumber()) {
                        properties.put(entry.getKey(), entry.getValue().getAsDouble());
                    }
                }
            }
            return Optional.of(new ParsedMetadata(dataId, role, faction, doctrine, properties));
        } catch (IOException | RuntimeException ignored) {
            return Optional.empty();
        }
    }

    private static ParsedMetadata infer(ResourceLocation entityId) {
        BenchmarkCategory category = inferCategory(entityId.getPath());
        return new ParsedMetadata(dataId(entityId), category.id(), "unknown", "unknown", Map.of());
    }

    private static BenchmarkCategory inferCategory(String path) {
        String value = path.toLowerCase(Locale.ROOT);
        // G4M is the base torpedo-bomber representative. Public 1.1.4 aircraft data may predate
        // the optional ai block, so preserve its repository-authoritative role during fallback.
        if (containsAny(value, "g4m", "torpedo")) {
            return BenchmarkCategory.TORPEDO_BOMBER;
        }
        if (containsAny(value, "b17", "b29", "g10n", "he111", "bomber")) {
            return BenchmarkCategory.BOMBER;
        }
        if (containsAny(value, "ju87", "sbd", "d4y", "il2", "attacker", "attack")) {
            return BenchmarkCategory.ATTACKER;
        }
        if (containsAny(value, "p40", "p51", "p47", "f4u", "f6f", "a6m", "ki61", "ki84",
                "fw190", "bf109", "yak3", "mig3", "mc202", "spitfire", "fighter")) {
            return BenchmarkCategory.FIGHTER;
        }
        return BenchmarkCategory.OTHER;
    }

    private static boolean containsAny(String value, String... needles) {
        for (String needle : needles) {
            if (value.contains(needle)) {
                return true;
            }
        }
        return false;
    }

    private static boolean isUnknown(String value) {
        return value == null || value.isBlank() || "unknown".equalsIgnoreCase(value);
    }

    private static String string(JsonObject object, String key, String fallback) {
        return object.has(key) && object.get(key).isJsonPrimitive()
                ? object.get(key).getAsString()
                : fallback;
    }

    private record ParsedMetadata(
            ResourceLocation dataId,
            String role,
            String faction,
            String doctrine,
            Map<String, Double> properties
    ) {
    }
}
