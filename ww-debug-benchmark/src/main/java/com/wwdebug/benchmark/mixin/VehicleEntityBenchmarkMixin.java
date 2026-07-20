package com.wwdebug.benchmark.mixin;

import com.wwdebug.benchmark.BenchmarkManager;
import net.minecraft.world.entity.Entity;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Pseudo;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

@Pseudo
@Mixin(targets = "immersive_aircraft.entity.VehicleEntity", remap = false)
public abstract class VehicleEntityBenchmarkMixin {
    @Inject(method = "tickPilot", at = @At("TAIL"), remap = false, require = 0)
    private void wwdebugBenchmark$applyFixedInput(CallbackInfo callbackInfo) {
        BenchmarkManager.applyControl((Entity) (Object) this);
    }
}
