package com.wwdebug.autopilot;

import com.wwdebug.benchmark.ReflectiveAircraft;
import com.wwdebug.benchmark.WWDebugBenchmarkMod;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.Mob;
import net.minecraft.world.entity.player.Player;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

public final class AutonomousFlightManager {
    private static final Map<UUID, SessionEntry> SESSIONS = new ConcurrentHashMap<>();
    private static final Set<UUID> MISSING_PROFILE_WARNINGS = ConcurrentHashMap.newKeySet();

    private AutonomousFlightManager() {
    }

    public static void applyControl(Entity aircraft) {
        if (aircraft.level().isClientSide || !ReflectiveAircraft.isAirplane(aircraft)
                || !ReflectiveAircraft.isControllable(aircraft)) {
            return;
        }

        Entity pilot = aircraft.getControllingPassenger();
        if (pilot instanceof Player || !(pilot instanceof Mob)) {
            stopSession(aircraft, "controlling_passenger_is_not_a_mob");
            return;
        }

        if (!(aircraft.level() instanceof ServerLevel level)) {
            return;
        }
        MinecraftServer server = level.getServer();
        SessionEntry entry = SESSIONS.get(aircraft.getUUID());
        if (entry == null) {
            Optional<FlightProfile> resolved = AutopilotProfileRegistry.resolve(server, aircraft);
            if (resolved.isEmpty()) {
                if (MISSING_PROFILE_WARNINGS.add(aircraft.getUUID())) {
                    WWDebugBenchmarkMod.LOGGER.warn(
                            "Mob autopilot disabled for {} because no measured flight profile was found (source={})",
                            aircraft.getName().getString(), AutopilotProfileRegistry.sourceDescription());
                    AutopilotLogManager.writeEvent(server, aircraft, "session_rejected",
                            "missing_measured_flight_profile", FlightPhase.ABORTED);
                }
                return;
            }
            FlightProfile profile = resolved.get();
            if (!profile.isFighter()) {
                return;
            }
            AutopilotSession session = new AutopilotSession(aircraft, profile);
            entry = new SessionEntry(aircraft, session);
            SESSIONS.put(aircraft.getUUID(), entry);
            MISSING_PROFILE_WARNINGS.remove(aircraft.getUUID());
            AutopilotLogManager.writeEvent(server, aircraft, "session_start",
                    "mob_controlling_passenger_and_measured_fighter_profile", FlightPhase.STARTUP);
        }

        FlightControlOutput output = entry.session.tick(server, aircraft);
        ReflectiveAircraft.applyControl(aircraft, output.x(), output.y(), output.z(), output.engineTarget());
    }

    public static void serverTick(MinecraftServer server) {
        for (SessionEntry entry : new ArrayList<>(SESSIONS.values())) {
            Entity aircraft = entry.aircraft;
            if (aircraft.isRemoved() || aircraft.getServer() != server) {
                stopSession(aircraft, "aircraft_removed_or_server_changed");
                continue;
            }
            Entity pilot = aircraft.getControllingPassenger();
            if (pilot instanceof Player || !(pilot instanceof Mob)) {
                stopSession(aircraft, "mob_pilot_dismounted_or_player_took_control");
            }
        }
        AutopilotValidationManager.tick(server);
    }

    public static void stopAll(MinecraftServer server) {
        for (SessionEntry entry : new ArrayList<>(SESSIONS.values())) {
            if (entry.aircraft.getServer() == server) {
                stopSession(entry.aircraft, "server_stopping");
            }
        }
        AutopilotValidationManager.stopSilently(server);
        AutopilotLogManager.closeServer(server);
    }

    public static Optional<SessionStatus> status(UUID aircraftUuid) {
        SessionEntry entry = SESSIONS.get(aircraftUuid);
        if (entry == null) {
            return Optional.empty();
        }
        AutopilotSession session = entry.session;
        return Optional.of(new SessionStatus(
                aircraftUuid,
                entry.aircraft.getName().getString(),
                session.profile().profileId().toString(),
                session.profile().doctrine(),
                session.phase(),
                session.phaseTicks(),
                session.missionTicks(),
                session.transitionReason()
        ));
    }

    public static List<SessionStatus> activeStatuses() {
        List<SessionStatus> statuses = new ArrayList<>();
        for (UUID uuid : SESSIONS.keySet()) {
            status(uuid).ifPresent(statuses::add);
        }
        statuses.sort(Comparator.comparing(SessionStatus::aircraftName));
        return statuses;
    }

    public static void forceStop(UUID aircraftUuid, String reason) {
        SessionEntry entry = SESSIONS.get(aircraftUuid);
        if (entry != null) {
            stopSession(entry.aircraft, reason);
        }
    }

    private static void stopSession(Entity aircraft, String reason) {
        SessionEntry removed = SESSIONS.remove(aircraft.getUUID());
        MISSING_PROFILE_WARNINGS.remove(aircraft.getUUID());
        if (removed == null || !(aircraft.level() instanceof ServerLevel level)) {
            return;
        }
        AutopilotLogManager.closeAircraft(level.getServer(), aircraft, removed.session.phase(), reason);
    }

    private record SessionEntry(Entity aircraft, AutopilotSession session) {
    }

    public record SessionStatus(
            UUID aircraftUuid,
            String aircraftName,
            String profileId,
            String doctrine,
            FlightPhase phase,
            int phaseTicks,
            int missionTicks,
            String transitionReason
    ) {
        public boolean complete() {
            return phase == FlightPhase.PARKED;
        }

        public boolean failed() {
            return phase == FlightPhase.ABORTED;
        }
    }
}