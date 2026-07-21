package com.wwdebug.autopilot;

import com.wwdebug.benchmark.ReflectiveAircraft;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.util.Mth;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.Mob;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.level.ClipContext;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraft.world.phys.HitResult;
import net.minecraft.world.phys.Vec3;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Applies two cooperative-flight layers after the normal mission controller:
 * predicted aircraft separation for every autonomous fighter, and optional tagged formation slots.
 */
public final class FormationFlightManager {
    private static final String GROUP_PREFIX = "wwformation:group:";
    private static final String SLOT_PREFIX = "wwformation:slot:";
    private static final String LEADER_TAG = "wwformation:leader";
    private static final double SEARCH_HORIZONTAL = 110.0;
    private static final double SEARCH_VERTICAL = 48.0;
    private static final double HARD_CURRENT_SEPARATION = 9.0;
    private static final double HARD_PREDICTED_SEPARATION = 13.0;
    private static final double PREDICTION_TICKS = 60.0;
    private static final Set<UUID> ACTIVE_COLLISION = ConcurrentHashMap.newKeySet();
    private static final Set<UUID> ACTIVE_FORMATION = ConcurrentHashMap.newKeySet();
    private static final ConcurrentHashMap<UUID, Integer> STATUS_TICKS = new ConcurrentHashMap<>();

    private FormationFlightManager() {
    }

    public static void applyControl(Entity aircraft) {
        if (aircraft.level().isClientSide || !ReflectiveAircraft.isAirplane(aircraft)
                || !ReflectiveAircraft.isControllable(aircraft)
                || !(aircraft.level() instanceof ServerLevel level)) {
            clear(aircraft.getUUID());
            return;
        }
        Entity pilot = aircraft.getControllingPassenger();
        Optional<AutonomousFlightManager.SessionStatus> status =
                AutonomousFlightManager.status(aircraft.getUUID());
        if (pilot instanceof Player || !(pilot instanceof Mob) || status.isEmpty()) {
            clear(aircraft.getUUID());
            return;
        }
        FlightPhase phase = status.get().phase();
        if (!eligiblePhase(phase) || aircraft.onGround() || immediateTerrainAhead(aircraft)) {
            clearModes(level, aircraft, phase);
            return;
        }

        FlightSnapshot snapshot = FlightSnapshot.capture(aircraft);
        FlightProfile profile = AutopilotProfileRegistry.resolve(level.getServer(), aircraft)
                .orElse(null);
        if (profile == null) {
            clear(aircraft.getUUID());
            return;
        }

        List<Entity> nearby = nearbyAircraft(level, aircraft);
        Optional<CollisionThreat> collision = nearby.stream()
                .map(other -> collisionThreat(aircraft, other))
                .filter(CollisionThreat::dangerous)
                .min(Comparator.comparingDouble(CollisionThreat::urgency));
        if (collision.isPresent()) {
            applyCollisionAvoidance(level, aircraft, phase, snapshot, profile, collision.get());
            ACTIVE_FORMATION.remove(aircraft.getUUID());
            return;
        }
        if (ACTIVE_COLLISION.remove(aircraft.getUUID())) {
            AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                    "collision_avoidance_clear", "predicted_separation_restored", phase);
        }

        String group = formationGroup(aircraft);
        if (group == null) {
            clearFormation(level, aircraft, phase, "no_formation_group");
            return;
        }
        List<Entity> members = formationMembers(level, aircraft, group);
        if (members.size() < 2) {
            clearFormation(level, aircraft, phase, "formation_group_has_no_other_members");
            return;
        }
        Entity leader = selectLeader(members);
        if (leader == aircraft) {
            clearFormation(level, aircraft, phase, "formation_leader_uses_mission_control");
            return;
        }
        applyFormationSlot(level, aircraft, phase, snapshot, profile, leader, members);
    }

    private static void applyCollisionAvoidance(ServerLevel level, Entity aircraft, FlightPhase phase,
                                                FlightSnapshot snapshot, FlightProfile profile,
                                                CollisionThreat threat) {
        Entity other = threat.other();
        Vec3 away = horizontal(aircraft.position().subtract(other.position()));
        if (away.lengthSqr() < 1.0e-8) {
            Vec3 forward = snapshot.horizontalForward();
            Vec3 right = new Vec3(-forward.z, 0.0, forward.x);
            away = aircraft.getUUID().compareTo(other.getUUID()) <= 0 ? right : right.scale(-1.0);
        }
        away = away.normalize();
        Vec3 desired = horizontal(snapshot.horizontalForward().scale(0.45).add(away.scale(1.55)));
        if (desired.lengthSqr() < 1.0e-8) {
            desired = away;
        }
        desired = desired.normalize();

        boolean primary = aircraft.getUUID().compareTo(other.getUUID()) <= 0;
        double altitudeDelta = primary || snapshot.altitudeAboveGround() < 55.0 ? 14.0 : -10.0;
        double targetAltitude = snapshot.position().y + altitudeDelta;
        double targetSpeed = primary
                ? Math.max(profile.cruiseSpeedBps(), snapshot.speedBps() + 4.0)
                : Math.max(profile.stallGuardSpeedBps() * 1.35, snapshot.speedBps() - 3.0);
        FlightControlOutput output = control(snapshot, desired, targetAltitude, targetSpeed,
                profile, primary ? 1.0f : 0.28f,
                "predicted_aircraft_collision_avoidance", "collision_avoidance");
        ReflectiveAircraft.applyControl(aircraft, -output.x(), output.y(), output.z(), output.engineTarget());

        String reason = "other_uuid=" + other.getUUID()
                + ":current=" + round(threat.currentSeparation())
                + ":predicted=" + round(threat.predictedSeparation())
                + ":closest_ticks=" + round(threat.closestTicks())
                + ":vertical_split=" + round(altitudeDelta);
        if (ACTIVE_COLLISION.add(aircraft.getUUID())) {
            AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                    "collision_avoidance_start", reason, phase);
        }
        writeAdapter(level, aircraft, phase, snapshot, output, reason);
    }

    private static void applyFormationSlot(ServerLevel level, Entity aircraft, FlightPhase phase,
                                           FlightSnapshot snapshot, FlightProfile profile,
                                           Entity leader, List<Entity> members) {
        int slot = formationSlot(aircraft, members, leader);
        SlotOffset offset = slotOffset(slot);
        Vec3 leaderForward = horizontal(leader.getLookAngle());
        if (leaderForward.lengthSqr() < 1.0e-8) {
            leaderForward = horizontal(leader.getDeltaMovement());
        }
        if (leaderForward.lengthSqr() < 1.0e-8) {
            leaderForward = new Vec3(0.0, 0.0, 1.0);
        }
        leaderForward = leaderForward.normalize();
        Vec3 leaderRight = new Vec3(-leaderForward.z, 0.0, leaderForward.x).normalize();
        Vec3 desiredPosition = leader.position()
                .add(leaderRight.scale(offset.lateral()))
                .subtract(leaderForward.scale(offset.trailing()))
                .add(0.0, offset.vertical(), 0.0);
        Vec3 slotErrorVector = desiredPosition.subtract(aircraft.position());
        double slotError = slotErrorVector.length();
        double lateralError = slotErrorVector.dot(leaderRight);
        double alongTrackError = slotErrorVector.dot(leaderForward);
        double verticalError = slotErrorVector.y;

        // A fixed-wing aircraft must not point directly at a slot that lies behind it. Correct
        // lateral displacement with a bounded intercept angle and correct fore/aft displacement
        // with airspeed relative to the leader.
        double lateralIntercept = Mth.clamp(lateralError / 42.0, -0.55, 0.55);
        Vec3 desiredDirection = horizontal(
                leaderForward.add(leaderRight.scale(lateralIntercept)));
        if (desiredDirection.lengthSqr() < 1.0e-8) {
            desiredDirection = leaderForward;
        }
        desiredDirection = desiredDirection.normalize();

        double leaderSpeed = leader.getDeltaMovement().horizontalDistance() * 20.0;
        double speedCorrection = Mth.clamp(alongTrackError * 0.14, -8.0, 8.0);
        if (Math.abs(lateralError) > 32.0) {
            speedCorrection = Math.min(speedCorrection, 4.0);
        }
        double targetSpeed = Math.max(profile.stallGuardSpeedBps() * 1.35,
                leaderSpeed + speedCorrection);
        float engineTarget;
        double speedError = targetSpeed - snapshot.speedBps();
        if (speedError > 3.5) {
            engineTarget = 1.0f;
        } else if (speedError > 0.8) {
            engineTarget = 0.76f;
        } else if (speedError < -2.5) {
            engineTarget = 0.08f;
        } else if (speedError < -0.8) {
            engineTarget = 0.24f;
        } else {
            engineTarget = 0.42f;
        }

        FlightControlOutput output = control(snapshot, desiredDirection, desiredPosition.y,
                targetSpeed, profile, engineTarget,
                "formation_slot_tracking", "formation_tracking");
        ReflectiveAircraft.applyControl(aircraft, -output.x(), output.y(), output.z(), output.engineTarget());
        ACTIVE_FORMATION.add(aircraft.getUUID());

        int statusTicks = STATUS_TICKS.merge(aircraft.getUUID(), 1, Integer::sum);
        String reason = "leader_uuid=" + leader.getUUID()
                + ":slot=" + slot
                + ":slot_error=" + round(slotError)
                + ":lateral_error=" + round(lateralError)
                + ":along_error=" + round(alongTrackError)
                + ":vertical_error=" + round(verticalError)
                + ":desired_x=" + round(desiredPosition.x)
                + ":desired_y=" + round(desiredPosition.y)
                + ":desired_z=" + round(desiredPosition.z)
                + ":leader_speed=" + round(leaderSpeed)
                + ":target_speed=" + round(targetSpeed);
        if (statusTicks == 1 || statusTicks % 20 == 0) {
            AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                    "formation_slot_tracking", reason, phase);
        }
        writeAdapter(level, aircraft, phase, snapshot, output, reason);
    }

    private static FlightControlOutput control(FlightSnapshot snapshot, Vec3 desired,
                                               double targetAltitude, double targetSpeed,
                                               FlightProfile profile, float engineTarget,
                                               String reason, String override) {
        double desiredYaw = Math.toDegrees(Math.atan2(-desired.x, desired.z));
        double headingError = Mth.wrapDegrees((float) (desiredYaw - snapshot.yawDeg()));
        float x = (float) Mth.clamp(headingError / 40.0, -0.62, 0.62);
        double altitudeError = targetAltitude - snapshot.position().y;
        double desiredPitch = Mth.clamp(
                -altitudeError * 0.18 + snapshot.verticalSpeedBps() * 0.28,
                -9.0, 7.0);
        if (snapshot.speedBps() < profile.stallGuardSpeedBps() * 1.25) {
            desiredPitch = Math.max(desiredPitch, -3.5);
            x *= 0.60f;
            engineTarget = Math.max(engineTarget, 0.90f);
        }
        float z = (float) Mth.clamp((desiredPitch - snapshot.pitchDeg()) / 18.0,
                -0.72, 0.72);
        return new FlightControlOutput(
                x, 0.0f, z, engineTarget, desired, targetAltitude, targetSpeed,
                headingError, altitudeError, targetSpeed - snapshot.speedBps(),
                snapshot.speedBps() < profile.stallGuardSpeedBps(), false,
                reason, override);
    }

    private static void writeAdapter(ServerLevel level, Entity aircraft, FlightPhase phase,
                                     FlightSnapshot snapshot, FlightControlOutput applied,
                                     String reason) {
        float previousEngineTarget = Double.isFinite(snapshot.engineTarget())
                ? (float) snapshot.engineTarget() : 0.0f;
        FlightControlOutput baseline = new FlightControlOutput(
                0.0f, 0.0f, 0.0f, previousEngineTarget,
                snapshot.horizontalForward(), snapshot.position().y, snapshot.speedBps(),
                0.0, 0.0, 0.0, false, false,
                "mission_or_previous_adapter", "none");
        AutopilotLogManager.writeControlAdapter(level.getServer(), aircraft, phase,
                reason, snapshot, baseline, applied);
    }

    private static CollisionThreat collisionThreat(Entity aircraft, Entity other) {
        Vec3 relativePosition = other.position().subtract(aircraft.position());
        Vec3 relativeVelocity = other.getDeltaMovement().subtract(aircraft.getDeltaMovement());
        double velocitySquared = relativeVelocity.lengthSqr();
        double closestTicks = velocitySquared < 1.0e-8 ? 0.0
                : Mth.clamp(-relativePosition.dot(relativeVelocity) / velocitySquared,
                0.0, PREDICTION_TICKS);
        double current = relativePosition.length();
        double predicted = relativePosition.add(relativeVelocity.scale(closestTicks)).length();
        boolean dangerous = current < HARD_CURRENT_SEPARATION
                || (closestTicks > 0.0 && predicted < HARD_PREDICTED_SEPARATION);
        double urgency = Math.min(current, predicted) + closestTicks * 0.03;
        return new CollisionThreat(other, current, predicted, closestTicks, dangerous, urgency);
    }

    private static List<Entity> nearbyAircraft(ServerLevel level, Entity aircraft) {
        AABB area = aircraft.getBoundingBox().inflate(
                SEARCH_HORIZONTAL, SEARCH_VERTICAL, SEARCH_HORIZONTAL);
        return level.getEntities(aircraft, area,
                other -> !other.isRemoved() && ReflectiveAircraft.isAirplane(other));
    }

    private static List<Entity> formationMembers(ServerLevel level, Entity aircraft, String group) {
        List<Entity> members = new ArrayList<>();
        members.add(aircraft);
        AABB area = aircraft.getBoundingBox().inflate(256.0, 128.0, 256.0);
        members.addAll(level.getEntities(aircraft, area,
                other -> !other.isRemoved() && ReflectiveAircraft.isAirplane(other)
                        && group.equals(formationGroup(other))));
        members.sort(Comparator.comparing(Entity::getUUID));
        return members;
    }

    private static Entity selectLeader(List<Entity> members) {
        return members.stream().filter(entity -> entity.getTags().contains(LEADER_TAG))
                .min(Comparator.comparing(Entity::getUUID))
                .orElseGet(() -> members.stream().min(Comparator.comparing(Entity::getUUID)).orElseThrow());
    }

    private static int formationSlot(Entity aircraft, List<Entity> members, Entity leader) {
        for (String tag : aircraft.getTags()) {
            if (tag.startsWith(SLOT_PREFIX)) {
                try {
                    return Math.max(1, Integer.parseInt(tag.substring(SLOT_PREFIX.length())));
                } catch (NumberFormatException ignored) {
                }
            }
        }
        List<Entity> wingmen = members.stream().filter(entity -> entity != leader)
                .sorted(Comparator.comparing(Entity::getUUID)).toList();
        int index = wingmen.indexOf(aircraft);
        return index < 0 ? 1 : index + 1;
    }

    private static SlotOffset slotOffset(int slot) {
        int row = (slot - 1) / 2 + 1;
        boolean left = slot % 2 == 1;
        double lateral = (left ? -1.0 : 1.0) * 22.0 * row;
        double trailing = 26.0 * row;
        double vertical = -2.0 * row;
        return new SlotOffset(lateral, trailing, vertical);
    }

    private static String formationGroup(Entity aircraft) {
        return aircraft.getTags().stream().filter(tag -> tag.startsWith(GROUP_PREFIX))
                .map(tag -> tag.substring(GROUP_PREFIX.length()))
                .filter(value -> !value.isBlank())
                .sorted().findFirst().orElse(null);
    }

    private static boolean eligiblePhase(FlightPhase phase) {
        return phase.isAirborneMissionPhase() && !phase.isLandingPhase()
                && phase != FlightPhase.STALL_ENTRY && phase != FlightPhase.STALL_RECOVERY;
    }

    private static boolean immediateTerrainAhead(Entity aircraft) {
        Vec3 start = aircraft.getBoundingBox().getCenter();
        Vec3 forward = aircraft.getLookAngle().normalize();
        Vec3 end = start.add(forward.scale(48.0));
        BlockHitResult hit = aircraft.level().clip(new ClipContext(
                start, end, ClipContext.Block.COLLIDER, ClipContext.Fluid.NONE, aircraft));
        return hit.getType() != HitResult.Type.MISS;
    }

    private static Vec3 horizontal(Vec3 vector) {
        return new Vec3(vector.x, 0.0, vector.z);
    }

    private static double round(double value) {
        return Math.rint(value * 10.0) / 10.0;
    }

    private static void clearModes(ServerLevel level, Entity aircraft, FlightPhase phase) {
        if (ACTIVE_COLLISION.remove(aircraft.getUUID())) {
            AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                    "collision_avoidance_clear", "flight_phase_or_terrain_priority", phase);
        }
        clearFormation(level, aircraft, phase, "flight_phase_or_terrain_priority");
    }

    private static void clearFormation(ServerLevel level, Entity aircraft, FlightPhase phase,
                                       String reason) {
        if (ACTIVE_FORMATION.remove(aircraft.getUUID())) {
            AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                    "formation_tracking_clear", reason, phase);
        }
        STATUS_TICKS.remove(aircraft.getUUID());
    }

    public static void clear(UUID aircraftUuid) {
        ACTIVE_COLLISION.remove(aircraftUuid);
        ACTIVE_FORMATION.remove(aircraftUuid);
        STATUS_TICKS.remove(aircraftUuid);
    }

    private record CollisionThreat(Entity other, double currentSeparation,
                                   double predictedSeparation, double closestTicks,
                                   boolean dangerous, double urgency) {
    }

    private record SlotOffset(double lateral, double trailing, double vertical) {
    }
}
