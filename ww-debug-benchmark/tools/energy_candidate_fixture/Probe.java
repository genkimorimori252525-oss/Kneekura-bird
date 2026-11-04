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
    public static ServerLevel originalWorld, interimWorld;
    public static final RuntimeException sentinel = new RuntimeException("injected pilot getter sentinel");
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

    static boolean simpleEnergyStage() {
        return scenario.startsWith("climb-") || scenario.startsWith("pivot-") || scenario.startsWith("capture-");
    }

    static boolean wantsAlignment() {
        return scenario.startsWith("alignment-") || scenario.startsWith("empty-aim-alignment-");
    }

    @SuppressWarnings("unchecked")
    public static void onFakeLog(String type, Entity entity) {
        if (!scenario.startsWith("empty-aim-alignment-") || !type.equals("air_combat_action_transition")) return;
        try {
            check(AirCombatManeuverManager.currentAim(entity.getUUID(), attackerId).isPresent(), "reentry aim missing");
            var states = AirCombatManeuverManager.class.getDeclaredField("STATES");
            states.setAccessible(true);
            Object state = ((Map<UUID, Object>) states.get(null)).get(entity.getUUID());
            check(state != null, "reentry state missing");
            var action = state.getClass().getDeclaredField("action");
            action.setAccessible(true);
            action.set(state, AirCombatAction.NONE);
            events.add("FAKE_LOG_REENTRY:force_offensive_none_after_aim");
        } catch (ReflectiveOperationException e) {
            throw new IllegalStateException(e);
        }
    }

    public static void onUuid(Entity entity) { }

    public static void onLevel(Entity entity) {
        if (entity != target) return;
        if (stack("AirCombatManeuverManager", "evaluateWithPilot")) events.add("offensive-level");
        else if (stack("EnergyFighterApexYawAdapter", "applyControl")
                || stack("EnergyFighterApexYawAdapter", "evaluateWithPilot")) events.add("energy-level");
    }

    public static void onPilot(Entity entity) {
        if (entity != target) return;
        if (stack("AirCombatManeuverManager", "evaluateWithPilot")) {
            if (scenario.equals("throw-offensive-pilot")) {
                events.add("throw-offensive-pilot");
                throw sentinel;
            }
            if (scenario.startsWith("fallback-outer-a-inner-b") && !innerSwitch) {
                check(entity.pilot == pilotA, "inner switch expects A");
                innerSwitch = true;
                entity.pilot = pilotB;
            }
            events.add("offensive-pilot:" + (entity.pilot == pilotA ? "A" : entity.pilot == pilotB ? "B" : "other"));
        } else if (stack("EnergyFighterApexYawAdapter", "applyControl")) {
            if (scenario.equals("throw-energy-pilot")) {
                events.add("throw-energy-pilot");
                throw sentinel;
            }
            events.add("energy-pilot:" + (entity.pilot == pilotA ? "A" : "other"));
            if (scenario.equals("fallback-outer-level-inner-other-final-outer") && interimWorld == null) {
                interimWorld = new ServerLevel();
                interimWorld.entities.addAll(originalWorld.entities);
                entity.world = interimWorld;
                events.add("energy-level-switch:outer-to-inner");
            }
        }
    }

    public static void onRemovedGetter(Entity entity) {
        if (entity != target || hookFired || !stack("ControlAuthorityArbiter", "attemptPendingWrite")) return;
        check(events.contains("energy-pilot:A"), "energy pilot read not reached");
        boolean simpleStage = simpleEnergyStage();
        if (simpleStage) {
            check(events.stream().noneMatch(x -> x.startsWith("offensive-pilot:")), "climb unexpectedly read offensive");
            String stage = scenario.substring(0, scenario.indexOf('-'));
            check(AutopilotLogManager.adapters.stream().anyMatch(x -> x.contains("energy_coupled_" + stage)),
                    "simple energy proposal not observed: " + stage);
        } else {
            check(events.stream().anyMatch(x -> x.startsWith("offensive-pilot:")), "offensive pilot read not reached");
            check(AirCombatManeuverManager.currentAim(entity.getUUID(), attackerId).isPresent(), "offensive aim absent");
            if (scenario.startsWith("empty-aim-alignment-")) {
                check(events.contains("FAKE_LOG_REENTRY:force_offensive_none_after_aim"), "fake reentry absent");
                check(AutopilotLogManager.adapters.stream().noneMatch(x -> x.contains(":combat_")),
                        "inner proposal unexpectedly present");
                check(!AirCombatManeuverManager.active(entity), "inner NONE state not retained");
            } else {
                check(AutopilotLogManager.adapters.stream().anyMatch(x -> x.contains(":combat_")), "offensive proposal not observed");
            }
        }
        boolean alignment = AutopilotLogManager.adapters.stream().anyMatch(x -> x.contains("energy_coupled_final_alignment"));
        check(alignment == wantsAlignment(), "alignment branch not reached as requested");
        hookFired = true;
        events.add("pending-guard:alignment=" + alignment + ":prior-writes=" + ReflectiveAircraft.writes.size());
        switch (scenario) {
            case "fallback-same", "alignment-same", "empty-aim-alignment-same", "climb-same", "pivot-same", "capture-same",
                    "fallback-outer-a-inner-b" -> { }
            case "fallback-outer-a-inner-b-final-a" -> entity.pilot = pilotA;
            case "fallback-outer-level-inner-other-final-outer" -> {
                check(entity.world == interimWorld, "inner level not reached");
                entity.world = originalWorld;
            }
            case "fallback-swap", "alignment-swap", "empty-aim-alignment-swap", "climb-swap", "pivot-swap", "capture-swap" -> entity.pilot = pilotB;
            case "fallback-same-uuid" -> entity.pilot = pilotSame;
            case "fallback-level" -> entity.world = new ServerLevel();
            case "fallback-player" -> entity.pilot = new Player();
            case "fallback-empty" -> entity.pilot = null;
            case "fallback-client" -> entity.level().isClientSide = true;
            case "fallback-removed" -> entity.removed = true;
            default -> throw new AssertionError("unexpected guard hook scenario");
        }
    }

    @SuppressWarnings({"unchecked", "rawtypes"})
    static void seedEnergy(Entity aircraft, String stageName) throws Exception {
        Class<?> stateClass = Class.forName("com.wwdebug.autopilot.EnergyFighterApexYawAdapter$State");
        Constructor<?> ctor = stateClass.getDeclaredConstructors()[0];
        ctor.setAccessible(true);
        Object state = ctor.newInstance(attackerId, 100, 1.0, 100.0, 100.0, 0.0, 0.0, 0.0);
        Class<?> stageClass = Class.forName("com.wwdebug.autopilot.EnergyFighterApexYawAdapter$Stage");
        var stage = stateClass.getDeclaredField("stage");
        stage.setAccessible(true);
        stage.set(state, Enum.valueOf((Class<? extends Enum>) stageClass, stageName));
        var states = EnergyFighterApexYawAdapter.class.getDeclaredField("STATES");
        states.setAccessible(true);
        ((Map<UUID, Object>) states.get(null)).put(aircraft.getUUID(), state);
    }

    public static void main(String[] args) throws Exception {
        scenario = args[0];
        ServerLevel world = new ServerLevel();
        originalWorld = world;
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
        enemyAircraft.pos = new Vec3(wantsAlignment() ? 6.0
                : scenario.startsWith("capture-") ? 60.0 : 0.0, 100, 50);
        enemyPilot.world = world;
        enemyPilot.pos = enemyAircraft.pos;
        enemyPilot.vel = aircraft.vel;
        enemyPilot.vehicle = enemyAircraft;
        world.entities.add(aircraft);
        world.entities.add(enemyPilot);
        AutopilotValidationCheckpoint.ticks = 100;
        if (scenario.equals("terrain")) TerrainAvoidancePlanner.enabled = true;
        if (scenario.equals("collision")) enemyPilot.vel = new Vec3(0, 0, 0.75);
        if (scenario.equals("empty-claimed")) noGun = true;
        var authorityField = ControlAuthorityArbiter.class.getDeclaredField("LAST_AUTHORITY");
        authorityField.setAccessible(true);
        @SuppressWarnings("unchecked")
        Map<UUID, ControlAuthorityArbiter.Authority> markers =
                (Map<UUID, ControlAuthorityArbiter.Authority>) authorityField.get(null);
        UUID otherId = new UUID(0, 777);
        markers.put(aircraft.getUUID(), ControlAuthorityArbiter.Authority.BENCHMARK_CONTROL);
        markers.put(otherId, ControlAuthorityArbiter.Authority.FORMATION);
        seedEnergy(aircraft, simpleEnergyStage() ? scenario.substring(0, scenario.indexOf('-')).toUpperCase() : "DOCTRINE");
        ControlAuthorityArbiter.Authority authority;
        try {
            authority = ControlAuthorityArbiter.applyControl(aircraft);
            check(!scenario.startsWith("throw-"), "expected sentinel exception absent");
        } catch (RuntimeException caught) {
            if (!scenario.startsWith("throw-")) throw caught;
            check(caught == sentinel, "injected exception identity changed");
            check(events.contains(scenario), "expected getter exception site not reached");
            check(!hookFired && ReflectiveAircraft.pilots.size() == 1
                    && ReflectiveAircraft.pilots.get(0) == pilotA, "unexpected write before sentinel");
            check(markers.get(aircraft.getUUID()) == ControlAuthorityArbiter.Authority.BENCHMARK_CONTROL
                    && markers.get(otherId) == ControlAuthorityArbiter.Authority.FORMATION, "sentinel changed markers");
            System.out.println("case=" + scenario + " SENTINEL_EXCEPTION identity=true events=" + events
                    + " writes=" + ReflectiveAircraft.writes);
            return;
        }
        System.out.println("case=" + scenario + " authority=" + authority + " hook=" + hookFired
                + " innerSwitch=" + innerSwitch + " pilotA=" + (aircraft.pilot == pilotA)
                + " pilotB=" + (aircraft.pilot == pilotB) + " pilotSame=" + (aircraft.pilot == pilotSame)
                + " writes=" + ReflectiveAircraft.writes + " setterPilots=" + ReflectiveAircraft.pilots
                + " events=" + events + " adapters=" + AutopilotLogManager.adapters);
        check(CombatWeaponManager.tickCalls == 0, "fake weapon unexpectedly ticked");
        check(markers.get(otherId) == ControlAuthorityArbiter.Authority.FORMATION, "unrelated authority marker changed");
        if (scenario.equals("empty-claimed")) {
            check(!hookFired && authority == ControlAuthorityArbiter.Authority.ENERGY_FIGHTER_REENGAGEMENT,
                    "empty energy claim not retained");
            check(EnergyFighterApexYawAdapter.active(aircraft) && ReflectiveAircraft.pilots.size() == 1,
                    "claimed without proposal wrote input or lost energy state");
            check(markers.get(aircraft.getUUID()) == ControlAuthorityArbiter.Authority.ENERGY_FIGHTER_REENGAGEMENT,
                    "empty claim authority marker not retained");
            check(events.stream().filter(x -> x.startsWith("offensive-pilot:")).count() == 1,
                    "claimed tick reached lower offensive layer");
            return;
        }
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
        if (scenario.equals("fallback-outer-level-inner-other-final-outer")) {
            check(interimWorld != null && aircraft.world == originalWorld, "level transition not observed");
        }
        check(!ReflectiveAircraft.pilots.isEmpty() && ReflectiveAircraft.pilots.get(0) == pilotA, "base A missing");
        if (scenario.startsWith("fallback-outer-a-inner-b")) {
            check(innerSwitch && events.contains("offensive-pilot:B"), "outer A / inner B not observed");
        } else if (simpleEnergyStage()) {
            check(events.stream().noneMatch(x -> x.startsWith("offensive-pilot:")), "energy stage read offensive");
        } else {
            check(events.contains("offensive-pilot:A"), "offensive pilot A not observed");
        }
        if (scenario.endsWith("-same")) {
            check(authority == ((wantsAlignment() || simpleEnergyStage())
                    ? ControlAuthorityArbiter.Authority.ENERGY_FIGHTER_REENGAGEMENT
                    : ControlAuthorityArbiter.Authority.OFFENSIVE_COMBAT), "proposal authority mismatch");
            check(ReflectiveAircraft.pilots.size() == 2 && ReflectiveAircraft.pilots.get(1) == pilotA,
                    "same A pending write expected");
        } else {
            if (scenario.equals("fallback-swap") || scenario.equals("alignment-swap") || scenario.equals("empty-aim-alignment-swap")
                    || scenario.equals("climb-swap") || scenario.equals("pivot-swap") || scenario.equals("capture-swap")
                    || scenario.equals("fallback-same-uuid") || scenario.startsWith("fallback-outer-a-inner-b")) {
                Mob expected = scenario.equals("fallback-same-uuid") ? pilotSame
                        : scenario.endsWith("-final-a") ? pilotA : pilotB;
                check(aircraft.pilot == expected, "expected distinct mob absent");
                if (ReflectiveAircraft.pilots.size() > 1) {
                    check(ReflectiveAircraft.pilots.get(1) == expected, "pending setter received wrong pilot object");
                }
            }
            check(ReflectiveAircraft.pilots.size() == 1, "CONTRACT: no stale energy pending write after ownership change");
            check(markers.get(aircraft.getUUID()) == ControlAuthorityArbiter.Authority.BENCHMARK_CONTROL,
                    "rejected pending write changed marker");
        }
    }
}
