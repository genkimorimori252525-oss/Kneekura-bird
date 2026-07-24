package com.wwdebug.autopilot;

import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.entity.Entity;

import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Live bridge from owned mission-route intent into the ordinary base-autonomy proposal.
 *
 * <p>The bridge is invoked while {@link AutonomousFlightManager} is preparing its mission output,
 * before terrain avoidance, native-flight adaptation, combat overrides, and the single final input
 * write. It therefore cannot bypass any higher-priority safety or authority layer.</p>
 */
public final class MissionRouteLiveControlBridge {
    private static final Set<UUID> ACTIVE_LOGGED = ConcurrentHashMap.newKeySet();
    private static final Set<UUID> COMPLETION_LOGGED = ConcurrentHashMap.newKeySet();

    private MissionRouteLiveControlBridge() {
    }

    public static FlightControlOutput apply(Entity aircraft, FlightControlOutput baseOutput) {
        Objects.requireNonNull(aircraft, "aircraft");
        Objects.requireNonNull(baseOutput, "baseOutput");
        if (!(aircraft.level() instanceof ServerLevel level) || aircraft.level().isClientSide) {
            return baseOutput;
        }

        MinecraftServer server = level.getServer();
        Optional<AutonomousFlightManager.SessionStatus> status =
                AutonomousFlightManager.status(aircraft.getUUID());
        Optional<FlightProfile> profile = AutopilotProfileRegistry.resolve(server, aircraft);
        if (status.isEmpty() || profile.isEmpty()) {
            return baseOutput;
        }

        MissionRouteValidationSetup.applyIfRequested(server, aircraft);
        FlightSnapshot snapshot = FlightSnapshot.capture(aircraft);
        MissionRouteGuidanceAdapter.Decision decision = MissionRouteGuidanceAdapter.plan(
                aircraft.getUUID(),
                status.get().phase(),
                snapshot,
                profile.get(),
                baseOutput);

        if (decision.routeActive()) {
            if (ACTIVE_LOGGED.add(aircraft.getUUID())) {
                AutopilotLogManager.writeEvent(server, aircraft, "route_guidance_start",
                        decision.description(), status.get().phase());
            }
            AutopilotLogManager.writeControlAdapter(server, aircraft, status.get().phase(),
                    decision.description(), snapshot, baseOutput, decision.output());
        } else {
            ACTIVE_LOGGED.remove(aircraft.getUUID());
        }
        if (decision.waypointAdvanced()) {
            AutopilotLogManager.writeEvent(server, aircraft, "route_waypoint_advanced",
                    decision.description(), status.get().phase());
        }
        if (decision.routeCompleted() && COMPLETION_LOGGED.add(aircraft.getUUID())) {
            AutopilotLogManager.writeEvent(server, aircraft, "route_guidance_completed",
                    decision.description(), status.get().phase());
        }

        return decision.routeActive() ? decision.output() : baseOutput;
    }
}
