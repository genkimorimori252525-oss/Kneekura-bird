package com.wwdebug.probe.input.mixin;

import com.wwdebug.probe.input.NativeInputObserver;
import com.wwdebug.probe.input.TraceBuffer;

import net.minecraft.world.entity.Entity;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.Unique;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/** Fixed IA 1.3.3 mapped names/descriptors; callbacks do not cancel or change arguments/state. */
@Mixin(targets = "immersive_aircraft.entity.VehicleEntity", remap = false)
abstract class VehicleInputMixin {
    @Shadow(remap = false) protected float movementX;
    @Shadow(remap = false) protected float movementY;
    @Shadow(remap = false) protected float movementZ;

    @Inject(method = "tickPilot()V", at = @At("HEAD"), require = 1, allow = 1, remap = false)
    private void wwinputObserver$tickHead(CallbackInfo ci) { trace(TraceBuffer.Point.TICK_HEAD, null, null, null); }

    @Inject(method = "tickPilot()V", at = @At("TAIL"), require = 1, allow = 1, remap = false)
    private void wwinputObserver$tickTail(CallbackInfo ci) { trace(TraceBuffer.Point.TICK_TAIL, null, null, null); }

    @Inject(method = "setInputs(FFF)V", at = @At("HEAD"), require = 1, allow = 1, remap = false)
    private void wwinputObserver$setHead(float x, float y, float z, CallbackInfo ci) {
        trace(TraceBuffer.Point.SET_HEAD, x, y, z);
    }

    @Inject(method = "setInputs(FFF)V", at = @At("RETURN"), require = 1, allow = 1, remap = false)
    private void wwinputObserver$setReturn(float x, float y, float z, CallbackInfo ci) {
        trace(TraceBuffer.Point.SET_RETURN, x, y, z);
    }

    @Unique
    private void trace(TraceBuffer.Point point, Float ax, Float ay, Float az) {
        try {
            NativeInputObserver.capture((Entity) (Object) this, point, movementX, movementY, movementZ, ax, ay, az);
        } catch (Throwable ignored) {
            try { NativeInputObserver.hookFailure(); } catch (Throwable ignoredAgain) { /* report must be present */ }
        }
    }
}
