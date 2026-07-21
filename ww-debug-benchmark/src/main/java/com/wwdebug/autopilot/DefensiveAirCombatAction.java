package com.wwdebug.autopilot;

/** Defensive responses selected only while a hostile aircraft is actively threatening this pilot. */
public enum DefensiveAirCombatAction {
    NONE(0, 0),
    DEFENSIVE_BREAK(28, 12),
    DEFENSIVE_JINK(12, 16),
    DIVE_ESCAPE(34, 18);

    private final int minimumCommitTicks;
    private final int cooldownTicks;

    DefensiveAirCombatAction(int minimumCommitTicks, int cooldownTicks) {
        this.minimumCommitTicks = minimumCommitTicks;
        this.cooldownTicks = cooldownTicks;
    }

    int minimumCommitTicks() {
        return minimumCommitTicks;
    }

    int cooldownTicks() {
        return cooldownTicks;
    }
}
