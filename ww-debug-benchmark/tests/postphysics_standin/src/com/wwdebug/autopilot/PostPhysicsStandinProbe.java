package com.wwdebug.autopilot;

import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.Mob;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.level.Level;
import net.minecraft.world.phys.Vec3;

import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

/** Direct invocation using a synthetic session and stand-in entity; no native game tick. */
public final class PostPhysicsStandinProbe {
    private static final UUID ID = UUID.fromString("00000000-0000-0000-0000-000000000c01");
    private PostPhysicsStandinProbe() { }

    public static void main(String[] args) throws Exception {
        String scenario = args[0];
        Entity aircraft = new Entity(ID, new Level(false));
        Mob mob = new Mob();
        aircraft.fixturePilot(mob);
        aircraft.fixtureGround(true);
        FlightPhase phase = scenario.equals("wrong-phase") ? FlightPhase.CRUISE_OUTBOUND : FlightPhase.BRAKE;
        Double lead = scenario.equals("mob-min") || scenario.equals("mob-max") ? 100.0 : null;
        double top = scenario.equals("mob-min") ? 10.0 : 40.0;
        if (!scenario.equals("no-session")) install(aircraft, new AutopilotSession(phase, new FlightProfile(lead, top)));
        check(MobPilotGate.isMobPiloted(aircraft), "actual mob gate must recognize the stand-in mob");

        boolean locked = scenario.endsWith("-locked");
        if (locked) {
            aircraft.fixtureVelocity(0.01, -0.02, 0.0);
            AutonomousFlightManager.applyPostPhysics(aircraft);
            check(aircraft.fixtureSetterCalls() == 1 && isLocked(), "mob must establish the actual manager lock");
        }
        aircraft.fixtureVelocity(0.2, -0.03, 0.0);
        aircraft.fixtureResetCalls();
        if (scenario.startsWith("player")) aircraft.fixturePilot(new Player());
        if (scenario.startsWith("empty")) aircraft.fixturePilot(null);
        if (scenario.startsWith("client")) aircraft.fixtureLevel(new Level(true));
        if (scenario.equals("airborne")) aircraft.fixtureGround(false);
        boolean expectedMob = !scenario.startsWith("player") && !scenario.startsWith("empty");
        check(MobPilotGate.isMobPiloted(aircraft) == expectedMob, "actual mob gate disagrees with fixture");
        Vec3 before = aircraft.getDeltaMovement();
        AutonomousFlightManager.applyPostPhysics(aircraft);
        if (scenario.startsWith("player") || scenario.startsWith("empty") || scenario.startsWith("client")
                || scenario.equals("airborne") || scenario.equals("wrong-phase") || scenario.equals("no-session")) {
            if (locked) check(isLocked(), "lock must remain present in this isolated direct call");
            check(aircraft.fixtureSetterCalls() == 0, "CONTRACT_FAIL automated setter invoked without eligible server mob");
            check(aircraft.getDeltaMovement().equals(before), "ineligible velocity changed");
        } else if (scenario.equals("mob-locked")) {
            check(isLocked() && aircraft.fixtureSetterCalls() == 1, "mob must retain existing lock");
            checkVelocity(aircraft, 0, -0.03, 0);
        } else {
            check(aircraft.fixtureSetterCalls() == 1, "eligible mob must receive brake setter");
            double expectedX = scenario.equals("mob-min") ? 0.195 : scenario.equals("mob-max") ? 0.19 : 0.1925;
            checkVelocity(aircraft, expectedX, -0.03, 0);
        }
        System.out.println("PASS " + scenario);
    }

    @SuppressWarnings("unchecked")
    private static void install(Entity aircraft, AutopilotSession session) throws Exception {
        Field sessions = AutonomousFlightManager.class.getDeclaredField("SESSIONS");
        sessions.setAccessible(true);
        Class<?> entryClass = Class.forName("com.wwdebug.autopilot.AutonomousFlightManager$SessionEntry");
        Constructor<?> ctor = entryClass.getDeclaredConstructors()[0];
        ctor.setAccessible(true);
        Object entry = ctor.newInstance(aircraft, session, null);
        ((Map<UUID, Object>) sessions.get(null)).put(ID, entry);
    }

    @SuppressWarnings("unchecked")
    private static boolean isLocked() throws Exception {
        Field locked = AutonomousFlightManager.class.getDeclaredField("POST_PHYSICS_BRAKE_LOCKED");
        locked.setAccessible(true);
        return ((Set<UUID>) locked.get(null)).contains(ID);
    }

    private static void checkVelocity(Entity aircraft, double x, double y, double z) {
        Vec3 v = aircraft.getDeltaMovement();
        check(Math.abs(v.x - x) < 1e-10 && Math.abs(v.y - y) < 1e-10 && Math.abs(v.z - z) < 1e-10,
                "unexpected brake velocity: " + v);
    }
    private static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }
}
