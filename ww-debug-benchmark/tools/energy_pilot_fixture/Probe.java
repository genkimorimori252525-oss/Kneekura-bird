package com.wwdebug.autopilot;

import com.wwdebug.benchmark.ReflectiveAircraft;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.Mob;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.phys.Vec3;

import java.lang.reflect.Constructor;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/** Artificial callbacks and state seeding: not a Forge GameTest or native input observer. */
public final class Probe {
    public static final List<String> events = new ArrayList<>();
    public static final UUID attackerId = new UUID(0, 1);
    public static Mob pilotA, pilotB, pilotSame;
    public static Entity target;
    public static boolean missingTarget, noThreat, noGun, defensiveThreat, restoreOnClear;
    public static boolean hookFired, innerSwitch;
    public static String scenario;
    public static final FlightProfile profile = new FlightProfile(new ResourceLocation("fixture", "p47n"),
            "fighter", "energy_fighter", 10.27, 32.72, 22, 34.64, null, null, 50);

    public static void restoreDefensiveState(Entity entity) {
        throw new AssertionError("unused fake logger reentry");
    }

    static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    static boolean stack(String cls, String method) {
        for (StackTraceElement frame : Thread.currentThread().getStackTrace()) {
            if (frame.getClassName().endsWith("." + cls) && frame.getMethodName().equals(method)) return true;
        }
        return false;
    }

    public static void onUuid(Entity entity) { }

    public static void onPilot(Entity entity) {
        if (entity != target) return;
        if (stack("AirCombatManeuverManager", "evaluateWithPilot")) {
            if (scenario.equals("fallback-outer-a-inner-b") && !innerSwitch) {
                check(entity.pilot == pilotA, "inner switch expects A");
                innerSwitch = true;
                entity.pilot = pilotB;
            }
            events.add("offensive-pilot:" + (entity.pilot == pilotA ? "A" : entity.pilot == pilotB ? "B" : "other"));
        } else if (stack("EnergyFighterApexYawAdapter", "applyControl")) {
            events.add("energy-pilot:" + (entity.pilot == pilotA ? "A" : "other"));
        }
    }

    public static void onRemovedGetter(Entity entity) {
        if (entity != target || hookFired || !stack("ControlAuthorityArbiter", "attemptPendingWrite")) return;
        check(events.contains("energy-pilot:A"), "energy pilot read not reached");
        check(events.stream().anyMatch(x -> x.startsWith("offensive-pilot:")), "offensive pilot read not reached");
        check(AutopilotLogManager.adapters.stream().anyMatch(x -> x.contains(":combat_")), "offensive proposal not observed");
        check(AirCombatManeuverManager.currentAim(entity.getUUID(), attackerId).isPresent(), "offensive aim absent");
        boolean alignment = AutopilotLogManager.adapters.stream().anyMatch(x -> x.contains("energy_coupled_final_alignment"));
        check(alignment == scenario.startsWith("alignment-"), "alignment branch not reached as requested");
        hookFired = true;
        events.add("pending-guard:alignment=" + alignment + ":prior-writes=" + ReflectiveAircraft.writes.size());
        switch (scenario) {
            case "fallback-same", "alignment-same", "fallback-outer-a-inner-b" -> { }
            case "fallback-swap", "alignment-swap" -> entity.pilot = pilotB;
            case "fallback-same-uuid" -> entity.pilot = pilotSame;
            case "fallback-player" -> entity.pilot = new Player();
            case "fallback-empty" -> entity.pilot = null;
            case "fallback-client" -> entity.level().isClientSide = true;
            case "fallback-removed" -> entity.removed = true;
            default -> throw new AssertionError("unexpected guard hook scenario");
        }
    }

    @SuppressWarnings({"unchecked", "rawtypes"})
    static void seedDoctrine(Entity aircraft) throws Exception {
        Class<?> stateClass = Class.forName("com.wwdebug.autopilot.EnergyFighterApexYawAdapter$State");
        Constructor<?> ctor = stateClass.getDeclaredConstructors()[0];
        ctor.setAccessible(true);
        Object state = ctor.newInstance(attackerId, 100, 1.0, 100.0, 100.0, 0.0, 0.0, 0.0);
        Class<?> stageClass = Class.forName("com.wwdebug.autopilot.EnergyFighterApexYawAdapter$Stage");
        var stage = stateClass.getDeclaredField("stage");
        stage.setAccessible(true);
        stage.set(state, Enum.valueOf((Class<? extends Enum>) stageClass, "DOCTRINE"));
        var states = EnergyFighterApexYawAdapter.class.getDeclaredField("STATES");
        states.setAccessible(true);
        ((Map<UUID, Object>) states.get(null)).put(aircraft.getUUID(), state);
    }

    public static void main(String[] args) throws Exception {
        scenario = args[0];
        ServerLevel world = new ServerLevel();
        Entity aircraft = new Entity(new UUID(0, 2), world);
        Entity enemyAircraft = new Entity(new UUID(0, 4), world);
        LivingEntity enemyPilot = new LivingEntity(attackerId);
        target = aircraft;
        pilotA = new Mob(new UUID(0, 3));
        pilotB = new Mob(new UUID(0, 5));
        pilotSame = new Mob(new UUID(0, 3));
        aircraft.pilot = pilotA;
        aircraft.vel = new Vec3(0, 0, 30.779231357359148 / 20.0);
        enemyAircraft.vel = aircraft.vel;
        enemyAircraft.pos = new Vec3(scenario.startsWith("alignment-") ? 6.0 : 0.0, 100, 50);
        enemyPilot.world = world;
        enemyPilot.pos = enemyAircraft.pos;
        enemyPilot.vel = aircraft.vel;
        enemyPilot.vehicle = enemyAircraft;
        world.entities.add(aircraft);
        world.entities.add(enemyPilot);
        AutopilotValidationCheckpoint.ticks = 100;
        if (scenario.equals("terrain")) TerrainAvoidancePlanner.enabled = true;
        if (scenario.equals("collision")) enemyPilot.vel = new Vec3(0, 0, 0.75);
        seedDoctrine(aircraft);
        var authority = ControlAuthorityArbiter.applyControl(aircraft);
        System.out.println("case=" + scenario + " authority=" + authority + " hook=" + hookFired
                + " innerSwitch=" + innerSwitch + " pilotA=" + (aircraft.pilot == pilotA)
                + " pilotB=" + (aircraft.pilot == pilotB) + " pilotSame=" + (aircraft.pilot == pilotSame)
                + " writes=" + ReflectiveAircraft.writes + " setterPilots=" + ReflectiveAircraft.pilots
                + " events=" + events + " adapters=" + AutopilotLogManager.adapters);
        check(CombatWeaponManager.tickCalls == 0, "fake weapon unexpectedly ticked");
        if (scenario.equals("terrain") || scenario.equals("collision")) {
            check(!hookFired, "suppressed branch reached pending hook");
            if (scenario.equals("collision")) {
                check(authority == ControlAuthorityArbiter.Authority.COLLISION_AVOIDANCE,
                        "collision authority not observed");
                check(events.stream().noneMatch(x -> x.startsWith("offensive-pilot:")),
                        "collision suppression did not precede offensive read");
                check(AutopilotLogManager.adapters.stream().anyMatch(x -> x.contains("predicted_aircraft_collision_avoidance")),
                        "collision direct adapter missing");
            } else {
                check(authority == ControlAuthorityArbiter.Authority.TERRAIN_AVOIDANCE,
                        "terrain authority not observed");
                check(events.contains("energy-pilot:A") && events.contains("offensive-pilot:A"),
                        "terrain abstention getters not observed");
                check(AutopilotLogManager.adapters.stream().noneMatch(x -> x.contains(":combat_")),
                        "terrain allowed offensive adapter");
                check(ReflectiveAircraft.pilots.size() == 1, "unexpected pending terrain write");
            }
            return;
        }
        check(hookFired, "pending hook not reached");
        check(!ReflectiveAircraft.pilots.isEmpty() && ReflectiveAircraft.pilots.get(0) == pilotA, "base A missing");
        if (scenario.equals("fallback-outer-a-inner-b")) {
            check(innerSwitch && events.contains("offensive-pilot:B"), "outer A / inner B not observed");
        } else {
            check(events.contains("offensive-pilot:A"), "offensive pilot A not observed");
        }
        if (scenario.endsWith("-same")) {
            check(authority == (scenario.startsWith("alignment-")
                    ? ControlAuthorityArbiter.Authority.ENERGY_FIGHTER_REENGAGEMENT
                    : ControlAuthorityArbiter.Authority.OFFENSIVE_COMBAT), "proposal authority mismatch");
            check(ReflectiveAircraft.pilots.size() == 2 && ReflectiveAircraft.pilots.get(1) == pilotA,
                    "same A pending write expected");
        } else {
            if (scenario.equals("fallback-swap") || scenario.equals("alignment-swap")
                    || scenario.equals("fallback-same-uuid") || scenario.equals("fallback-outer-a-inner-b")) {
                Mob expected = scenario.equals("fallback-same-uuid") ? pilotSame : pilotB;
                check(aircraft.pilot == expected, "expected distinct mob absent");
                if (ReflectiveAircraft.pilots.size() > 1) {
                    check(ReflectiveAircraft.pilots.get(1) == expected, "pending setter received wrong pilot object");
                }
            }
            check(ReflectiveAircraft.pilots.size() == 1, "CONTRACT: no stale energy pending write after ownership change");
        }
    }
}
