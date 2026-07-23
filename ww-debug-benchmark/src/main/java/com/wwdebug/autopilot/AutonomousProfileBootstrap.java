package com.wwdebug.autopilot;

import com.wwdebug.benchmark.AircraftMetadataResolver;
import com.wwdebug.benchmark.BenchmarkCategory;
import com.wwdebug.benchmark.BenchmarkManager;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.MinecraftServer;

import java.nio.file.Files;
import java.nio.file.Path;

/** Selects the measured benchmark category required before autonomous-flight validation. */
final class AutonomousProfileBootstrap {
    private AutonomousProfileBootstrap() {
    }

    static boolean measuredProfileAvailable(MinecraftServer server, Path configuredProfile,
                                            String target) {
        if (!Files.isRegularFile(configuredProfile)) {
            return false;
        }
        AutopilotProfileRegistry.reload(server);
        if ("all".equalsIgnoreCase(target)) {
            return !AutopilotProfileRegistry.fighterProfiles(server).isEmpty();
        }
        ResourceLocation id = ResourceLocation.tryParse(target);
        return id != null && AutopilotProfileRegistry.resolve(server, id).isPresent();
    }

    static void startMeasuredBenchmark(CommandSourceStack source, MinecraftServer server,
                                       String target) {
        BenchmarkCategory category = benchmarkCategory(server, target);
        int benchmarkCount = BenchmarkManager.start(source, category, false);
        if (benchmarkCount <= 0) {
            throw new IllegalStateException(
                    "Could not start measured " + category.id() + " benchmark");
        }
    }

    private static BenchmarkCategory benchmarkCategory(MinecraftServer server, String target) {
        if ("all".equalsIgnoreCase(target)) {
            return BenchmarkCategory.FIGHTER;
        }
        ResourceLocation id = ResourceLocation.tryParse(target);
        if (id == null) {
            throw new IllegalStateException(
                    "Invalid aircraft id for measured benchmark: " + target);
        }
        BenchmarkCategory category = AircraftMetadataResolver
                .resolve(server.getResourceManager(), id)
                .category();
        if (category == BenchmarkCategory.ALL || category == BenchmarkCategory.OTHER) {
            throw new IllegalStateException(
                    "Unsupported measured benchmark category for " + target
                            + ": " + category.id());
        }
        return category;
    }
}
