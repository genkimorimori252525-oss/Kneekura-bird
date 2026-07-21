package com.wwdebug.autopilot;

import com.wwdebug.benchmark.ReflectiveAircraft;
import com.wwdebug.benchmark.ReflectiveArmament;
import net.minecraft.network.chat.Component;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.entity.npc.Villager;
import net.minecraft.world.phys.Vec3;
import net.minecraftforge.registries.ForgeRegistries;

import java.lang.reflect.Field;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * GameTest-only scene with two real autonomous fighters using the same combat controller.
 * The primary A6M remains part of the normal validation mission; the opposing P-47N is discarded
 * after the combat window so the primary can return and park.
 */
final class MutualDogfightValidationManager {
    private static final String SCENARIO_PROPERTY = "wwdebug.flightGameTestScenario";
    private static final String SCENARIO = "dogfight_mutual";
    private static final String TEST_NAME_PREFIX = "AUTOPILOT TEST ";
    private static final String OPPONENT_TAG = "wwcombat:mutual_opponent";
    private static final String RED_FACTION = "wwcombat:faction:red";
    private static final String BLUE_FACTION = "wwcombat:faction:blue";
    private static final String HOSTILE_RED = "wwcombat:hostile:red";
    private static final String HOSTILE_BLUE = "wwcombat:hostile:blue";
    private static final int COMBAT_WINDOW_TICKS = 760;
    private static final int MISSING_ENTITY_GRACE_TICKS = 40;
    private static final Map<UUID, Scene> SCENES = new ConcurrentHashMap<>();

    private static final Field SESSIONS = field(AutonomousFlightManager.class, "SESSIONS");
    private static final Field ENTRY_SESSION = sessionEntryField("session");
    private static final Field PHASE = field(AutopilotSession.class, "phase");
    private static final Field PHASE_TICKS = field(AutopilotSession.class, "phaseTicks");
    private static final Field MISSION_TICKS = field(AutopilotSession.class, "missionTicks");
    private static final Field STABLE_TICKS = field(AutopilotSession.class, "stableTicks");
    private static final Field FALLING_TICKS = field(AutopilotSession.class, "fallingTicks");
    private static final Field PHASE_TARGET_YAW = field(AutopilotSession.class, "phaseTargetYaw");
    private static final Field PHASE_DIRECTION = field(AutopilotSession.class, "phaseDirection");
    private static final Field TRANSITION_REASON = field(AutopilotSession.class, "transitionReason");
    private static final Field LAST_OUTPUT = field(AutopilotSession.class, "lastOutput");

    private MutualDogfightValidationManager() {
    }

    static void tick(ServerLevel level, Entity aircraft, FlightPhase phase) {
        if (!SCENARIO.equals(System.getProperty(SCENARIO_PROPERTY, "").trim().toLowerCase())
                || aircraft.getTags().contains(OPPONENT_TAG)
                || !aircraft.getName().getString().startsWith(TEST_NAME_PREFIX)) {
            return;
        }
        Scene scene = SCENES.computeIfAbsent(aircraft.getUUID(), ignored -> new Scene());
        if (scene.completed) {
            return;
        }
        if (!scene.started) {
            if (phase != FlightPhase.CRUISE_OUTBOUND) {
                return;
            }
            start(level, aircraft, scene, phase);
            return;
        }

        Entity opponent = scene.opponent;
        if (opponent == null || opponent.isRemoved()) {
            Entity reloaded = scene.opponentUuid == null ? null : level.getEntity(scene.opponentUuid);
            if (reloaded != null && !reloaded.isRemoved()) {
                scene.opponent = reloaded;
                opponent = reloaded;
                scene.missingEntityTicks = 0;
            } else if (++scene.missingEntityTicks <= MISSING_ENTITY_GRACE_TICKS) {
                return;
            } else {
                completeScene(level, aircraft, scene, phase,
                        "opponent_missing_after_grace_period");
                return;
            }
        } else {
            scene.missingEntityTicks = 0;
        }

        scene.ageTicks++;
        if (CombatAwarenessManager.currentSolution(aircraft.getUUID())
                .map(solution -> solution.targetUuid().equals(scene.opponentPilotUuid))
                .orElse(false)) {
            scene.primaryTrackTicks++;
        }
        if (CombatAwarenessManager.currentSolution(opponent.getUUID())
                .map(solution -> solution.targetUuid().equals(scene.primaryPilotUuid))
                .orElse(false)) {
            scene.opponentTrackTicks++;
        }
        if (AirCombatManeuverManager.active(aircraft)) {
            scene.primaryCombatTicks++;
        }
        if (AirCombatManeuverManager.active(opponent)) {
            scene.opponentCombatTicks++;
        }

        double separation = aircraft.distanceTo(opponent);
        scene.minimumSeparation = Math.min(scene.minimumSeparation, separation);
        scene.maximumSeparation = Math.max(scene.maximumSeparation, separation);
        if (scene.ageTicks % 20 == 0) {
            AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                    "mutual_dogfight_validation_status",
                    "opponent_uuid=" + opponent.getUUID()
                            + ":age_ticks=" + scene.ageTicks
                            + ":separation=" + round(separation)
                            + ":primary_track_ticks=" + scene.primaryTrackTicks
                            + ":opponent_track_ticks=" + scene.opponentTrackTicks
                            + ":primary_combat_ticks=" + scene.primaryCombatTicks
                            + ":opponent_combat_ticks=" + scene.opponentCombatTicks
                            + ":opponent_phase=" + AutonomousFlightManager.status(opponent.getUUID())
                            .map(status -> status.phase().name()).orElse("NONE"),
                    phase);
        }
        if (scene.ageTicks >= COMBAT_WINDOW_TICKS) {
            completeScene(level, aircraft, scene, phase, "combat_window_complete");
        }
    }

    private static void start(ServerLevel level, Entity primary, Scene scene, FlightPhase phase) {
        Entity primaryPilot = primary.getControllingPassenger();
        if (primaryPilot == null || !ReflectiveArmament.equipTestMachineGun(primary, 48)) {
            scene.completed = true;
            AutopilotLogManager.writeEvent(level.getServer(), primary,
                    "mutual_dogfight_validation_setup_failed",
                    primaryPilot == null ? "primary_has_no_pilot" : "could_not_arm_primary",
                    phase);
            return;
        }
        applyFaction(primary, primaryPilot, RED_FACTION, HOSTILE_BLUE);

        EntityType<?> opponentType = ForgeRegistries.ENTITY_TYPES.getValue(
                new ResourceLocation("warfare_wings", "p47n"));
        Entity opponent = opponentType == null ? null : opponentType.create(level);
        if (opponent == null) {
            clearFaction(primary, RED_FACTION, HOSTILE_BLUE);
            scene.completed = true;
            AutopilotLogManager.writeEvent(level.getServer(), primary,
                    "mutual_dogfight_validation_setup_failed", "could_not_create_p47n", phase);
            return;
        }

        Vec3 forward = horizontal(primary.getLookAngle());
        if (forward.lengthSqr() < 1.0e-8) {
            forward = horizontal(primary.getDeltaMovement());
        }
        if (forward.lengthSqr() < 1.0e-8) {
            forward = new Vec3(0.0, 0.0, 1.0);
        }
        forward = forward.normalize();
        Vec3 right = new Vec3(-forward.z, 0.0, forward.x).normalize();
        Vec3 opponentPosition = primary.position().add(forward.scale(92.0))
                .add(right.scale(25.0)).add(0.0, 8.0, 0.0);
        Vec3 opponentDirection = primary.position().subtract(opponentPosition).normalize();

        opponent.setCustomName(Component.literal("AUTOPILOT TEST MUTUAL BLUE P47N"));
        opponent.setCustomNameVisible(true);
        opponent.setInvulnerable(true);
        opponent.addTag(OPPONENT_TAG);
        opponent.moveTo(opponentPosition.x, opponentPosition.y, opponentPosition.z,
                yaw(opponentDirection), 0.0f);
        level.addFreshEntity(opponent);

        Villager opponentPilot = EntityType.VILLAGER.create(level);
        if (opponentPilot == null) {
            opponent.discard();
            clearFaction(primary, RED_FACTION, HOSTILE_BLUE);
            scene.completed = true;
            AutopilotLogManager.writeEvent(level.getServer(), primary,
                    "mutual_dogfight_validation_setup_failed", "could_not_create_opponent_pilot", phase);
            return;
        }
        opponentPilot.setNoAi(true);
        opponentPilot.setSilent(true);
        opponentPilot.setInvulnerable(true);
        opponentPilot.setCustomName(Component.literal("MUTUAL BLUE PILOT"));
        opponentPilot.moveTo(opponentPosition.x, opponentPosition.y, opponentPosition.z,
                yaw(opponentDirection), 0.0f);
        level.addFreshEntity(opponentPilot);
        if (!opponentPilot.startRiding(opponent, true)) {
            opponentPilot.discard();
            opponent.discard();
            clearFaction(primary, RED_FACTION, HOSTILE_BLUE);
            scene.completed = true;
            AutopilotLogManager.writeEvent(level.getServer(), primary,
                    "mutual_dogfight_validation_setup_failed", "could_not_mount_opponent_pilot", phase);
            return;
        }
        applyFaction(opponent, opponentPilot, BLUE_FACTION, HOSTILE_RED);
        if (!ReflectiveArmament.equipTestMachineGun(opponent, 48)) {
            opponentPilot.discard();
            opponent.discard();
            clearFaction(primary, RED_FACTION, HOSTILE_BLUE);
            scene.completed = true;
            AutopilotLogManager.writeEvent(level.getServer(), primary,
                    "mutual_dogfight_validation_setup_failed", "could_not_arm_opponent", phase);
            return;
        }
        ReflectiveAircraft.fillFuel(opponent);
        ReflectiveAircraft.warmEngine(opponent, 0.90f);
        double opponentSpeed = AutopilotProfileRegistry.resolve(level.getServer(), opponent)
                .map(FlightProfile::cruiseSpeedBps).orElse(30.0);
        opponent.setDeltaMovement(opponentDirection.scale(opponentSpeed / 20.0));
        ReflectiveAircraft.applyControl(opponent, 0.0f, 0.0f, 0.0f, 0.90f);

        // Create the normal autonomous session, then seed only the disposable opponent into cruise.
        AutonomousFlightManager.applyControl(opponent);
        seedOpponentCruise(opponent, opponentDirection);

        scene.started = true;
        scene.primaryPilotUuid = primaryPilot.getUUID();
        scene.opponent = opponent;
        scene.opponentUuid = opponent.getUUID();
        scene.opponentPilotUuid = opponentPilot.getUUID();
        scene.minimumSeparation = primary.distanceTo(opponent);
        scene.maximumSeparation = scene.minimumSeparation;
        AutopilotLogManager.writeEvent(level.getServer(), primary,
                "mutual_dogfight_validation_started",
                "primary_uuid=" + primary.getUUID()
                        + ":primary_pilot_uuid=" + primaryPilot.getUUID()
                        + ":primary_faction=red"
                        + ":opponent_uuid=" + opponent.getUUID()
                        + ":opponent_pilot_uuid=" + opponentPilot.getUUID()
                        + ":opponent_faction=blue"
                        + ":initial_separation=" + round(primary.distanceTo(opponent))
                        + ":opponent_speed_bps=" + round(opponentSpeed),
                phase);
    }

    @SuppressWarnings("unchecked")
    private static void seedOpponentCruise(Entity opponent, Vec3 direction) {
        try {
            Map<UUID, Object> sessions = (Map<UUID, Object>) SESSIONS.get(null);
            Object entry = sessions.get(opponent.getUUID());
            if (entry == null) {
                throw new IllegalStateException("opponent autonomous session was not created");
            }
            Object session = ENTRY_SESSION.get(entry);
            PHASE.set(session, FlightPhase.CRUISE_OUTBOUND);
            PHASE_TICKS.setInt(session, 0);
            MISSION_TICKS.setInt(session, 9_000);
            STABLE_TICKS.setInt(session, 0);
            FALLING_TICKS.setInt(session, 0);
            PHASE_TARGET_YAW.setFloat(session, opponent.getYRot());
            PHASE_DIRECTION.set(session, direction);
            TRANSITION_REASON.set(session, "mutual_dogfight_opponent_seeded");
            LAST_OUTPUT.set(session, null);
        } catch (IllegalAccessException exception) {
            throw new IllegalStateException("Could not seed mutual-dogfight opponent", exception);
        }
    }

    private static void completeScene(ServerLevel level, Entity primary, Scene scene,
                                      FlightPhase phase, String reason) {
        Entity opponent = scene.opponent;
        if (opponent != null && !opponent.isRemoved()) {
            cleanupOpponent(opponent);
        } else if (scene.opponentUuid != null) {
            Entity loaded = level.getEntity(scene.opponentUuid);
            if (loaded != null && !loaded.isRemoved()) {
                cleanupOpponent(loaded);
            }
        }
        clearFaction(primary, RED_FACTION, HOSTILE_BLUE);
        finish(level, primary, scene, phase, reason);
    }

    private static void finish(ServerLevel level, Entity primary, Scene scene,
                               FlightPhase phase, String reason) {
        scene.completed = true;
        AutopilotLogManager.writeEvent(level.getServer(), primary,
                "mutual_dogfight_validation_completed",
                reason
                        + ":age_ticks=" + scene.ageTicks
                        + ":primary_track_ticks=" + scene.primaryTrackTicks
                        + ":opponent_track_ticks=" + scene.opponentTrackTicks
                        + ":primary_combat_ticks=" + scene.primaryCombatTicks
                        + ":opponent_combat_ticks=" + scene.opponentCombatTicks
                        + ":minimum_separation=" + round(scene.minimumSeparation)
                        + ":maximum_separation=" + round(scene.maximumSeparation),
                phase);
    }

    private static void cleanupOpponent(Entity opponent) {
        Entity pilot = opponent.getControllingPassenger();
        AutonomousFlightManager.forceStop(opponent.getUUID(), "mutual_dogfight_window_complete");
        if (pilot != null) {
            pilot.stopRiding();
            pilot.discard();
        }
        opponent.discard();
    }

    private static void applyFaction(Entity aircraft, Entity pilot,
                                     String factionTag, String hostileTag) {
        aircraft.addTag(factionTag);
        aircraft.addTag(hostileTag);
        pilot.addTag(factionTag);
        pilot.addTag(hostileTag);
    }

    private static void clearFaction(Entity aircraft, String factionTag, String hostileTag) {
        aircraft.removeTag(factionTag);
        aircraft.removeTag(hostileTag);
        Entity pilot = aircraft.getControllingPassenger();
        if (pilot != null) {
            pilot.removeTag(factionTag);
            pilot.removeTag(hostileTag);
        }
    }

    private static float yaw(Vec3 direction) {
        return (float) Math.toDegrees(Math.atan2(-direction.x, direction.z));
    }

    private static Vec3 horizontal(Vec3 vector) {
        return new Vec3(vector.x, 0.0, vector.z);
    }

    private static double round(double value) {
        return Math.rint(value * 100.0) / 100.0;
    }

    private static Field field(Class<?> owner, String name) {
        try {
            Field field = owner.getDeclaredField(name);
            field.setAccessible(true);
            return field;
        } catch (NoSuchFieldException exception) {
            throw new ExceptionInInitializerError(exception);
        }
    }

    private static Field sessionEntryField(String name) {
        try {
            Class<?> entry = Class.forName(
                    "com.wwdebug.autopilot.AutonomousFlightManager$SessionEntry");
            Field field = entry.getDeclaredField(name);
            field.setAccessible(true);
            return field;
        } catch (ClassNotFoundException | NoSuchFieldException exception) {
            throw new ExceptionInInitializerError(exception);
        }
    }

    static void clear(UUID aircraftUuid) {
        Scene scene = SCENES.remove(aircraftUuid);
        if (scene == null) {
            return;
        }
        Entity opponent = scene.opponent;
        if (opponent != null && !opponent.isRemoved()) {
            cleanupOpponent(opponent);
        }
    }

    private static final class Scene {
        private UUID primaryPilotUuid;
        private Entity opponent;
        private UUID opponentUuid;
        private UUID opponentPilotUuid;
        private int ageTicks;
        private int missingEntityTicks;
        private int primaryTrackTicks;
        private int opponentTrackTicks;
        private int primaryCombatTicks;
        private int opponentCombatTicks;
        private double minimumSeparation = Double.POSITIVE_INFINITY;
        private double maximumSeparation;
        private boolean started;
        private boolean completed;
    }
}
