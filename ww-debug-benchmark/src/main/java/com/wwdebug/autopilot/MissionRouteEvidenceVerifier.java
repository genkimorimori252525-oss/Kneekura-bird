package com.wwdebug.autopilot;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import net.minecraft.server.MinecraftServer;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.stream.Stream;

/** Strict evidence contract for exact-physics owned-route integration proofs. */
public final class MissionRouteEvidenceVerifier {
    private static final String SCENARIO_PROPERTY = "wwdebug.flightGameTestScenario";
    private static final String AIRCRAFT_PROPERTY = "wwdebug.flightGameTestAircraft";
    private static final String A6M = "warfare_wings:a6m";
    private static final String G4M = "warfare_wings:g4m";
    private static final Set<String> TERRAIN_OVERRIDES = Set.of(
            "predictive_terrain_avoidance",
            "terrain_emergency_climb");

    private MissionRouteEvidenceVerifier() {
    }

    public static void verify(MinecraftServer server, JsonArray results) {
        String requested = requestedAircraft();
        if (!proofRequested(requested)) {
            return;
        }

        JsonObject result = proofResult(results, requested);
        String uuid = text(result, "aircraft_uuid");
        String directoryText = AutopilotLogManager.currentDirectory(server);
        if ("not-opened".equals(directoryText)) {
            throw new IllegalStateException("Route evidence telemetry directory was not opened");
        }

        Path log = findAircraftLog(Path.of(directoryText).resolve("aircraft"), uuid);
        List<JsonObject> rows = readRows(log);
        require(count(rows, "route_validation_assigned") == 1,
                requested + " expected one route_validation_assigned event");
        require(count(rows, "route_guidance_start") == 1,
                requested + " expected one route_guidance_start event");
        require(count(rows, "route_guidance_completed") == 1,
                requested + " expected one route_guidance_completed event");

        int assignedIndex = firstIndex(rows, "route_validation_assigned");
        int startIndex = firstIndex(rows, "route_guidance_start");
        int completedIndex = firstIndex(rows, "route_guidance_completed");
        JsonObject assigned = rows.get(assignedIndex);
        JsonObject start = rows.get(startIndex);
        JsonObject completed = rows.get(completedIndex);
        long startTick = number(start, "server_tick");
        long completedTick = number(completed, "server_tick");
        String assignedReason = text(assigned, "reason");
        require(assignedReason.contains("aircraft=" + requested),
                "assignment evidence did not identify the requested aircraft");
        if (G4M.equals(requested)) {
            require(assignedReason.contains("role=torpedo_bomber"),
                    "G4M profile did not preserve torpedo_bomber role");
            require(assignedReason.contains("compact=true"),
                    "G4M did not use the compact representative route");
        }
        require(assignedIndex <= startIndex && completedIndex > startIndex && completedTick > startTick,
                "route completion did not occur after assignment and activation");
        require("CRUISE_OUTBOUND".equals(text(start, "phase")),
                "route did not activate in CRUISE_OUTBOUND");
        require("CRUISE_OUTBOUND".equals(text(completed, "phase")),
                "ordinary mission phase advanced while route owned navigation");

        List<Integer> remaining = new ArrayList<>();
        for (JsonObject row : rows) {
            if ("route_waypoint_advanced".equals(text(row, "event"))) {
                remaining.add(remainingFrom(text(row, "reason")));
            }
        }
        require(remaining.equals(List.of(3, 2, 1, 0)),
                "waypoints were skipped or advanced out of order: " + remaining);

        Map<Long, AdapterOrder> adapters = new HashMap<>();
        boolean routeControlApplied = false;
        boolean routeGroundContact = false;
        boolean phaseTransitionDuringRoute = false;
        boolean releaseToOrdinaryMission = false;
        for (int index = 0; index < rows.size(); index++) {
            JsonObject row = rows.get(index);
            long tick = optionalNumber(row, "server_tick", -1L);
            String event = text(row, "event");
            boolean withinOwnedRoute = index >= startIndex && index <= completedIndex;
            if (withinOwnedRoute) {
                if ("control_adapter".equals(event)
                        && "follow_owned_waypoint_route".equals(text(row, "applied_action_reason"))) {
                    routeControlApplied = true;
                    adapters.computeIfAbsent(tick, ignored -> new AdapterOrder()).routeIndex = index;
                }
                if ("control_adapter".equals(event)
                        && TERRAIN_OVERRIDES.contains(text(row, "applied_safety_override"))) {
                    adapters.computeIfAbsent(tick, ignored -> new AdapterOrder()).terrainIndex = index;
                }
                if (index > startIndex && index < completedIndex
                        && "phase_transition".equals(event)) {
                    phaseTransitionDuringRoute = true;
                }
                if ("frame".equals(event) && Boolean.TRUE.equals(booleanValue(row, "on_ground"))) {
                    routeGroundContact = true;
                }
            }
            if (index > completedIndex
                    && tick >= completedTick
                    && "phase_transition".equals(event)
                    && text(row, "reason").startsWith(
                    "CRUISE_OUTBOUND->TURN_LEFT:outbound_cruise_sample_complete")) {
                releaseToOrdinaryMission = true;
            }
        }

        require(routeControlApplied, "no live owned-route control proposal was applied");
        require(!phaseTransitionDuringRoute,
                "ordinary demonstration mission advanced underneath route ownership");
        require(!routeGroundContact, "aircraft touched the ground while route guidance was active");
        require(releaseToOrdinaryMission,
                "route completion did not release the aircraft back to the ordinary mission");

        if (A6M.equals(requested)) {
            boolean terrainOverrodeRoute = adapters.values().stream().anyMatch(order ->
                    order.routeIndex >= 0 && order.terrainIndex > order.routeIndex);
            require(terrainOverrodeRoute,
                    "terrain avoidance never overrode an A6M route proposal in the same tick");
        }
    }

    private static boolean proofRequested(String requested) {
        return "full".equals(System.getProperty(SCENARIO_PROPERTY, "").trim().toLowerCase(Locale.ROOT))
                && (A6M.equals(requested) || G4M.equals(requested));
    }

    private static String requestedAircraft() {
        return System.getProperty(AIRCRAFT_PROPERTY, "").trim().toLowerCase(Locale.ROOT);
    }

    private static JsonObject proofResult(JsonArray results, String requested) {
        for (JsonElement element : results) {
            if (!element.isJsonObject()) {
                continue;
            }
            JsonObject row = element.getAsJsonObject();
            if (requested.equals(text(row, "entity_id"))
                    && Boolean.TRUE.equals(booleanValue(row, "passed"))) {
                return row;
            }
        }
        throw new IllegalStateException("Passed representative result was unavailable for " + requested);
    }

    private static Path findAircraftLog(Path directory, String uuid) {
        try (Stream<Path> files = Files.list(directory)) {
            return files.filter(Files::isRegularFile)
                    .filter(path -> path.getFileName().toString().contains(uuid))
                    .findFirst()
                    .orElseThrow(() -> new IllegalStateException(
                    "Missing route evidence telemetry for " + uuid));
        } catch (IOException exception) {
            throw new IllegalStateException("Could not scan route evidence telemetry", exception);
        }
    }

    private static List<JsonObject> readRows(Path log) {
        List<JsonObject> rows = new ArrayList<>();
        try (Stream<String> lines = Files.lines(log, StandardCharsets.UTF_8)) {
            lines.forEach(line -> {
                try {
                    JsonElement value = JsonParser.parseString(line);
                    if (value.isJsonObject()) {
                        rows.add(value.getAsJsonObject());
                    }
                } catch (RuntimeException ignored) {
                }
            });
        } catch (IOException exception) {
            throw new IllegalStateException("Could not read route evidence telemetry " + log, exception);
        }
        return rows;
    }

    private static int count(List<JsonObject> rows, String event) {
        return (int) rows.stream().filter(row -> event.equals(text(row, "event"))).count();
    }

    private static int firstIndex(List<JsonObject> rows, String event) {
        for (int index = 0; index < rows.size(); index++) {
            if (event.equals(text(rows.get(index), "event"))) {
                return index;
            }
        }
        throw new IllegalStateException("Missing event " + event);
    }

    private static int remainingFrom(String reason) {
        int index = reason.lastIndexOf(":remaining=");
        if (index < 0) {
            throw new IllegalStateException("Waypoint event lacks remaining count: " + reason);
        }
        try {
            return Integer.parseInt(reason.substring(index + 11));
        } catch (NumberFormatException exception) {
            throw new IllegalStateException("Invalid waypoint remaining count: " + reason, exception);
        }
    }

    private static String text(JsonObject object, String key) {
        return object.has(key) && object.get(key).isJsonPrimitive()
                ? object.get(key).getAsString() : "";
    }

    private static long number(JsonObject object, String key) {
        if (!object.has(key) || !object.get(key).isJsonPrimitive()) {
            throw new IllegalStateException("Missing numeric route evidence field " + key);
        }
        return object.get(key).getAsLong();
    }

    private static long optionalNumber(JsonObject object, String key, long fallback) {
        try {
            return object.has(key) ? object.get(key).getAsLong() : fallback;
        } catch (RuntimeException ignored) {
            return fallback;
        }
    }

    private static Boolean booleanValue(JsonObject object, String key) {
        try {
            return object.has(key) ? object.get(key).getAsBoolean() : null;
        } catch (RuntimeException ignored) {
            return null;
        }
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new IllegalStateException("Owned-route evidence failed: " + message);
        }
    }

    private static final class AdapterOrder {
        private int routeIndex = -1;
        private int terrainIndex = -1;
    }
}
