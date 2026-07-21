package com.wwdebug.benchmark.mixin;

import com.wwdebug.autopilot.AirCombatManeuverManager;
import com.wwdebug.autopilot.AirspaceSafetyProbe;
import com.wwdebug.autopilot.AutonomousFlightManager;
import com.wwdebug.autopilot.AutopilotWheelLockAdapter;
import com.wwdebug.autopilot.CombatAwarenessManager;
import com.wwdebug.autopilot.CombatWeaponManager;
import com.wwdebug.autopilot.DefensiveAirCombatManager;
import com.wwdebug.autopilot.EnergyFighterCounterattackGate;
import com.wwdebug.autopilot.FormationFlightManager;
import com.wwdebug.autopilot.MutualDogfightMissionHoldAdapter;
import com.wwdebug.autopilot.MutualDogfightOpeningCommitmentAdapter;
import com.wwdebug.autopilot.TurnFighterFinalAlignmentAdapter;
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
            // Keep the reciprocal qualification's first opposed crossing deterministic. Once both
            // fighters have passed and opened the range, all ordinary doctrine layers resume.
            boolean openingCommitment =
                    MutualDogfightOpeningCommitmentAdapter.applyControl(aircraft);
            if (!openingCommitment) {
                // Let the high-yo-yo controller complete its reversal instead of replacing a steadily
                // improving target angle with the previous long crossing-cut orbit. New starts are
                // admitted only while the opponent remains inside a useful re-entry envelope.
                boolean counterattackControl =
                        EnergyFighterCounterattackGate.applyControl(aircraft);
                if (!counterattackControl) {
                    DefensiveAirCombatManager.applyControl(aircraft);
                    if (!DefensiveAirCombatManager.active(aircraft)) {
                        AirCombatManeuverManager.applyControl(aircraft);
                        // A turn fighter that is already close to the fixed-gun cone receives a brief
                        // stronger alignment input. The weapon manager still owns every firing gate.
                        TurnFighterFinalAlignmentAdapter.applyControl(aircraft);
                    }
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
