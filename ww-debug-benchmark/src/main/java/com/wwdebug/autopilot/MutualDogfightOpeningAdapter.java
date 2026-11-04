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
 * GameTest-only neutral opening for the reciprocal fighter qualification.
 *
 * <p>The scene manager creates the P-47N first. Before either aircraft selects a target, this
 * adapter moves the opponent from the A6M's six o'clock to a symmetric offset head-on geometry.
 * Both pilots therefore begin about twenty degrees off the other's nose, so neither receives a
 * free rear-quarter shot and both must solve the intercept.</p>
 */
final class MutualDogfightOpeningAdapter {
    private static final String SCENARIO_PROPERTY = "wwdebug.flightGameTestScenario";
    private static final String SCENARIO = "dogfight_mutual";
    private static final String TEST_NAME_PREFIX = "AUTOPILOT TEST ";
    private static final String OPPONENT_TAG = "wwcombat:mutual_opponent";
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

        AABB search = primary.getBoundingBox().inflate(240.0, 96.0, 240.0);
        Entity opponent = level.getEntities(primary, search,
                        entity -> !entity.isRemoved()
                                && entity.getTags().contains(OPPONENT_TAG)
                                && ReflectiveAircraft.isAirplane(entity))
                .stream().findFirst().orElse(null);
        if (opponent == null || !MobPilotGate.isMobPiloted(opponent)) {
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
        Vec3 opponentDirection = forward.scale(-1.0);
        Vec3 opponentPosition = primary.position()
                .add(forward.scale(150.0))
                .add(right.scale(55.0))
                .add(0.0, 8.0, 0.0);
        double opponentSpeed = AutopilotProfileRegistry.resolve(level.getServer(), opponent)
                .map(FlightProfile::cruiseSpeedBps)
                .orElse(34.0);

        opponent.moveTo(opponentPosition.x, opponentPosition.y, opponentPosition.z,
                yaw(opponentDirection), 0.0f);
        opponent.setDeltaMovement(opponentDirection.scale(opponentSpeed / 20.0));
        ReflectiveAircraft.setRoll(opponent, 0.0f);
        ReflectiveAircraft.warmEngine(opponent, 0.72f);
        ReflectiveAircraft.applyControl(opponent, 0.0f, 0.0f, 0.0f, 0.72f);
        APPLIED.add(primary.getUUID());

        double separation = primary.distanceTo(opponent);
        double primaryAngle = angleDegrees(forward,
                opponent.position().subtract(primary.position()));
        double opponentAngle = angleDegrees(opponentDirection,
                primary.position().subtract(opponent.position()));
        AutopilotLogManager.writeEvent(level.getServer(), primary,
                "mutual_dogfight_opening_balanced",
                "opponent_uuid=" + opponent.getUUID()
                        + ":separation=" + round(separation)
                        + ":primary_off_nose_deg=" + round(primaryAngle)
                        + ":opponent_off_nose_deg=" + round(opponentAngle)
                        + ":opponent_speed_bps=" + round(opponentSpeed),
                phase);
    }

    static void clear(UUID aircraftUuid) {
        APPLIED.remove(aircraftUuid);
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
