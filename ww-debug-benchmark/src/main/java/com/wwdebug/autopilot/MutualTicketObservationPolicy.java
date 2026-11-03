package com.wwdebug.autopilot;

/** Pure policy for the opt-in GameTest force-loop observer. */
final class MutualTicketObservationPolicy {
    private MutualTicketObservationPolicy() {
    }

    static boolean enabled(boolean gameTestServer, String scenario, String configured,
                           String actual, String option) {
        return gameTestServer && "dogfight_mutual".equals(scenario)
                && "warfare_wings:a6m".equals(configured)
                && "warfare_wings:a6m".equals(actual) && "true".equals(option);
    }

    static String state(Boolean value) {
        return value == null ? "unknown" : value.toString();
    }

    static String action(boolean encountered, boolean complete, Boolean forcedBefore, Boolean setterResult) {
        if (!encountered) return complete ? "not_encountered" : "unknown";
        if (forcedBefore == null) return "unknown";
        if (forcedBefore) return "already_forced";
        if (setterResult == null) return "attempt_incomplete";
        return setterResult ? "attempt_returned_true" : "attempt_returned_false";
    }

    static boolean emit(String previous, String current, long tick) {
        return previous == null || !previous.equals(current) || (tick >= 0 && tick % 20 == 0);
    }
}
