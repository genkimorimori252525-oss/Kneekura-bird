package com.wwdebug.autopilot;

/**
 * High-level fighter actions selected by utility rather than a hard-coded fixed sequence.
 * Minimum commitment and cooldown values prevent unrealistic action flicker.
 */
public enum AirCombatAction {
    NONE(0, 0),
    INTERCEPT(24, 8),
    ATTACK_APPROACH(20, 8),
    FIRING_PASS(12, 16),
    BREAK_AWAY(28, 12),
    EXTEND(34, 12),
    REPOSITION(30, 10),
    DISENGAGE(50, 20);

    private final int minimumCommitTicks;
    private final int cooldownTicks;

    AirCombatAction(int minimumCommitTicks, int cooldownTicks) {
        this.minimumCommitTicks = minimumCommitTicks;
        this.cooldownTicks = cooldownTicks;
    }

    public int minimumCommitTicks() {
        return minimumCommitTicks;
    }

    public int cooldownTicks() {
        return cooldownTicks;
    }
}
