package com.wwdebug.autopilot;

public enum FlightPhase {
    STARTUP,
    TAKEOFF_ROLL,
    ROTATE,
    CLIMB,
    CRUISE_OUTBOUND,
    TURN_LEFT,
    CRUISE_CROSS,
    TURN_RIGHT,
    STALL_SETUP,
    STALL_ENTRY,
    STALL_RECOVERY,
    RETURN_TO_PATTERN,
    DOWNWIND,
    BASE,
    FINAL,
    FLARE,
    TOUCHDOWN,
    BRAKE,
    GO_AROUND,
    PARKED,
    ABORTED;

    public boolean isLandingPhase() {
        return switch (this) {
            case RETURN_TO_PATTERN, DOWNWIND, BASE, FINAL, FLARE, TOUCHDOWN, BRAKE, GO_AROUND -> true;
            default -> false;
        };
    }

    public boolean isAirborneMissionPhase() {
        return switch (this) {
            case ROTATE, CLIMB, CRUISE_OUTBOUND, TURN_LEFT, CRUISE_CROSS, TURN_RIGHT,
                    STALL_SETUP, STALL_ENTRY, STALL_RECOVERY, RETURN_TO_PATTERN,
                    DOWNWIND, BASE, FINAL, FLARE, GO_AROUND -> true;
            default -> false;
        };
    }

    public boolean isTerminal() {
        return this == PARKED || this == ABORTED;
    }
}