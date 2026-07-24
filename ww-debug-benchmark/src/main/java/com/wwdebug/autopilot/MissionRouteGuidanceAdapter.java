package com.wwdebug.autopilot;

import java.util.Objects;
import java.util.Optional;
import java.util.UUID;

/**
 * Resolves an owned mission route into a base-autonomy proposal without writing aircraft input.
 *
 * <p>Only ordinary cruise/turn phases may use the route. Takeoff, stall recovery, landing, terrain,
 * combat, collision, and player-control layers remain authoritative outside this boundary.</p>
 */
public final class MissionRouteGuidanceAdapter {
    private MissionRouteGuidanceAdapter() {
    }

    public static Decision plan(UUID aircraftId,
                                FlightPhase phase,
                                FlightSnapshot snapshot,
                                FlightProfile profile,
                                FlightControlOutput baseOutput) {
        Objects.requireNonNull(aircraftId, "aircraftId");
        Objects.requireNonNull(phase, "phase");
        Objects.requireNonNull(snapshot, "snapshot");
        Objects.requireNonNull(profile, "profile");
        Objects.requireNonNull(baseOutput, "baseOutput");

        if (!routeEligiblePhase(phase)) {
            return Decision.inactive(baseOutput, "phase_not_route_eligible");
        }

        MissionOrderManager.Assignment mission = MissionOrderManager.current(aircraftId).orElse(null);
        MissionRouteManager.Assignment ownedRoute = MissionRouteManager.current(aircraftId).orElse(null);
        if (mission == null || ownedRoute == null
                || mission.revision() != ownedRoute.missionRevision()
                || !mission.order().orderId().equals(ownedRoute.orderId())) {
            return Decision.inactive(baseOutput, "no_current_owned_route");
        }
        if (ownedRoute.route().completed()) {
            return new Decision(baseOutput, false, false, true, "owned_route_already_complete");
        }

        WaypointGuidancePlanner.Decision guidance = WaypointGuidancePlanner.plan(
                snapshot.position(),
                snapshot.horizontalForward(),
                ownedRoute.route(),
                profile.cruiseSpeedBps());

        MissionRouteManager.Assignment resultingRoute = ownedRoute;
        if (guidance.waypointAdvanced()) {
            Optional<MissionRouteManager.Assignment> advanced = MissionRouteManager.advance(
                    aircraftId,
                    mission.revision(),
                    mission.order().orderId(),
                    snapshot.position());
            if (advanced.isEmpty() || !advanced.get().route().equals(guidance.route())) {
                return Decision.inactive(baseOutput, "route_ownership_changed_during_advance");
            }
            resultingRoute = advanced.get();
        }

        if (guidance.completed()) {
            return new Decision(
                    baseOutput,
                    false,
                    guidance.waypointAdvanced(),
                    true,
                    "owned_route_completed_preserve_base_autonomy");
        }

        MissionOrderManager.Assignment currentMission = MissionOrderManager.current(aircraftId).orElse(null);
        MissionRouteManager.Assignment currentRoute = MissionRouteManager.current(aircraftId).orElse(null);
        if (!mission.equals(currentMission) || !resultingRoute.equals(currentRoute)) {
            return Decision.inactive(baseOutput, "route_ownership_changed_before_control_proposal");
        }

        FlightControlOutput routeOutput = WaypointGuidanceControlAdapter.adapt(
                snapshot,
                profile,
                guidance.target().orElseThrow());
        return new Decision(
                routeOutput,
                true,
                guidance.waypointAdvanced(),
                false,
                guidance.waypointAdvanced()
                        ? "owned_route_waypoint_advanced"
                        : "owned_route_guidance_active");
    }

    private static boolean routeEligiblePhase(FlightPhase phase) {
        return phase == FlightPhase.CRUISE_OUTBOUND
                || phase == FlightPhase.TURN_LEFT
                || phase == FlightPhase.CRUISE_CROSS
                || phase == FlightPhase.TURN_RIGHT;
    }

    public record Decision(FlightControlOutput output,
                           boolean routeActive,
                           boolean waypointAdvanced,
                           boolean routeCompleted,
                           String description) {
        public Decision {
            output = Objects.requireNonNull(output, "output");
            description = Objects.requireNonNull(description, "description");
            if (routeActive && routeCompleted) {
                throw new IllegalArgumentException("a completed route cannot own live guidance");
            }
        }

        static Decision inactive(FlightControlOutput output, String description) {
            return new Decision(output, false, false, false, description);
        }
    }
}
