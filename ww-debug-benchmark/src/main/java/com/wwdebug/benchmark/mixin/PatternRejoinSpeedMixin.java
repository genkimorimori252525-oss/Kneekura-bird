package com.wwdebug.benchmark.mixin;

import com.wwdebug.autopilot.FlightProfile;
import com.wwdebug.autopilot.PatternRejoinSpeedPolicy;
import org.spongepowered.asm.mixin.Final;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.ModifyArg;

/** Keeps the long, turning pattern-rejoin transit above the measured turn-speed floor. */
@Mixin(targets = "com.wwdebug.autopilot.AutopilotSession", remap = false)
abstract class PatternRejoinSpeedMixin {
    @Shadow @Final private FlightProfile profile;

    @ModifyArg(
            method = "returnToPattern",
            at = @At(
                    value = "INVOKE",
                    target = "Lcom/wwdebug/autopilot/AutopilotSession;waypointControl(Lnet/minecraft/world/entity/Entity;Lcom/wwdebug/autopilot/FlightSnapshot;Lnet/minecraft/world/phys/Vec3;DLjava/lang/String;)Lcom/wwdebug/autopilot/FlightControlOutput;"
            ),
            index = 3,
            require = 1,
            remap = false
    )
    private double wwdebugBenchmark$useMeasuredPatternRejoinSpeed(double originalTargetSpeed) {
        return PatternRejoinSpeedPolicy.targetSpeedBps(profile);
    }
}
