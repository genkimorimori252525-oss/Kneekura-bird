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

    static boolean visibilityEnabled(String option) {
        return "true".equals(option);
    }

    /** Conditional inference only: the two reads are not an atomic snapshot. */
    static String visibility(Boolean range, Boolean combined) {
        if (range == null || combined == null) return "unknown";
        if (!range) return combined ? "changed_or_inconsistent" : "unknown";
        return combined ? "true_if_stable" : "false_if_stable";
    }

    static String visibilityAtTicks(Boolean range, Boolean combined, Long startTick, Long endTick) {
        if (startTick == null || endTick == null || startTick < 0 || !startTick.equals(endTick)) return "unknown";
        return visibility(range, combined);
    }

    /** Block coordinates and timestamps belong in output, not the change fingerprint. */
    static String visibilityFingerprint(String base, Boolean chunkMatches, Boolean compositeBefore,
                                        String before, Boolean compositeAfter, String after, boolean error) {
        return base + ":visibility_probe=true"
                + ":block_chunk_matches=" + state(chunkMatches)
                + ":composite_before=" + state(compositeBefore) + ":visibility_before=" + before
                + ":composite_after=" + state(compositeAfter) + ":visibility_after=" + after
                + ":visibility_probe_error=" + error;
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
