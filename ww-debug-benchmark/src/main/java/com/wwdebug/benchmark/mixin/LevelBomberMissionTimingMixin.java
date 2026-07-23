package com.wwdebug.benchmark.mixin;

import com.wwdebug.autopilot.FlightProfile;
import org.spongepowered.asm.mixin.Final;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.injection.Constant;
import org.spongepowered.asm.mixin.injection.ModifyConstant;

/** Gives measured level bombers enough time to cover their longer outbound mission distance. */
@Mixin(targets = "com.wwdebug.autopilot.AutopilotSession", remap = false)
abstract class LevelBomberMissionTimingMixin {
    @Shadow @Final private FlightProfile profile;

    @ModifyConstant(
            method = "returnToPattern",
            constant = @Constant(intValue = 1800),
            remap = false
    )
    private int wwdebugBenchmark$extendLevelBomberReturnBudget(int originalTicks) {
        return profile.isLevelBomber() ? 2600 : originalTicks;
    }
}
