package com.wwdebug.autopilot;

import com.wwdebug.benchmark.WWDebugBenchmarkMod;
import net.minecraft.core.BlockPos;
import net.minecraft.gametest.framework.GameTest;
import net.minecraft.gametest.framework.GameTestHelper;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.phys.Vec3;
import net.minecraftforge.gametest.GameTestHolder;
import net.minecraftforge.gametest.PrefixGameTestTemplate;

/**
 * Contract for the shared separation predicate.
 *
 * <p>The danger floors decide two different things in two different classes — whether combat is
 * suppressed, and whether an avoidance manoeuvre is written — so these pin the arithmetic itself
 * rather than either caller.</p>
 */
@GameTestHolder(WWDebugBenchmarkMod.MOD_ID)
@PrefixGameTestTemplate(false)
public final class AirspaceSafetyProbeGameTests {
    private AirspaceSafetyProbeGameTests() {
    }

    @GameTest(template = "empty", timeoutTicks = 40, batch = "airspace_safety_probe")
    public static void aRecedingPairIsNeverDangerousOnPredictedSeparation(GameTestHelper helper) {
        // The regression this guards: dropping the closestTicks > 0 condition would make two
        // aircraft flying apart trip the predicted floor, because the closest approach of a
        // receding pair is behind them.
        Entity a = helper.spawn(EntityType.ARMOR_STAND, new BlockPos(1, 2, 1));
        Entity b = helper.spawn(EntityType.ARMOR_STAND, new BlockPos(1, 2, 1));
        b.setPos(a.getX() + 40.0, a.getY(), a.getZ());
        a.setDeltaMovement(new Vec3(-2.0, 0.0, 0.0));
        b.setDeltaMovement(new Vec3(2.0, 0.0, 0.0));

        AirspaceSafetyProbe.Prediction prediction = AirspaceSafetyProbe.predict(a, b);
        check(prediction.closestTicks() == 0.0,
                "a receding pair must report no future closest approach");
        check(!prediction.dangerous(),
                "40 blocks apart and separating must not be dangerous");
        helper.succeed();
    }

    @GameTest(template = "empty", timeoutTicks = 40, batch = "airspace_safety_probe")
    public static void currentSeparationInsideTheHardFloorIsDangerousEvenWhenStationary(
            GameTestHelper helper) {
        Entity a = helper.spawn(EntityType.ARMOR_STAND, new BlockPos(1, 2, 1));
        Entity b = helper.spawn(EntityType.ARMOR_STAND, new BlockPos(1, 2, 1));
        b.setPos(a.getX() + 5.0, a.getY(), a.getZ());
        a.setDeltaMovement(Vec3.ZERO);
        b.setDeltaMovement(Vec3.ZERO);

        AirspaceSafetyProbe.Prediction prediction = AirspaceSafetyProbe.predict(a, b);
        check(prediction.dangerous(),
                "5 blocks apart breaches the 9-block current floor regardless of motion");
        check(prediction.closestTicks() == 0.0,
                "a stationary pair has no future closest approach");
        helper.succeed();
    }

    @GameTest(template = "empty", timeoutTicks = 40, batch = "airspace_safety_probe")
    public static void aClosingPairIsDangerousBeforeItIsClose(GameTestHelper helper) {
        // Currently far apart, but converging fast enough to breach the predicted floor inside the
        // horizon. This is the whole point of predicting rather than measuring.
        Entity a = helper.spawn(EntityType.ARMOR_STAND, new BlockPos(1, 2, 1));
        Entity b = helper.spawn(EntityType.ARMOR_STAND, new BlockPos(1, 2, 1));
        b.setPos(a.getX() + 60.0, a.getY(), a.getZ());
        a.setDeltaMovement(new Vec3(1.5, 0.0, 0.0));
        b.setDeltaMovement(new Vec3(-1.5, 0.0, 0.0));

        AirspaceSafetyProbe.Prediction prediction = AirspaceSafetyProbe.predict(a, b);
        check(prediction.currentSeparation() > 50.0,
                "the pair must still be far apart, or this proves nothing about prediction");
        check(prediction.closestTicks() > 0.0, "a closing pair must have a future closest approach");
        check(prediction.dangerous(),
                "a head-on closure that breaches the predicted floor must be dangerous early");
        helper.succeed();
    }

    @GameTest(template = "empty", timeoutTicks = 40, batch = "airspace_safety_probe")
    public static void predictionIsSymmetricBetweenTheTwoAircraft(GameTestHelper helper) {
        // Both aircraft evaluate the threat independently and must reach the same verdict;
        // FormationFlightManager then splits them vertically by UUID order. If the verdict were
        // asymmetric, one would climb while the other held course.
        Entity a = helper.spawn(EntityType.ARMOR_STAND, new BlockPos(1, 2, 1));
        Entity b = helper.spawn(EntityType.ARMOR_STAND, new BlockPos(1, 2, 1));
        b.setPos(a.getX() + 30.0, a.getY() + 4.0, a.getZ() + 10.0);
        a.setDeltaMovement(new Vec3(1.2, 0.0, 0.4));
        b.setDeltaMovement(new Vec3(-1.1, 0.0, -0.5));

        AirspaceSafetyProbe.Prediction ab = AirspaceSafetyProbe.predict(a, b);
        AirspaceSafetyProbe.Prediction ba = AirspaceSafetyProbe.predict(b, a);
        check(ab.dangerous() == ba.dangerous(),
                "both aircraft must agree on whether the pair is dangerous");
        check(Math.abs(ab.currentSeparation() - ba.currentSeparation()) < 1.0e-9,
                "current separation must be symmetric");
        check(Math.abs(ab.predictedSeparation() - ba.predictedSeparation()) < 1.0e-9,
                "predicted separation must be symmetric");
        check(Math.abs(ab.closestTicks() - ba.closestTicks()) < 1.0e-9,
                "time to closest approach must be symmetric");
        helper.succeed();
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new IllegalStateException(message);
        }
    }
}
