package com.wwdebug.benchmark.mixin;

import com.wwdebug.autopilot.AirCombatManeuverManager;
import com.wwdebug.autopilot.AirspaceSafetyProbe;
import com.wwdebug.autopilot.AutonomousFlightManager;
import com.wwdebug.autopilot.AutopilotWheelLockAdapter;
import com.wwdebug.autopilot.CombatAwarenessManager;
import com.wwdebug.autopilot.CombatWeaponManager;
import com.wwdebug.autopilot.DefensiveAirCombatManager;
import com.wwdebug.autopilot.EnergyFighterApexYawAdapter;
import com.wwdebug.autopilot.FormationFlightManager;
import com.wwdebug.autopilot.TerrainAvoidancePlanner;
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
        AutonomousFlightManager.applyControl(aircraft);
        FormationFlightManager.applyControl(aircraft);
        // Formation, terrain, and collision safety have already been applied. Combat must never
        // overwrite those inputs while one of the shared safety planners is authoritative.
        if (!AirspaceSafetyProbe.collisionRisk(aircraft)
                && !TerrainAvoidancePlanner.active(aircraft)) {
            boolean apexYawControl = EnergyFighterApexYawAdapter.applyControl(aircraft);
            if (!apexYawControl) {
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
