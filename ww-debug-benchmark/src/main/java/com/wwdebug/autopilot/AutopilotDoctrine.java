package com.wwdebug.autopilot;

import java.util.Locale;

/**
 * The doctrine vocabulary the autopilot understands.
 *
 * <p>Doctrine arrives as a free-form string from aircraft data, so this enum is deliberately
 * lenient: unrecognised input becomes {@link #UNKNOWN} rather than throwing. Before this type
 * existed the same leniency was implicit in a {@code default -> BALANCED} switch arm, which
 * meant an aircraft with no doctrine and an aircraft with a misspelt doctrine were
 * indistinguishable. {@link #isRecognised()} makes that difference observable.
 */
public enum AutopilotDoctrine {
    TURN_FIGHTER("turn_fighter"),
    ENERGY_FIGHTER("energy_fighter"),
    LEVEL_BOMBER("level_bomber"),
    TORPEDO_ATTACK("torpedo_attack"),
    ATTACKER("attacker"),
    UNKNOWN("unknown");

    private final String id;

    AutopilotDoctrine(String id) {
        this.id = id;
    }

    /**
     * The lowercase wire form. Telemetry, aircraft data and the Python scenario verifiers all
     * match on this, never on {@link #name()} — {@code name()} would yield {@code ENERGY_FIGHTER}
     * and silently break every verifier that asserts on the doctrine label.
     */
    public String id() {
        return id;
    }

    public boolean isRecognised() {
        return this != UNKNOWN;
    }

    /** Never throws and never returns null. Unrecognised input is {@link #UNKNOWN}, by design. */
    public static AutopilotDoctrine fromId(String value) {
        if (value == null) {
            return UNKNOWN;
        }
        String normalized = value.trim().toLowerCase(Locale.ROOT);
        for (AutopilotDoctrine doctrine : values()) {
            if (doctrine.id.equals(normalized)) {
                return doctrine;
            }
        }
        return UNKNOWN;
    }
}
