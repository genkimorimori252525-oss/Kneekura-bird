package com.wwdebug.autopilot;

import java.util.EnumMap;

/**
 * Per-doctrine utility, commitment and cooldown tuning for the shared fighter action set.
 * Emergency terrain and collision responses remain outside these weights and always retain priority.
 */
final class AirCombatDoctrineTuning {
    private static final Tuning TURN_FIGHTER = tuning(
            "turn_fighter",
            weights(0.94, 1.16, 1.10, 0.78, 0.70, 0.86, 1.0),
            durations(22, 26, 15, 24, 28, 24, 50),
            durations(6, 6, 13, 15, 15, 9, 20),
            10.0
    );
    private static final Tuning ENERGY_FIGHTER = tuning(
            "energy_fighter",
            // EXTEND enters REPOSITION explicitly after opening the range. Keep that committed setup,
            // but do not let high off-nose REPOSITION or ATTACK_APPROACH utility suppress the turn
            // back into INTERCEPT after the energy fighter has recovered speed.
            weights(1.12, 0.35, 1.04, 1.18, 1.22, 0.30, 1.0),
            // At roughly fifty blocks per second of opening closure, a 34-tick reposition commitment
            // adds about ninety blocks before the fighter may turn back. Twelve ticks still establishes
            // the offset manoeuvre, but releases before the opponent can settle into a rear-quarter lock.
            durations(26, 18, 11, 31, 20, 12, 50),
            durations(8, 10, 18, 10, 8, 8, 20),
            13.0
    );
    private static final Tuning BALANCED = tuning(
            "balanced_fighter",
            weights(1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0),
            durations(24, 20, 12, 28, 34, 30, 50),
            durations(8, 8, 16, 12, 12, 10, 20),
            12.0
    );

    private AirCombatDoctrineTuning() {
    }

    static Tuning resolve(String doctrine) {
        if (doctrine == null) {
            return BALANCED;
        }
        return switch (doctrine.trim().toLowerCase()) {
            case "turn_fighter" -> TURN_FIGHTER;
            case "energy_fighter" -> ENERGY_FIGHTER;
            default -> BALANCED;
        };
    }

    private static Tuning tuning(String name, EnumMap<AirCombatAction, Double> weights,
                                 EnumMap<AirCombatAction, Integer> commitments,
                                 EnumMap<AirCombatAction, Integer> cooldowns,
                                 double switchMargin) {
        return new Tuning(name, weights, commitments, cooldowns, switchMargin);
    }

    private static EnumMap<AirCombatAction, Double> weights(
            double intercept, double approach, double firing, double breakAway,
            double extend, double reposition, double disengage) {
        EnumMap<AirCombatAction, Double> values = new EnumMap<>(AirCombatAction.class);
        values.put(AirCombatAction.NONE, 1.0);
        values.put(AirCombatAction.INTERCEPT, intercept);
        values.put(AirCombatAction.ATTACK_APPROACH, approach);
        values.put(AirCombatAction.FIRING_PASS, firing);
        values.put(AirCombatAction.BREAK_AWAY, breakAway);
        values.put(AirCombatAction.EXTEND, extend);
        values.put(AirCombatAction.REPOSITION, reposition);
        values.put(AirCombatAction.DISENGAGE, disengage);
        return values;
    }

    private static EnumMap<AirCombatAction, Integer> durations(
            int intercept, int approach, int firing, int breakAway,
            int extend, int reposition, int disengage) {
        EnumMap<AirCombatAction, Integer> values = new EnumMap<>(AirCombatAction.class);
        values.put(AirCombatAction.NONE, 0);
        values.put(AirCombatAction.INTERCEPT, intercept);
        values.put(AirCombatAction.ATTACK_APPROACH, approach);
        values.put(AirCombatAction.FIRING_PASS, firing);
        values.put(AirCombatAction.BREAK_AWAY, breakAway);
        values.put(AirCombatAction.EXTEND, extend);
        values.put(AirCombatAction.REPOSITION, reposition);
        values.put(AirCombatAction.DISENGAGE, disengage);
        return values;
    }

    record Tuning(String name, EnumMap<AirCombatAction, Double> weights,
                  EnumMap<AirCombatAction, Integer> commitments,
                  EnumMap<AirCombatAction, Integer> cooldowns,
                  double switchMargin) {
        double weight(AirCombatAction action) {
            return weights.getOrDefault(action, 1.0);
        }

        int commitment(AirCombatAction action) {
            return commitments.getOrDefault(action, action.minimumCommitTicks());
        }

        int cooldown(AirCombatAction action) {
            return cooldowns.getOrDefault(action, action.cooldownTicks());
        }
    }
}
