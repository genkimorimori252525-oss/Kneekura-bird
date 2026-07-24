package com.wwdebug.benchmark.mixin;

import com.wwdebug.autopilot.FlightControlOutput;
import com.wwdebug.autopilot.MissionRouteLiveControlBridge;
import net.minecraft.world.entity.Entity;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.ModifyVariable;

/** Inserts owned-route guidance into the existing mission proposal before safety adapters run. */
@Mixin(targets = "com.wwdebug.autopilot.AutonomousFlightManager", remap = false)
abstract class AutonomousFlightRouteGuidanceMixin {
    @ModifyVariable(
            method = "applyControl",
            at = @At(value = "STORE"),
            ordinal = 0,
            remap = false
    )
    private static FlightControlOutput wwdebugBenchmark$applyOwnedRouteGuidance(
            FlightControlOutput baseOutput, Entity aircraft) {
        return MissionRouteLiveControlBridge.apply(aircraft, baseOutput);
    }
}
