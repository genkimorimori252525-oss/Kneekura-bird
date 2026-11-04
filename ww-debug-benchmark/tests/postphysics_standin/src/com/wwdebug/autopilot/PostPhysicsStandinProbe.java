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
        if (scenario.startsWith("stale-")) { stale(scenario); return; }
        if (scenario.startsWith("cross-")) { cross(scenario); return; }
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
            if (locked) check(isLocked() == scenario.startsWith("client"),
                    "server non-mob clears lock; client must not alter it");
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

    private static void cross(String scenario) throws Exception {
        Entity aircraft = new Entity(ID, new Level(false));
        aircraft.fixturePilot(new Mob());
        aircraft.fixtureGround(true);
        install(aircraft, new AutopilotSession(FlightPhase.BRAKE, new FlightProfile(null, 40.0)));
        boolean ineligible = scenario.equals("cross-player") || scenario.equals("cross-empty")
                || scenario.equals("cross-client");
        if (ineligible) {
            aircraft.fixtureVelocity(0.01, -0.02, 0);
            AutonomousFlightManager.applyPostPhysics(aircraft);
            check(isLocked(), "mob must establish the actual manager lock");
        }
        if (scenario.equals("cross-player")) aircraft.fixturePilot(new Player());
        if (scenario.equals("cross-empty")) aircraft.fixturePilot(null);
        if (scenario.equals("cross-client")) aircraft.fixtureLevel(new Level(true));
        double x = ineligible ? 0.03 : scenario.equals("cross-mob-crossover") ? 0.055 : 0.2;
        aircraft.fixtureVelocity(x, -0.03, 0);
        aircraft.fixtureResetCalls();
        AutonomousFlightManager.applyPostPhysics(aircraft);
        AutopilotWheelLockAdapter.apply(aircraft);
        if (ineligible) {
            check(isLocked() == scenario.equals("cross-client"),
                    "server non-mob clears lock; client must not alter it");
            check(aircraft.fixtureSetterCalls() == 0, "CONTRACT_FAIL combined setters invoked without eligible server mob");
            checkVelocity(aircraft, x, -0.03, 0);
        } else if (scenario.equals("cross-mob-crossover")) {
            check(aircraft.fixtureSetterCalls() == 2, "manager deceleration should enter wheel-lock threshold");
            checkVelocity(aircraft, 0, -0.03, 0);
        } else {
            check(aircraft.fixtureSetterCalls() == 1, "mob receives normal manager deceleration");
            checkVelocity(aircraft, 0.1925, -0.03, 0);
        }
        System.out.println("PASS " + scenario);
    }

    private static void stale(String scenario) throws Exception {
        Entity aircraft = new Entity(ID, new Level(false));
        aircraft.fixturePilot(new Mob());
        aircraft.fixtureGround(true);
        install(aircraft, new AutopilotSession(FlightPhase.BRAKE, new FlightProfile(null, 40.0)));
        aircraft.fixtureVelocity(0.01, -0.02, 0);
        AutonomousFlightManager.applyPostPhysics(aircraft);
        check(isLocked(), "mob must establish lock");
        if (scenario.equals("stale-force-stop-locked")) {
            AutonomousFlightManager.forceStop(ID, "synthetic_test");
            check(!isLocked() && AutonomousFlightManager.status(ID).isEmpty(), "forceStop must remove the live lock and session");
            aircraft.fixtureVelocity(0.2, -0.03, 0);
            aircraft.fixtureResetCalls();
            AutonomousFlightManager.applyPostPhysics(aircraft);
            AutopilotWheelLockAdapter.apply(aircraft);
            check(aircraft.fixtureSetterCalls() == 0, "stopped session must not write");
            checkVelocity(aircraft, 0.2, -0.03, 0);
            System.out.println("PASS " + scenario);
            return;
        }
        if (scenario.equals("stale-player") || scenario.equals("stale-client")) aircraft.fixturePilot(new Player());
        if (scenario.equals("stale-empty") || scenario.equals("stale-empty-airborne") || scenario.equals("stale-stop")) {
            aircraft.fixturePilot(null);
        }
        if (scenario.equals("stale-client")) aircraft.fixtureLevel(new Level(true));
        if (scenario.equals("stale-airborne") || scenario.equals("stale-empty-airborne")) aircraft.fixtureGround(false);
        aircraft.fixtureVelocity(0.2, -0.03, 0);
        aircraft.fixtureResetCalls();
        Object originalEntry = sessionEntry();
        AutonomousFlightManager.SessionStatus originalStatus = AutonomousFlightManager.status(ID).orElseThrow();
        AutonomousFlightManager.applyPostPhysics(aircraft);
        AutopilotWheelLockAdapter.apply(aircraft);
        check(sessionEntry() == originalEntry && AutonomousFlightManager.status(ID).orElseThrow().equals(originalStatus),
                "direct calls must preserve the session entry and visible status");
        check(aircraft.fixtureSetterCalls() == 0, "ineligible aircraft must not receive a setter");
        checkVelocity(aircraft, 0.2, -0.03, 0);
        check(AutonomousFlightManager.status(ID).isPresent(), "direct calls must not stop the session");
        boolean retainsLock = scenario.equals("stale-client") || scenario.equals("stale-airborne");
        boolean lockAfterIneligible = isLocked();
        if (scenario.equals("stale-stop")) {
            check(!lockAfterIneligible, "CONTRACT_FAIL server non-mob retained lock");
            AutonomousFlightManager.forceStop(ID, "synthetic_test");
            check(!isLocked() && AutonomousFlightManager.status(ID).isEmpty(), "forceStop must remove session and lock");
        }
        aircraft.fixtureLevel(new Level(false));
        aircraft.fixtureGround(true);
        aircraft.fixturePilot(new Mob());
        aircraft.fixtureVelocity(0.2, -0.03, 0);
        aircraft.fixtureResetCalls();
        AutonomousFlightManager.applyPostPhysics(aircraft);
        AutopilotWheelLockAdapter.apply(aircraft);
        if (scenario.equals("stale-stop")) {
            check(aircraft.fixtureSetterCalls() == 0, "no session must prevent a setter");
            checkVelocity(aircraft, 0.2, -0.03, 0);
        } else if (retainsLock) {
            check(lockAfterIneligible, "client or airborne mob must retain lock");
            check(isLocked() && aircraft.fixtureSetterCalls() == 2, "unchanged lock must remain effective");
            checkVelocity(aircraft, 0, -0.03, 0);
        } else {
            checkVelocity(aircraft, 0.1925, -0.03, 0);
            check(!lockAfterIneligible && !isLocked() && aircraft.fixtureSetterCalls() == 1, "CONTRACT_FAIL stale lock remains on mob return");
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
    private static Object sessionEntry() throws Exception {
        Field sessions = AutonomousFlightManager.class.getDeclaredField("SESSIONS");
        sessions.setAccessible(true);
        return ((Map<UUID, Object>) sessions.get(null)).get(ID);
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
