package com.wwdebug.benchmark.mixin;

import com.wwdebug.autopilot.AirCombatManeuverManager;
import com.wwdebug.autopilot.AirspaceSafetyProbe;
import com.wwdebug.autopilot.AutonomousFlightManager;
import com.wwdebug.autopilot.AutopilotWheelLockAdapter;
import com.wwdebug.autopilot.CombatAwarenessManager;
import com.wwdebug.autopilot.CombatWeaponManager;
import com.wwdebug.autopilot.DefensiveAirCombatManager;
import com.wwdebug.autopilot.EnergyFighterCounterattackManager;
import com.wwdebug.autopilot.EnergyFighterCrossingCutAdapter;
import com.wwdebug.autopilot.FormationFlightManager;
import com.wwdebug.autopilot.MutualDogfightMissionHoldAdapter;
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
        Entity aircraft = (Entity) (Object) this;
        BenchmarkManager.applyControl(aircraft);
        MutualDogfightMissionHoldAdapter.beforeControl(aircraft);
        AutonomousFlightManager.applyControl(aircraft);
        FormationFlightManager.applyControl(aircraft);
        // Formation collision avoidance has already been applied at this point. Do not let combat
        // overwrite it while the shared CPA probe is dangerous.
        if (!AirspaceSafetyProbe.collisionRisk(aircraft)) {
            // At the high-yo-yo broadside crossing, cut directly through the turn circle instead of
            // waiting for the target to enter a narrow cone and flying past the best intercept.
            boolean crossingCutControl = EnergyFighterCrossingCutAdapter.applyControl(aircraft);
            if (crossingCutControl) {
                EnergyFighterCounterattackManager.clear(aircraft.getUUID());
            }
            // Counterattack recovery runs before ordinary defense. When it owns this tick, stale
            // defensive reacquisition is never applied and cannot overwrite the turn-back.
            boolean counterattackControl = crossingCutControl
                    || EnergyFighterCounterattackManager.applyControl(aircraft);
            if (!counterattackControl) {
                DefensiveAirCombatManager.applyControl(aircraft);
                if (!DefensiveAirCombatManager.active(aircraft)) {
                    AirCombatManeuverManager.applyControl(aircraft);
                }
            }
        }
    }

    @Inject(method = "tick", at = @At("TAIL"), remap = false, require = 0)
    private void wwdebugBenchmark$applyPostPhysicsWheelBrake(CallbackInfo callbackInfo) {
        Entity aircraft = (Entity) (Object) this;
        AutonomousFlightManager.applyPostPhysics(aircraft);
        AutopilotWheelLockAdapter.apply(aircraft);
        CombatAwarenessManager.tick(aircraft);
        CombatWeaponManager.tick(aircraft);
    }
}
