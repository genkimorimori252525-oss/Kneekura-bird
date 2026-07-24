package com.wwdebug.benchmark.mixin;

import com.wwdebug.autopilot.FlightControlOutput;
import com.wwdebug.autopilot.FlightPhase;
import com.wwdebug.autopilot.MissionRouteLiveControlBridge;
import net.minecraft.server.MinecraftServer;
import net.minecraft.world.entity.Entity;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

import java.util.UUID;

/** Prevents the fixed demonstration mission from timing out underneath owned route navigation. */
@Mixin(targets = "com.wwdebug.autopilot.AutopilotSession", remap = false)
abstract class AutopilotSessionRouteClockMixin {
    @Shadow private UUID aircraftUuid;
    @Shadow private FlightPhase phase;
    @Shadow private int phaseTicks;
    @Shadow private int missionTicks;

    @Inject(method = "tick", at = @At("RETURN"), require = 1, remap = false)
    private void wwdebugBenchmark$holdOrdinaryMissionClock(
            MinecraftServer server,
            Entity aircraft,
            CallbackInfoReturnable<FlightControlOutput> callback) {
        if (MissionRouteLiveControlBridge.shouldHoldMissionClock(aircraftUuid, phase)) {
            phaseTicks = Math.max(0, phaseTicks - 1);
            missionTicks = Math.max(0, missionTicks - 1);
        }
    }
}
