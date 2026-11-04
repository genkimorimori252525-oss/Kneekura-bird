package com.wwdebug.autopilot;

import com.mojang.authlib.GameProfile;
import com.wwdebug.benchmark.ReflectiveAircraft;
import net.minecraft.core.BlockPos;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.gametest.framework.GameTest;
import net.minecraft.gametest.framework.GameTestHelper;
import net.minecraft.gametest.framework.GameTestRegistry;
import net.minecraft.gametest.framework.GameTestServer;
import net.minecraft.network.chat.Component;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.entity.npc.Villager;
import net.minecraft.world.phys.Vec3;
import net.minecraftforge.common.util.FakePlayer;
import net.minecraftforge.gametest.GameTestHolder;
import net.minecraftforge.gametest.PrefixGameTestTemplate;

import java.lang.reflect.Field;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

/**
 * Isolated GameTest fixture, not a normal flight or network-player test. The caller must prove
 * the world and JVM are disposable; the system property below is only an attestation. The test
 * seeds BRAKE and onGround directly and calls each writer synchronously without a native tick.
 * Never include this test-only source in the production artifact.
 */
@GameTestHolder("wwdebug_brake_probe")
@PrefixGameTestTemplate(false)
public final class BrakePilotOwnershipProbe {
    private static final String NAMESPACE = "wwdebug_brake_probe";
    private static final String BATCH = "brake_pilot_ownership_probe_only";
    private static final String ATTESTATION = "fresh-disposable-world-single-jvm";

    private BrakePilotOwnershipProbe() { }

    @GameTest(template = "empty", timeoutTicks = 40, batch = BATCH)
    public static void staleBrakePreservesPilotAuthority(GameTestHelper helper) throws Exception {
        ServerLevel level = helper.getLevel();
        check(level.getServer() instanceof GameTestServer, "requires a GameTestServer");
        check(level.getServer().isSameThread(), "requires the server thread");
        check(ATTESTATION.equals(System.getProperty("wwdebug.brakeProbeIsolation")),
                "requires independently verified disposable-world and single-JVM isolation");
        check(NAMESPACE.equals(System.getProperty("forge.enabledGameTestNamespaces")),
                "requires the dedicated namespace alone");
        var tests = GameTestRegistry.getAllTestFunctions();
        check(tests.size() == 1, "requires exactly one registered GameTest");
        var selected = tests.iterator().next();
        check("stalebrakepreservespilotauthority".equals(selected.getTestName())
                        && BATCH.equals(selected.getBatchName())
                        && (NAMESPACE + ":empty").equals(selected.getStructureName()),
                "unexpected test, batch or structure registration");

        EntityType<?> type = BuiltInRegistries.ENTITY_TYPE
                .getOptional(new ResourceLocation("warfare_wings", "a6m"))
                .orElseThrow(() -> new IllegalStateException("fixed Warfare Wings A6M is required"));
        Entity aircraft = type.create(level);
        Villager mob = EntityType.VILLAGER.create(level);
        check(aircraft != null && mob != null, "could not create fixture aircraft and pilot");
        FakePlayer player = new FakePlayer(level, new GameProfile(UUID.randomUUID(), "WWBrakeProbe"));
        UUID id = aircraft.getUUID();
        List<String> failures = new ArrayList<>();
        Object[] ownedEntry = {null};
        boolean[] added = {false, false};
        long cleanupTick = level.getGameTime();
        Throwable setupFailure = null;
        try {
            check(AutonomousFlightManager.status(id).isEmpty(), "fixture UUID already has a session");
            check(!id.equals(mob.getUUID()) && !id.equals(player.getUUID())
                            && !mob.getUUID().equals(player.getUUID()), "fixture UUIDs are not unique");
            check(level.getEntity(id) == null && level.getEntity(mob.getUUID()) == null
                            && level.getEntity(player.getUUID()) == null,
                    "a fixture UUID already identifies a world entity");
            check(!brakeLocks().contains(id) && !managerSet("POST_PHYSICS_BRAKE_LOGGED").contains(id)
                            && !managerSet("MISSING_PROFILE_WARNINGS").contains(id)
                            && !((Map<?, ?>) staticField("FLARE_EXTENSIONS")).containsKey(id)
                            && !checkpointEntries().contains(id),
                    "fixture UUID already has autonomous state");
            Vec3 origin = Vec3.atBottomCenterOf(helper.absolutePos(new BlockPos(1, 2, 1)));
            aircraft.setCustomName(Component.literal("BRAKE OWNERSHIP PROBE"));
            aircraft.moveTo(origin.x, origin.y, origin.z, 0.0f, 0.0f);
            mob.moveTo(origin.x, origin.y, origin.z, 0.0f, 0.0f);
            player.moveTo(origin.x, origin.y, origin.z, 0.0f, 0.0f);
            mob.setNoAi(true);
            added[0] = level.addFreshEntity(aircraft);
            check(added[0], "could not add the fixture aircraft");
            added[1] = level.addFreshEntity(mob);
            check(added[1], "could not add the fixture mob");
            check(ReflectiveAircraft.isAirplane(aircraft) && ReflectiveAircraft.isControllable(aircraft),
                    "fixture must be the real controllable aircraft");
            check(AutopilotProfileRegistry.resolve(level.getServer(), aircraft).isPresent(),
                    "fixture requires the measured A6M profile");
            check(mob.startRiding(aircraft, true) && aircraft.getControllingPassenger() == mob
                            && MobPilotGate.isMobPiloted(aircraft),
                    "fixture mob must hold the controls");
            aircraft.setOnGround(true);
            AutonomousFlightManager.applyControl(aircraft);
            Object entry = sessionEntries().get(id);
            check(entry != null && field(entry, "aircraft") == aircraft,
                    "fixture must own the exact autonomous session");
            ownedEntry[0] = entry;
            Object session = field(entry, "session");
            Field phase = session.getClass().getDeclaredField("phase");
            phase.setAccessible(true);
            phase.set(session, FlightPhase.BRAKE);
            long tick = level.getGameTime();
            verifyContext(level, aircraft, mob, player, entry, tick, mob, "mob positive control");

            Vec3 moving = new Vec3(0.4, -0.03, 0.1); // More than 1 bps; does not enter the lock.
            Vec3 slow = new Vec3(0.03, -0.03, 0.01); // Between 0.5 and 1.0 bps.
            positiveBrake(aircraft, moving, failures);
            verifyContext(level, aircraft, mob, player, entry, tick, mob, "mob wheel-lock control");
            positiveWheelLock(aircraft, slow, failures);

            verifyContext(level, aircraft, mob, player, entry, tick, mob, "before mob dismount");
            mob.stopRiding();
            verifyContext(level, aircraft, mob, player, entry, tick, null, "empty seat");
            unchanged(aircraft, moving, true, "empty seat post-physics", failures);
            verifyContext(level, aircraft, mob, player, entry, tick, null, "empty seat wheel-lock control");
            unchanged(aircraft, slow, false, "empty seat wheel lock", failures);

            check(player.getVehicle() == null && player.getPassengers().isEmpty(),
                    "fake player has an unknown vehicle or passenger");
            check(player.startRiding(aircraft, true), "fake player could not mount fixture");
            verifyContext(level, aircraft, mob, player, entry, tick, player, "player takeover");
            unchanged(aircraft, moving, true, "player post-physics", failures);
            verifyContext(level, aircraft, mob, player, entry, tick, player, "player wheel-lock control");
            unchanged(aircraft, slow, false, "player wheel lock", failures);

            verifyContext(level, aircraft, mob, player, entry, tick, player, "before player dismount");
            player.stopRiding();
            check(player.getVehicle() == null && aircraft.getPassengers().isEmpty()
                            && mob.getVehicle() == null && mob.getPassengers().isEmpty(),
                    "fixture mob has an unknown vehicle or passenger");
            check(mob.startRiding(aircraft, true), "fixture mob could not resume controls");
            verifyContext(level, aircraft, mob, player, entry, tick, mob, "lock positive control");
            aircraft.setDeltaMovement(new Vec3(0.02, -0.03, 0.0));
            AutonomousFlightManager.applyPostPhysics(aircraft);
            check(brakeLocks().contains(id), "mob control must establish the test brake lock");
            check(aircraft.getDeltaMovement().horizontalDistance() == 0.0,
                    "mob control must apply the established lock");

            verifyContext(level, aircraft, mob, player, entry, tick, mob, "before lock-state mob dismount");
            mob.stopRiding();
            verifyContext(level, aircraft, mob, player, entry, tick, null, "empty seat after lock");
            unchanged(aircraft, moving, true, "empty seat retained lock", failures);
            check(player.getVehicle() == null && player.getPassengers().isEmpty(),
                    "fake player has an unknown vehicle or passenger before remount");
            check(player.startRiding(aircraft, true), "fake player could not remount fixture");
            verifyContext(level, aircraft, mob, player, entry, tick, player, "player after lock");
            unchanged(aircraft, moving, true, "player retained lock", failures);
        } catch (Throwable failure) {
            setupFailure = failure;
        } finally {
            cleanupOwned(level, aircraft, mob, player, ownedEntry[0], added, cleanupTick, failures);
        }
        if (setupFailure != null) {
            throw new IllegalStateException("fixture precondition or cleanup failed: " + failures, setupFailure);
        }
        check(failures.isEmpty(), "brake pilot authority violations: " + failures);
        helper.succeed();
    }

    private static void verifyContext(ServerLevel level, Entity aircraft, Villager mob, FakePlayer player,
                                      Object entry, long tick, Entity pilot, String label) throws Exception {
        check(level.getServer().isSameThread() && level.getServer().getLevel(level.dimension()) == level
                        && level.getGameTime() == tick, label + ": wrong server thread, world or tick");
        check(aircraft.level() == level && !aircraft.isRemoved()
                        && level.getEntity(aircraft.getUUID()) == aircraft && aircraft.onGround(),
                label + ": aircraft registration, world or ground flag changed");
        check(mob.level() == level && !mob.isRemoved() && level.getEntity(mob.getUUID()) == mob
                        && player.level() == level && !player.isRemoved()
                        && level.getEntity(player.getUUID()) == null,
                label + ": fixture pilot registration or world changed");
        check(aircraft.getControllingPassenger() == pilot, label + ": wrong controlling passenger");
        check(pilot == null || pilot.level() == level && !pilot.isRemoved()
                        && (pilot instanceof Villager && level.getEntity(pilot.getUUID()) == pilot
                        || pilot instanceof FakePlayer && level.getEntity(pilot.getUUID()) == null),
                label + ": pilot registration or world changed");
        check(aircraft.getVehicle() == null && (pilot == null ? aircraft.getPassengers().isEmpty()
                        : aircraft.getPassengers().size() == 1 && aircraft.getPassengers().get(0) == pilot
                        && pilot.getVehicle() == aircraft && pilot.getPassengers().isEmpty()),
                label + ": unexpected passenger or vehicle");
        check(mob.getVehicle() == (pilot == mob ? aircraft : null)
                        && player.getVehicle() == (pilot == player ? aircraft : null)
                        && mob.getPassengers().isEmpty() && player.getPassengers().isEmpty(),
                label + ": fixture pilot has an unexpected vehicle or passenger");
        check(MobPilotGate.isMobPiloted(aircraft) == (pilot instanceof Villager)
                        && MobPilotGate.isPlayerControlled(aircraft) == (pilot instanceof FakePlayer),
                label + ": pilot gate does not match the fixture occupant");
        check(sessionEntries().get(aircraft.getUUID()) == entry && field(entry, "aircraft") == aircraft,
                label + ": session or aircraft identity changed");
        check(AutonomousFlightManager.status(aircraft.getUUID())
                        .map(status -> status.phase() == FlightPhase.BRAKE).orElse(false),
                label + ": stale BRAKE session is missing");
    }

    private static void positiveBrake(Entity aircraft, Vec3 sentinel, List<String> failures) {
        aircraft.setDeltaMovement(sentinel);
        check(close(aircraft.getDeltaMovement(), sentinel), "post-physics sentinel was not established");
        AutonomousFlightManager.applyPostPhysics(aircraft);
        if (!(aircraft.getDeltaMovement().horizontalDistance() < sentinel.horizontalDistance())) {
            failures.add("mob post-physics positive control did not slow aircraft");
        }
    }

    private static void positiveWheelLock(Entity aircraft, Vec3 sentinel, List<String> failures) {
        aircraft.setDeltaMovement(sentinel);
        check(close(aircraft.getDeltaMovement(), sentinel), "wheel-lock sentinel was not established");
        AutopilotWheelLockAdapter.apply(aircraft);
        if (aircraft.getDeltaMovement().horizontalDistance() != 0.0) {
            failures.add("mob wheel-lock positive control did not stop aircraft");
        }
    }

    private static void unchanged(Entity aircraft, Vec3 sentinel, boolean postPhysics,
                                  String label, List<String> failures) {
        aircraft.setDeltaMovement(sentinel);
        check(close(aircraft.getDeltaMovement(), sentinel), label + ": sentinel was not established");
        if (postPhysics) AutonomousFlightManager.applyPostPhysics(aircraft);
        else AutopilotWheelLockAdapter.apply(aircraft);
        if (!close(aircraft.getDeltaMovement(), sentinel)) {
            failures.add(label + ": velocity changed from " + sentinel + " to " + aircraft.getDeltaMovement());
        }
    }

    private static boolean close(Vec3 first, Vec3 second) {
        return first.distanceToSqr(second) < 1.0e-18;
    }

    /** Stop on the first uncertain observation or operation; never retry an unknown outcome. */
    private static void cleanupOwned(ServerLevel level, Entity aircraft, Villager mob, FakePlayer player,
                                     Object ownedEntry, boolean[] added, long tick, List<String> failures) {
        try {
            check(added[0] && added[1] && ownedEntry != null,
                    "partial fixture creation or session ownership is unknown");
            CleanupSnapshot before = snapshot(level, aircraft, mob, player, tick, false, false);
            check(before.entry() == ownedEntry && before.entryAircraft() == aircraft,
                    "session identity is missing or changed; preserve all fixture entities");

            if (before.playerVehicle() == aircraft) {
                player.stopRiding();
                CleanupSnapshot after = snapshot(level, aircraft, mob, player, tick, false, false);
                check(sameExcept(before, after, mob, player, "player"),
                        "unexpected change after player dismount");
                before = after;
            }

            // The server-thread check and identity snapshots are not an atomic lease. External
            // mutation must be excluded independently before running this disposable probe.
            AutonomousFlightManager.forceStop(aircraft.getUUID(), "brake_probe_cleanup");
            CleanupSnapshot afterStop = snapshot(level, aircraft, mob, player, tick, false, false);
            check(sameExcept(before, afterStop, mob, player, "session"),
                    "session stop was incomplete or another observed state changed");
            before = afterStop;

            if (before.mobVehicle() == aircraft) {
                mob.stopRiding();
                CleanupSnapshot after = snapshot(level, aircraft, mob, player, tick, false, false);
                check(sameExcept(before, after, mob, player, "mob"),
                        "unexpected change after mob dismount");
                before = after;
            }
            check(before.passengers().isEmpty(), "fixture aircraft still has passengers");

            mob.discard();
            CleanupSnapshot afterMob = snapshot(level, aircraft, mob, player, tick, true, false);
            check(sameExcept(before, afterMob, mob, player, "discard_mob"),
                    "unexpected change after mob discard");
            aircraft.discard();
            CleanupSnapshot afterAircraft = snapshot(level, aircraft, mob, player, tick, true, true);
            check(sameExcept(afterMob, afterAircraft, mob, player, "discard_aircraft"),
                    "unexpected change after aircraft discard");
        } catch (Throwable failure) {
            failures.add("fixture cleanup aborted; preserve remaining state: " + failure);
        }
    }

    private record CleanupSnapshot(Object entry, Object entryAircraft, List<Entity> passengers,
                                   Entity playerVehicle, Entity mobVehicle, boolean locked,
                                   boolean logged, boolean warned, boolean checkpoint, Object flare,
                                   boolean mobRemoved, boolean aircraftRemoved) { }

    private static CleanupSnapshot snapshot(ServerLevel level, Entity aircraft, Villager mob,
                                            FakePlayer player, long tick, boolean mobRemoved,
                                            boolean aircraftRemoved) throws ReflectiveOperationException {
        check(level.getServer().isSameThread() && level.getServer().getLevel(level.dimension()) == level
                        && level.getGameTime() == tick, "server, world, thread or tick changed");
        check(aircraft.level() == level && mob.level() == level && player.level() == level,
                "fixture entity world changed");
        Entity registeredAircraft = level.getEntity(aircraft.getUUID());
        Entity registeredMob = level.getEntity(mob.getUUID());
        check(aircraft.isRemoved() == aircraftRemoved && mob.isRemoved() == mobRemoved && !player.isRemoved(),
                "fixture removal state changed");
        check((registeredAircraft == aircraft || aircraftRemoved && registeredAircraft == null)
                        && (registeredMob == mob || mobRemoved && registeredMob == null)
                        && level.getEntity(player.getUUID()) == null,
                "fixture registry identity changed");
        check(aircraft.getVehicle() == null && mob.getPassengers().isEmpty()
                        && player.getPassengers().isEmpty(), "unexpected vehicle or child passenger");
        List<Entity> passengers = List.copyOf(aircraft.getPassengers());
        check(passengers.stream().allMatch(p -> p == mob || p == player)
                        && passengers.size() == (containsIdentity(passengers, mob) ? 1 : 0)
                        + (containsIdentity(passengers, player) ? 1 : 0),
                "unidentified aircraft passenger");
        check((mob.getVehicle() == null || mob.getVehicle() == aircraft)
                        && (player.getVehicle() == null || player.getVehicle() == aircraft),
                "fixture pilot entered an unexpected vehicle");
        check(containsIdentity(passengers, mob) == (mob.getVehicle() == aircraft)
                        && containsIdentity(passengers, player) == (player.getVehicle() == aircraft),
                "passenger and vehicle observations disagree");
        Object entry = sessionEntries().get(aircraft.getUUID());
        Object entryAircraft = entry == null ? null : field(entry, "aircraft");
        return new CleanupSnapshot(entry, entryAircraft, passengers, player.getVehicle(), mob.getVehicle(),
                brakeLocks().contains(aircraft.getUUID()), managerSet("POST_PHYSICS_BRAKE_LOGGED").contains(aircraft.getUUID()),
                managerSet("MISSING_PROFILE_WARNINGS").contains(aircraft.getUUID()),
                checkpointEntries().contains(aircraft.getUUID()),
                ((Map<?, ?>) staticField("FLARE_EXTENSIONS")).get(aircraft.getUUID()), mobRemoved, aircraftRemoved);
    }

    private static boolean sameExcept(CleanupSnapshot before, CleanupSnapshot after, Entity mob,
                                      Entity player, String action) {
        boolean session = "session".equals(action);
        boolean dismountPlayer = "player".equals(action);
        boolean dismountMob = "mob".equals(action);
        boolean sameEntry = session ? after.entry() == null && after.entryAircraft() == null
                : after.entry() == before.entry() && after.entryAircraft() == before.entryAircraft();
        boolean sameAux = session ? !after.locked() && !after.logged() && !after.warned()
                && !after.checkpoint() && after.flare() == null
                : after.locked() == before.locked() && after.logged() == before.logged()
                && after.warned() == before.warned() && after.checkpoint() == before.checkpoint()
                && java.util.Objects.equals(after.flare(), before.flare());
        Entity removed = dismountPlayer ? player : dismountMob ? mob : null;
        List<Entity> expected = before.passengers().stream().filter(p -> p != removed).toList();
        return sameEntry && sameAux && sameIdentities(expected, after.passengers())
                && after.playerVehicle() == (dismountPlayer ? null : before.playerVehicle())
                && after.mobVehicle() == (dismountMob ? null : before.mobVehicle())
                && after.mobRemoved() == ("discard_mob".equals(action) || before.mobRemoved())
                && after.aircraftRemoved() == ("discard_aircraft".equals(action) || before.aircraftRemoved());
    }

    private static boolean containsIdentity(List<Entity> values, Entity wanted) {
        return values.stream().anyMatch(value -> value == wanted);
    }

    private static boolean sameIdentities(List<Entity> first, List<Entity> second) {
        if (first.size() != second.size()) return false;
        for (int i = 0; i < first.size(); i++) if (first.get(i) != second.get(i)) return false;
        return true;
    }

    private static Map<?, ?> sessionEntries() {
        return (Map<?, ?>) staticField("SESSIONS");
    }

    @SuppressWarnings("unchecked")
    private static Set<UUID> brakeLocks() {
        return (Set<UUID>) staticField("POST_PHYSICS_BRAKE_LOCKED");
    }

    private static Set<?> managerSet(String name) {
        return (Set<?>) staticField(name);
    }

    private static Set<?> checkpointEntries() {
        try {
            Field field = AutopilotValidationCheckpoint.class.getDeclaredField("APPLIED");
            field.setAccessible(true);
            return (Set<?>) field.get(null);
        } catch (ReflectiveOperationException exception) {
            throw new IllegalStateException("cannot inspect checkpoint ownership", exception);
        }
    }

    private static Object staticField(String name) {
        try {
            Field field = AutonomousFlightManager.class.getDeclaredField(name);
            field.setAccessible(true);
            return field.get(null);
        } catch (ReflectiveOperationException exception) {
            throw new IllegalStateException("cannot inspect " + name, exception);
        }
    }

    private static Object field(Object owner, String name) throws ReflectiveOperationException {
        Field field = owner.getClass().getDeclaredField(name);
        field.setAccessible(true);
        return field.get(owner);
    }

    private static void check(boolean condition, String message) {
        if (!condition) throw new IllegalStateException(message);
    }
}
