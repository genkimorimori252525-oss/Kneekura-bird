package com.wwdebug.autopilot;

/** Pure policy for the explicitly enabled, read-only mutual GameTest probe. */
final class MutualDogfightObservationPolicy {
    private MutualDogfightObservationPolicy() {
    }

    static boolean enabled(boolean gameTestServer, String scenario, String aircraft,
                           String actualAircraft, String option) {
        return gameTestServer && "dogfight_mutual".equals(scenario)
                && "warfare_wings:a6m".equals(aircraft) && "warfare_wings:a6m".equals(actualAircraft)
                && "true".equals(option);
    }

    static boolean sample(boolean started, long tick) {
        return started && tick >= 0 && tick % 20 == 0;
    }

    static String state(Boolean value) {
        return value == null ? "unknown" : value.toString();
    }

    static String lookup(Object reference, Object visible) {
        if (reference == null) return "unknown";
        if (visible == null) return "not_visible";
        return reference == visible ? "same" : "different";
    }

    static String stage(boolean initial) {
        return initial ? "after_fixture_direct_apply_before_opening" : "before_rebind";
    }
}
