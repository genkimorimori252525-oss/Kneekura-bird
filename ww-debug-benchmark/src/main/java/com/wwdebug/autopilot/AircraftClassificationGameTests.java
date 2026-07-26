package com.wwdebug.autopilot;

import com.wwdebug.benchmark.AircraftMetadata;
import com.wwdebug.benchmark.AircraftMetadataResolver;
import com.wwdebug.benchmark.WWDebugBenchmarkMod;
import net.minecraft.gametest.framework.GameTest;
import net.minecraft.gametest.framework.GameTestHelper;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.packs.resources.ResourceManager;
import net.minecraftforge.gametest.GameTestHolder;
import net.minecraftforge.gametest.PrefixGameTestTemplate;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Doctrine-arrival contract for every base aircraft.
 *
 * <p>The expected values below are stated independently of
 * {@code data/wwdebug_benchmark/ai/aircraft_classification.json} on purpose. If the two ever
 * disagree the contract fails, which is the point: before this test existed, regenerating the
 * measured profile fixture would silently downgrade all 14 qualified fighters to the balanced
 * tuning without a single compile error or failing assertion.
 */
@GameTestHolder(WWDebugBenchmarkMod.MOD_ID)
@PrefixGameTestTemplate(false)
public final class AircraftClassificationGameTests {
    private static final Map<String, AutopilotDoctrine> EXPECTED = expected();

    private AircraftClassificationGameTests() {
    }

    @GameTest(template = "empty", timeoutTicks = 60, batch = "aircraft_classification_contract")
    public static void everyBaseAircraftResolvesARecognisedDoctrine(GameTestHelper helper) {
        ResourceManager resources = helper.getLevel().getServer().getResourceManager();

        StringBuilder unresolved = new StringBuilder();
        for (String path : EXPECTED.keySet()) {
            AircraftMetadata metadata =
                    AircraftMetadataResolver.resolve(resources, new ResourceLocation("warfare_wings", path));
            if (!AutopilotDoctrine.fromId(metadata.doctrine()).isRecognised()) {
                unresolved.append(' ').append(path).append("=").append(metadata.doctrine());
            }
        }

        check(unresolved.length() == 0,
                "every base aircraft must reach the autopilot with an actionable doctrine, but"
                        + unresolved + " did not");
        helper.succeed();
    }

    @GameTest(template = "empty", timeoutTicks = 60, batch = "aircraft_classification_contract")
    public static void doctrineMatchesTheDeclaredClassification(GameTestHelper helper) {
        ResourceManager resources = helper.getLevel().getServer().getResourceManager();

        StringBuilder wrong = new StringBuilder();
        for (Map.Entry<String, AutopilotDoctrine> entry : EXPECTED.entrySet()) {
            AircraftMetadata metadata = AircraftMetadataResolver.resolve(
                    resources, new ResourceLocation("warfare_wings", entry.getKey()));
            AutopilotDoctrine actual = AutopilotDoctrine.fromId(metadata.doctrine());
            if (actual != entry.getValue()) {
                wrong.append(' ').append(entry.getKey())
                        .append(": expected ").append(entry.getValue().id())
                        .append(" but resolved ").append(actual.id());
            }
        }

        check(wrong.length() == 0, "declared doctrine classification drifted —" + wrong);
        helper.succeed();
    }

    @GameTest(template = "empty", timeoutTicks = 60, batch = "aircraft_classification_contract")
    public static void qualifiedFighterSplitIsPinned(GameTestHelper helper) {
        ResourceManager resources = helper.getLevel().getServer().getResourceManager();

        int turnFighters = 0;
        int energyFighters = 0;
        for (String path : EXPECTED.keySet()) {
            AircraftMetadata metadata =
                    AircraftMetadataResolver.resolve(resources, new ResourceLocation("warfare_wings", path));
            AutopilotDoctrine doctrine = AutopilotDoctrine.fromId(metadata.doctrine());
            if (doctrine == AutopilotDoctrine.TURN_FIGHTER) {
                turnFighters++;
            } else if (doctrine == AutopilotDoctrine.ENERGY_FIGHTER) {
                energyFighters++;
            }
        }

        // The split recorded by the route qualification of all 24 base aircraft.
        check(turnFighters == 3, "expected 3 turn fighters, resolved " + turnFighters);
        check(energyFighters == 11, "expected 11 energy fighters, resolved " + energyFighters);
        helper.succeed();
    }

    @GameTest(template = "empty", timeoutTicks = 60, batch = "aircraft_classification_contract")
    public static void schemeVariantsInheritTheBaseClassification(GameTestHelper helper) {
        ResourceManager resources = helper.getLevel().getServer().getResourceManager();

        AircraftMetadata variant = AircraftMetadataResolver.resolve(
                resources, new ResourceLocation("warfare_wings", "a6m_scheme2"));
        check(AutopilotDoctrine.fromId(variant.doctrine()) == AutopilotDoctrine.TURN_FIGHTER,
                "a paint scheme must not change which doctrine an airframe flies, resolved "
                        + variant.doctrine());
        helper.succeed();
    }

    @GameTest(template = "empty", timeoutTicks = 20, batch = "aircraft_classification_contract")
    public static void unrecognisedDoctrineDegradesInsteadOfThrowing(GameTestHelper helper) {
        check(AutopilotDoctrine.fromId(null) == AutopilotDoctrine.UNKNOWN, "null must not throw");
        check(AutopilotDoctrine.fromId("") == AutopilotDoctrine.UNKNOWN, "blank must not throw");
        check(AutopilotDoctrine.fromId("  ENERGY_FIGHTER  ") == AutopilotDoctrine.ENERGY_FIGHTER,
                "doctrine matching must tolerate padding and case");
        // "escort" is the label the authored data used for all six heavy aircraft. It is not a
        // combat doctrine, and the classification file replaces it — so it must read as
        // unrecognised rather than quietly selecting a tuning.
        check(AutopilotDoctrine.fromId("escort") == AutopilotDoctrine.UNKNOWN,
                "a retired label must not resolve to an actionable doctrine");

        for (AutopilotDoctrine doctrine : AutopilotDoctrine.values()) {
            check(doctrine.id().equals(doctrine.id().toLowerCase(java.util.Locale.ROOT)),
                    "doctrine ids are the wire form asserted by the Python verifiers and must stay "
                            + "lowercase, but " + doctrine.name() + " exposes " + doctrine.id());
        }
        helper.succeed();
    }

    private static Map<String, AutopilotDoctrine> expected() {
        Map<String, AutopilotDoctrine> values = new LinkedHashMap<>();
        values.put("a6m", AutopilotDoctrine.TURN_FIGHTER);
        values.put("spitfire", AutopilotDoctrine.TURN_FIGHTER);
        values.put("yak3", AutopilotDoctrine.TURN_FIGHTER);

        values.put("bf109", AutopilotDoctrine.ENERGY_FIGHTER);
        values.put("f4u", AutopilotDoctrine.ENERGY_FIGHTER);
        values.put("f6f", AutopilotDoctrine.ENERGY_FIGHTER);
        values.put("fw190", AutopilotDoctrine.ENERGY_FIGHTER);
        values.put("ki61", AutopilotDoctrine.ENERGY_FIGHTER);
        values.put("ki84", AutopilotDoctrine.ENERGY_FIGHTER);
        values.put("mc202", AutopilotDoctrine.ENERGY_FIGHTER);
        values.put("mig3", AutopilotDoctrine.ENERGY_FIGHTER);
        values.put("p40e", AutopilotDoctrine.ENERGY_FIGHTER);
        values.put("p47n", AutopilotDoctrine.ENERGY_FIGHTER);
        values.put("p51d", AutopilotDoctrine.ENERGY_FIGHTER);

        values.put("b17", AutopilotDoctrine.LEVEL_BOMBER);
        values.put("b29", AutopilotDoctrine.LEVEL_BOMBER);
        values.put("g10n1", AutopilotDoctrine.LEVEL_BOMBER);
        values.put("g10n2", AutopilotDoctrine.LEVEL_BOMBER);
        values.put("he111", AutopilotDoctrine.LEVEL_BOMBER);

        values.put("g4m", AutopilotDoctrine.TORPEDO_ATTACK);

        values.put("d4y", AutopilotDoctrine.ATTACKER);
        values.put("il2", AutopilotDoctrine.ATTACKER);
        values.put("ju87", AutopilotDoctrine.ATTACKER);
        values.put("sbd", AutopilotDoctrine.ATTACKER);
        return Map.copyOf(values);
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new IllegalStateException(message);
        }
    }
}
