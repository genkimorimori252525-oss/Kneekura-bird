package com.wwdebug.benchmark;

import com.google.gson.Gson;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.packs.resources.Resource;
import net.minecraft.server.packs.resources.ResourceManager;

import java.io.Reader;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Optional;

/**
 * Doctrine and faction classification for the base aircraft, shipped with the benchmark mod.
 *
 * <p>This exists because the published warfare_wings 1.1.4 jar contains 90 aircraft JSON files
 * and not one of them carries an {@code ai} block. {@link AircraftMetadataResolver} already
 * compensates for that on the role axis by backfilling from {@link BenchmarkCategory}; doctrine
 * and faction had no equivalent path, so every aircraft outside the hand-authored fighter fixture
 * arrived at the autopilot as {@code doctrine="unknown"}.
 *
 * <p>The table is the mod author's own {@code ai} block, lifted from the repository's
 * {@code data/warfare_wings/aircraft/*.json} and corrected for the six heavy aircraft that were
 * all labelled {@code escort}. See the resource file for the full provenance note.
 */
final class AircraftClassification {
    private static final Gson GSON = new Gson();
    private static final ResourceLocation SOURCE =
            new ResourceLocation("wwdebug_benchmark", "ai/aircraft_classification.json");

    // The table is immutable per resource reload, so cache it against the manager that produced
    // it. resolve() runs once per aircraft per session; re-reading the file each time would be
    // pure waste, but caching without the identity check would survive a datapack reload.
    private static volatile ResourceManager cachedSource;
    private static volatile Map<String, Entry> cachedTable;

    private AircraftClassification() {
    }

    record Entry(String faction, String doctrine) {
    }

    static Optional<Entry> forBaseEntityId(ResourceManager resources, String baseEntityId) {
        return Optional.ofNullable(table(resources).get(baseEntityId));
    }

    private static Map<String, Entry> table(ResourceManager resources) {
        Map<String, Entry> cached = cachedTable;
        if (cached != null && cachedSource == resources) {
            return cached;
        }

        Map<String, Entry> loaded = load(resources);
        cachedTable = loaded;
        cachedSource = resources;
        return loaded;
    }

    private static Map<String, Entry> load(ResourceManager resources) {
        Optional<Resource> resource = resources.getResource(SOURCE);
        if (resource.isEmpty()) {
            return Map.of();
        }

        try (Reader reader = resource.get().openAsReader()) {
            JsonObject root = GSON.fromJson(reader, JsonObject.class);
            if (root == null || !root.has("aircraft") || !root.get("aircraft").isJsonObject()) {
                return Map.of();
            }

            Map<String, Entry> table = new LinkedHashMap<>();
            for (Map.Entry<String, JsonElement> entry : root.getAsJsonObject("aircraft").entrySet()) {
                if (!entry.getValue().isJsonObject()) {
                    continue;
                }
                JsonObject value = entry.getValue().getAsJsonObject();
                table.put(entry.getKey(), new Entry(
                        string(value, "faction"),
                        string(value, "doctrine")
                ));
            }
            return Map.copyOf(table);
        } catch (Exception ignored) {
            // A malformed classification file must not take the session down: the aircraft simply
            // keeps the doctrine the runtime data gave it, which is the pre-existing behaviour.
            return Map.of();
        }
    }

    private static String string(JsonObject object, String key) {
        return object.has(key) && object.get(key).isJsonPrimitive()
                ? object.get(key).getAsString() : null;
    }
}
