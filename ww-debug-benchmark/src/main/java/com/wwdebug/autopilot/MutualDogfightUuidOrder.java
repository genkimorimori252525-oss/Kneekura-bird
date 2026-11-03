package com.wwdebug.autopilot;

import java.util.Optional;
import java.util.UUID;

/** Test-only UUID plan; ordinary servers and runs without an explicit option remain untouched. */
final class MutualDogfightUuidOrder {
    // The two v4 aircraft IDs have equal UUID.hashCode() values. Both compare below both pilot
    // IDs, so swapping aircraft order does not also swap the known aircraft-to-pilot comparisons.
    private static final UUID LOW = UUID.fromString("10000000-0000-4000-8000-000000000001");
    private static final UUID HIGH = UUID.fromString("20000000-0000-4000-8000-000030000001");
    private static final UUID PRIMARY_PILOT = UUID.fromString("70000000-0000-4000-8000-000000000002");
    private static final UUID OPPONENT_PILOT = UUID.fromString("70000000-0000-4000-8000-000000000003");

    private MutualDogfightUuidOrder() {
    }

    static Optional<Plan> resolve(boolean gameTestServer, String scenario, String target, String option) {
        if (!gameTestServer || option == null) {
            return Optional.empty();
        }
        if (!"dogfight_mutual".equals(scenario) || !"warfare_wings:a6m".equals(target)) {
            throw new IllegalArgumentException("UUID order is limited to the A6M mutual GameTest");
        }
        return switch (option) {
            case "a6m-low" -> Optional.of(new Plan(option, LOW, PRIMARY_PILOT, HIGH, OPPONENT_PILOT));
            case "a6m-high" -> Optional.of(new Plan(option, HIGH, PRIMARY_PILOT, LOW, OPPONENT_PILOT));
            default -> throw new IllegalArgumentException("unknown mutual GameTest UUID order: " + option);
        };
    }

    /** Assess one insertion without assuming that a hidden entity is available through lookup. */
    static String registrationStatus(boolean accepted, boolean addedToWorld, boolean removed,
                                     UUID expectedUuid, UUID actualUuid, Object entity, Object visible) {
        if (!accepted || !addedToWorld || removed || entity == null || expectedUuid == null
                || !expectedUuid.equals(actualUuid) || (visible != null && visible != entity)) {
            throw new IllegalStateException("mutual UUID fixture registration failed");
        }
        return visible == entity ? "visible" : "hidden_or_unavailable";
    }

    record Plan(String order, UUID primaryAircraft, UUID primaryPilot,
                UUID opponentAircraft, UUID opponentPilot) {
    }
}
