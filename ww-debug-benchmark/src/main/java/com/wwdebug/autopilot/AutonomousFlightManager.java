package com.wwdebug.autopilot;

import com.wwdebug.benchmark.ReflectiveAircraft;
import com.wwdebug.benchmark.WWDebugBenchmarkMod;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.util.Mth;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.Mob;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.phys.Vec3;

import java.lang.reflect.Field;
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
    private static final Map<UUID, Integer> FLARE_EXTENSIONS = new ConcurrentHashMap<>();
    private static final Field SESSION_RUNWAY_FORWARD = sessionField("runwayForward");
    private static final Field SESSION_PHASE = sessionField("phase");
    private static final Field SESSION_PHASE_TICKS = sessionField("phaseTicks");
    private static final Field SESSION_TRANSITION_REASON = sessionField("transitionReason");

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
            AutopilotValidationCheckpoint.applyIfRequested(server, aircraft, session);
        }

        FlightControlOutput planned = entry.session.tick(server, aircraft);
        FlightSnapshot snapshot = FlightSnapshot.capture(aircraft);
        extendFlareIfSafe(server, aircraft, entry.session, snapshot, planned);
        AdaptedControl adapted = adaptForNativeFlight(entry.session, snapshot, planned);
        if (adapted.overridden()) {
            AutopilotLogManager.writeControlAdapter(server, aircraft, entry.session.phase(),
                    adapted.reason(), snapshot, planned, adapted.output());
        }
        FlightControlOutput applied = adapted.output();
        // The controller uses conventional heading-error sign. Immersive Aircraft's lateral input
        // axis is the opposite sign, so convert only at the final hardware-adapter boundary.
        ReflectiveAircraft.applyControl(aircraft, -applied.x(), applied.y(), applied.z(),
                applied.engineTarget());
    }

    private static void extendFlareIfSafe(MinecraftServer server, Entity aircraft,
                                          AutopilotSession session, FlightSnapshot snapshot,
                                          FlightControlOutput planned) {
        if (session.phase() != FlightPhase.GO_AROUND
                || !"flare_timeout_without_ground_contact".equals(session.transitionReason())
                || snapshot.onGround()
                || snapshot.altitudeAboveGround() > 20.0
                || snapshot.verticalSpeedBps() > 1.0) {
            return;
        }
        Vec3 runway = runwayForward(session, planned.desiredDirection());
        double desiredYaw = Math.toDegrees(Math.atan2(-runway.x, runway.z));
        double headingError = Math.abs(Mth.wrapDegrees((float) (desiredYaw - snapshot.yawDeg())));
        if (headingError > 8.0) {
            return;
        }
        int extensions = FLARE_EXTENSIONS.getOrDefault(aircraft.getUUID(), 0);
        if (extensions >= 1) {
            return;
        }
        try {
            SESSION_PHASE.set(session, FlightPhase.FLARE);
            SESSION_PHASE_TICKS.setInt(session, 0);
            SESSION_TRANSITION_REASON.set(session, "native_aligned_flare_extension");
            FLARE_EXTENSIONS.put(aircraft.getUUID(), extensions + 1);
            AutopilotLogManager.writeEvent(server, aircraft, "native_flare_extension",
                    "aligned_descent_continues_below_20_blocks", FlightPhase.FLARE);
        } catch (IllegalAccessException exception) {
            WWDebugBenchmarkMod.LOGGER.warn("Could not extend aligned flare", exception);
        }
    }

    private static AdaptedControl adaptForNativeFlight(AutopilotSession session,
                                                        FlightSnapshot snapshot,
                                                        FlightControlOutput planned) {
        if (session.phase() == FlightPhase.FLARE && !snapshot.onGround()) {
            double agl = snapshot.altitudeAboveGround();
            double desiredPitch;
            String stage;
            if (agl > 7.0) {
                desiredPitch = Mth.clamp((agl - 3.0) * 0.36, 4.5, 10.0);
                stage = "descent";
            } else if (agl > 3.0) {
                desiredPitch = 2.0;
                stage = "roundout";
            } else {
                desiredPitch = -0.5;
                stage = "ground_cushion";
            }

            float z = (float) Mth.clamp(
                    (desiredPitch - snapshot.pitchDeg()) / 18.0,
                    -0.78,
                    0.78
            );
            double approachSpeed = session.profile().approachSpeedBps();
            double stallEnergyGate = session.profile().stallGuardSpeedBps() * 1.45;
            float engine;
            if (snapshot.speedBps() < stallEnergyGate) {
                engine = 1.0f;
            } else if (snapshot.speedBps() < approachSpeed * 0.80) {
                engine = 0.72f;
            } else if (agl > 3.0) {
                engine = 0.38f;
            } else {
                engine = 0.12f;
            }

            Vec3 runway = runwayForward(session, planned.desiredDirection());
            double desiredYaw = Math.toDegrees(Math.atan2(-runway.x, runway.z));
            double headingError = Mth.wrapDegrees((float) (desiredYaw - snapshot.yawDeg()));
            float x = (float) Mth.clamp(headingError / 38.0, -0.65, 0.65);
            return new AdaptedControl(copyWithHeading(planned, x, z, engine, runway, headingError,
                    "native_flare_" + stage + "_with_runway_heading",
                    "native_landing_" + stage + "_adapter"), true,
                    "flare_" + stage + "_holds_runway_heading_until_ground_contact");
        }

        if (session.phase() == FlightPhase.GO_AROUND && !snapshot.onGround()) {
            double altitudeError = planned.targetAltitude() - snapshot.position().y;
            double desiredPitch = Mth.clamp(
                    -altitudeError * 0.16 + snapshot.verticalSpeedBps() * 0.30,
                    -8.0,
                    6.0
            );
            if (snapshot.speedBps() < planned.targetSpeedBps() * 0.90) {
                desiredPitch = Math.max(desiredPitch, -4.0);
            }
            if (altitudeError < -12.0) {
                desiredPitch = Math.max(desiredPitch, 2.5);
            }
            float z = (float) Mth.clamp(
                    (desiredPitch - snapshot.pitchDeg()) / 18.0,
                    -0.78,
                    0.78
            );
            return new AdaptedControl(copyWith(planned, z, 1.0f,
                    "native_go_around_balance_speed_and_target_altitude",
                    "native_go_around_energy_adapter"), true,
                    "go_around_pitch_limited_for_speed_and_altitude_capture");
        }

        return new AdaptedControl(planned, false, "none");
    }

    private static FlightControlOutput copyWith(FlightControlOutput original, float z,
                                                 float engineTarget, String reason,
                                                 String safetyOverride) {
        return new FlightControlOutput(
                original.x(),
                original.y(),
                z,
                engineTarget,
                original.desiredDirection(),
                original.targetAltitude(),
                original.targetSpeedBps(),
                original.headingErrorDeg(),
                original.altitudeError(),
                original.speedErrorBps(),
                original.stallRisk(),
                original.terrainRisk(),
                reason,
                safetyOverride
        );
    }

    private static FlightControlOutput copyWithHeading(FlightControlOutput original, float x, float z,
                                                        float engineTarget, Vec3 desiredDirection,
                                                        double headingError, String reason,
                                                        String safetyOverride) {
        return new FlightControlOutput(
                x,
                original.y(),
                z,
                engineTarget,
                desiredDirection,
                original.targetAltitude(),
                original.targetSpeedBps(),
                headingError,
                original.altitudeError(),
                original.speedErrorBps(),
                original.stallRisk(),
                original.terrainRisk(),
                reason,
                safetyOverride
        );
    }

    private static Vec3 runwayForward(AutopilotSession session, Vec3 fallback) {
        try {
            Object value = SESSION_RUNWAY_FORWARD.get(session);
            if (value instanceof Vec3 vector && vector.horizontalDistanceSqr() > 1.0e-8) {
                return new Vec3(vector.x, 0.0, vector.z).normalize();
            }
        } catch (IllegalAccessException ignored) {
            // Fall through to the controller's desired direction.
        }
        Vec3 horizontal = new Vec3(fallback.x, 0.0, fallback.z);
        return horizontal.lengthSqr() > 1.0e-8 ? horizontal.normalize() : new Vec3(0.0, 0.0, 1.0);
    }

    private static Field sessionField(String name) {
        try {
            Field field = AutopilotSession.class.getDeclaredField(name);
            field.setAccessible(true);
            return field;
        } catch (NoSuchFieldException exception) {
            throw new ExceptionInInitializerError(exception);
        }
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
        FLARE_EXTENSIONS.remove(aircraft.getUUID());
        AutopilotValidationCheckpoint.forget(aircraft.getUUID());
        if (removed == null || !(aircraft.level() instanceof ServerLevel level)) {
            return;
        }
        AutopilotLogManager.closeAircraft(level.getServer(), aircraft, removed.session.phase(), reason);
    }

    private record SessionEntry(Entity aircraft, AutopilotSession session) {
    }

    private record AdaptedControl(FlightControlOutput output, boolean overridden, String reason) {
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
