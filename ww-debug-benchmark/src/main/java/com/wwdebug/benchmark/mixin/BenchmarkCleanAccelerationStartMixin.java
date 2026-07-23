package com.wwdebug.benchmark.mixin;

import com.wwdebug.benchmark.ReflectiveAircraft;
import net.minecraft.world.entity.Entity;
import org.spongepowered.asm.mixin.Final;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/** Corrects benchmark instrumentation so acceleration starts are sampled after the hard reset. */
@Mixin(targets = "com.wwdebug.benchmark.BenchmarkManager$AircraftTest", remap = false)
abstract class BenchmarkCleanAccelerationStartMixin {
    @Shadow @Final private Entity aircraft;
    @Shadow private double accelerationInitialSpeed;
    @Shadow private double accelerationInitialEnginePower;

    @Inject(
            method = "advancePhase",
            at = @At(
                    value = "INVOKE",
                    target = "Lcom/wwdebug/benchmark/BenchmarkManager$AircraftTest;resetFlight()V",
                    ordinal = 0,
                    shift = At.Shift.AFTER
            ),
            remap = false
    )
    private void wwdebugBenchmark$sampleCleanAccelerationStart(CallbackInfo callbackInfo) {
        accelerationInitialSpeed = aircraft.getDeltaMovement().horizontalDistance() * 20.0;
        accelerationInitialEnginePower = ReflectiveAircraft.enginePower(aircraft);
    }
}
