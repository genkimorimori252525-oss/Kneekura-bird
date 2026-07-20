package com.wwdebug.benchmark;

import net.minecraft.resources.ResourceLocation;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;

public record AircraftMetadata(
        ResourceLocation entityId,
        ResourceLocation dataId,
        String variantGroup,
        String role,
        String faction,
        String doctrine,
        BenchmarkCategory category,
        Map<String, Double> declaredProperties
) {
    public AircraftMetadata {
        role = role == null ? "unknown" : role;
        faction = faction == null ? "unknown" : faction;
        doctrine = doctrine == null ? "unknown" : doctrine;
        declaredProperties = Collections.unmodifiableMap(new LinkedHashMap<>(declaredProperties));
    }
}
