package com.wwdebug.benchmark.mixin;

import com.google.gson.JsonArray;
import com.wwdebug.autopilot.MissionRouteEvidenceVerifier;
import net.minecraft.server.MinecraftServer;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/** Makes route ownership and safety precedence part of the real Forge GameTest result. */
@Mixin(targets = "com.wwdebug.autopilot.AutonomousFlightGameTests", remap = false)
abstract class AutonomousFlightRouteEvidenceMixin {
    @Inject(method = "verifyRunwayStops", at = @At("RETURN"), require = 1, remap = false)
    private static void wwdebugBenchmark$verifyLiveOwnedRoute(
            MinecraftServer server,
            JsonArray results,
            CallbackInfo callback) {
        MissionRouteEvidenceVerifier.verify(server, results);
    }
}
