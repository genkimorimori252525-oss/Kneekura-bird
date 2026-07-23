package com.wwdebug.benchmark.mixin;

import com.wwdebug.autopilot.AutonomousFlightManager;
import com.wwdebug.autopilot.AutopilotWheelLockAdapter;
import com.wwdebug.autopilot.ControlAuthorityArbiter;
import com.wwdebug.autopilot.FighterCombatFacade;
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
        Entity aircraft = (Entity) (Object) this;
        ControlAuthorityArbiter.applyControl(aircraft);
    }

    @Inject(method = "tick", at = @At("TAIL"), remap = false, require = 0)
    private void wwdebugBenchmark$applyPostPhysicsWheelBrake(CallbackInfo callbackInfo) {
        Entity aircraft = (Entity) (Object) this;
        AutonomousFlightManager.applyPostPhysics(aircraft);
        AutopilotWheelLockAdapter.apply(aircraft);
        FighterCombatFacade.tick(aircraft);
    }
}
