package com.wwdebug.benchmark;

import java.util.Arrays;
import java.util.Locale;

public enum BenchmarkCategory {
    ALL("all"),
    FIGHTER("fighter"),
    ATTACKER("attacker"),
    BOMBER("bomber"),
    TORPEDO_BOMBER("torpedo_bomber"),
    OTHER("other");

    private final String id;

    BenchmarkCategory(String id) {
        this.id = id;
    }

    public String id() {
        return id;
    }

    public boolean matches(AircraftMetadata metadata) {
        return this == ALL || this == metadata.category();
    }

    public static BenchmarkCategory fromRole(String role) {
        if (role == null || role.isBlank()) {
            return OTHER;
        }
        String normalized = role.toLowerCase(Locale.ROOT).replace('-', '_').replace(' ', '_');
        return switch (normalized) {
            case "fighter", "interceptor" -> FIGHTER;
            case "attacker", "attack", "ground_attack", "strike" -> ATTACKER;
            case "bomber", "heavy_bomber", "medium_bomber", "dive_bomber" -> BOMBER;
            case "torpedo_bomber", "torpedo" -> TORPEDO_BOMBER;
            default -> OTHER;
        };
    }

    public static BenchmarkCategory byId(String id) {
        return Arrays.stream(values())
                .filter(value -> value.id.equalsIgnoreCase(id))
                .findFirst()
                .orElse(null);
    }
}
