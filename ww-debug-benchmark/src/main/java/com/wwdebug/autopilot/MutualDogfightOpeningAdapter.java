package com.wwdebug.autopilot;

import com.wwdebug.benchmark.ReflectiveAircraft;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.Vec3;

import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * GameTest-only doctrine-neutral opening for the reciprocal fighter qualification.
 *
 * <p>Neither aircraft starts behind the other. The A6M begins about twenty degrees off the P-47N,
 * while the energy fighter receives a modest altitude and speed advantage and starts roughly six
 * degrees off its crossing solution. Six degrees remains outside the three-degree fixed-gun cone,
 * but the longer aircraft-awareness range gives the P-47N time to solve the first energy pass
 * before collision avoidance necessarily takes priority.</p>
 */
final class MutualDogfightOpeningAdapter {
    private static final String SCENARIO_PROPERTY = "wwdebug.flightGameTestScenario";
    private static final String SCENARIO = "dogfight_mutual";
    private static final String TEST_NAME_PREFIX = "AUTOPILOT TEST ";
    private static final String OPPONENT_TAG = "wwcombat:mutual_opponent";
    private static final double ENERGY_FIGHTER_OFF_NOSE_DEG = 6.0;
    private static final Set<UUID> APPLIED = ConcurrentHashMap.newKeySet();

    private MutualDogfightOpeningAdapter() {
    }

    static void apply(ServerLevel level, Entity primary, FlightPhase phase) {
        if (!SCENARIO.equals(System.getProperty(SCENARIO_PROPERTY, "").trim().toLowerCase())
                || primary.getTags().contains(OPPONENT_TAG)
                || !primary.getName().getString().startsWith(TEST_NAME_PREFIX)
                || APPLIED.contains(primary.getUUID())) {
            return;
        }

        AABB search = primary.getBoundingBox().inflate(320.0, 144.0, 320.0);
        Entity opponent = level.getEntities(primary, search,
                        entity -> !entity.isRemoved()
                                && entity.getTags().contains(OPPONENT_TAG)
                                && ReflectiveAircraft.isAirplane(entity))
                .stream().findFirst().orElse(null);
        if (opponent == null) {
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
        Vec3 opponentPosition = primary.position()
                .add(forward.scale(225.0))
                .add(right.scale(82.0))
                .add(0.0, 28.0, 0.0);
        Vec3 targetDirection = horizontal(primary.position().subtract(opponentPosition)).normalize();
        Vec3 opponentDirection = leaveOffNose(forward.scale(-1.0), targetDirection,
                ENERGY_FIGHTER_OFF_NOSE_DEG);
        double opponentSpeed = AutopilotProfileRegistry.resolve(level.getServer(), opponent)
                .map(profile -> profile.cruiseSpeedBps() + 2.0)
                .orElse(36.0);

        opponent.moveTo(opponentPosition.x, opponentPosition.y, opponentPosition.z,
                yaw(opponentDirection), 0.0f);
        opponent.setDeltaMovement(opponentDirection.scale(opponentSpeed / 20.0));
        ReflectiveAircraft.setRoll(opponent, 0.0f);
        ReflectiveAircraft.warmEngine(opponent, 0.82f);
        ReflectiveAircraft.applyControl(opponent, 0.0f, 0.0f, 0.0f, 0.82f);
        APPLIED.add(primary.getUUID());

        double separation = primary.distanceTo(opponent);
        double primaryAngle = angleDegrees(forward,
                opponent.position().subtract(primary.position()));
        double opponentAngle = angleDegrees(opponentDirection,
                primary.position().subtract(opponent.position()));
        AutopilotLogManager.writeEvent(level.getServer(), primary,
                "mutual_dogfight_opening_energy_crossing",
                "opponent_uuid=" + opponent.getUUID()
                        + ":separation=" + round(separation)
                        + ":primary_off_nose_deg=" + round(primaryAngle)
                        + ":opponent_off_nose_deg=" + round(opponentAngle)
                        + ":opponent_altitude_advantage=28.0"
                        + ":opponent_speed_bps=" + round(opponentSpeed),
                phase);
    }

    static void clear(UUID aircraftUuid) {
        APPLIED.remove(aircraftUuid);
    }

    private static Vec3 leaveOffNose(Vec3 start, Vec3 target, double remainingDegrees) {
        Vec3 from = horizontal(start).normalize();
        Vec3 to = horizontal(target).normalize();
        double dot = Math.max(-1.0, Math.min(1.0, from.dot(to)));
        double angle = Math.acos(dot);
        double remaining = Math.toRadians(remainingDegrees);
        if (angle <= remaining || angle < 1.0e-6) {
            return from;
        }
        double fraction = (angle - remaining) / angle;
        double sin = Math.sin(angle);
        if (Math.abs(sin) < 1.0e-6) {
            return from.scale(1.0 - fraction).add(to.scale(fraction)).normalize();
        }
        double fromWeight = Math.sin((1.0 - fraction) * angle) / sin;
        double toWeight = Math.sin(fraction * angle) / sin;
        return from.scale(fromWeight).add(to.scale(toWeight)).normalize();
    }

    private static float yaw(Vec3 direction) {
        return (float) Math.toDegrees(Math.atan2(-direction.x, direction.z));
    }

    private static double angleDegrees(Vec3 first, Vec3 second) {
        if (first.lengthSqr() < 1.0e-8 || second.lengthSqr() < 1.0e-8) {
            return 0.0;
        }
        double dot = first.normalize().dot(second.normalize());
        return Math.toDegrees(Math.acos(Math.max(-1.0, Math.min(1.0, dot))));
    }

    private static Vec3 horizontal(Vec3 vector) {
        return new Vec3(vector.x, 0.0, vector.z);
    }

    private static double round(double value) {
        return Math.rint(value * 100.0) / 100.0;
    }
}
