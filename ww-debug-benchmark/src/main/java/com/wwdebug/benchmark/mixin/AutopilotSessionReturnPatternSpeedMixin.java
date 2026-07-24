package com.wwdebug.benchmark.mixin;

import com.wwdebug.autopilot.FlightProfile;
import com.wwdebug.autopilot.ReturnToPatternSpeedPolicy;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.ModifyArg;

/** Raises only the long pattern-rejoin target to the measured sustainable turn-speed floor. */
@Mixin(targets = "com.wwdebug.autopilot.AutopilotSession", remap = false)
abstract class AutopilotSessionReturnPatternSpeedMixin {
    @Shadow private FlightProfile profile;

    @ModifyArg(
            method = "returnToPattern",
            at = @At(
                    value = "INVOKE",
                    target = "Lcom/wwdebug/autopilot/AutopilotSession;waypointControl(Lnet/minecraft/world/entity/Entity;Lcom/wwdebug/autopilot/FlightSnapshot;Lnet/minecraft/world/phys/Vec3;DLjava/lang/String;)Lcom/wwdebug/autopilot/FlightControlOutput;"
            ),
            index = 3,
            require = 1
    )
    private double wwdebug$useMeasuredTurnFloorForPatternRejoin(double originalTargetSpeed) {
        return Math.max(originalTargetSpeed, ReturnToPatternSpeedPolicy.targetSpeedBps(profile));
    }
}
