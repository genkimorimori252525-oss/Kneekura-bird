package com.wwdebug.autopilot;

import com.wwdebug.benchmark.ReflectiveAircraft;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.LivingEntity;

import java.util.Optional;

/**
 * Conservative tag-based combat factions for autonomous aircraft.
 *
 * <p>Tags are intentionally directional:</p>
 * <ul>
 *   <li>{@code wwcombat:faction:<id>} declares an entity's faction.</li>
 *   <li>{@code wwcombat:hostile:<id>} allows that entity to attack the named faction.</li>
 * </ul>
 *
 * <p>Aircraft and their pilots share the same effective relationship. When both sides have
 * factions, ordinary Minecraft {@code Enemy} classification is not enough to permit fire; the
 * attacker's faction owner must explicitly declare the target faction hostile.</p>
 */
final class CombatFactionRelations {
    private static final String FACTION_PREFIX = "wwcombat:faction:";
    private static final String HOSTILE_PREFIX = "wwcombat:hostile:";

    private CombatFactionRelations() {
    }

    static Optional<String> faction(Entity entity) {
        if (entity == null) {
            return Optional.empty();
        }
        Optional<String> direct = tagValue(entity, FACTION_PREFIX);
        if (direct.isPresent()) {
            return direct;
        }
        Entity vehicle = entity.getVehicle();
        if (vehicle != null) {
            Optional<String> vehicleFaction = tagValue(vehicle, FACTION_PREFIX);
            if (vehicleFaction.isPresent()) {
                return vehicleFaction;
            }
        }
        if (ReflectiveAircraft.isAirplane(entity)) {
            LivingEntity pilot = entity.getControllingPassenger();
            if (pilot != null) {
                return tagValue(pilot, FACTION_PREFIX);
            }
        }
        return Optional.empty();
    }

    static boolean sameFaction(Entity first, Entity second) {
        Optional<String> firstFaction = faction(first);
        Optional<String> secondFaction = faction(second);
        return firstFaction.isPresent() && secondFaction.isPresent()
                && firstFaction.get().equals(secondFaction.get());
    }

    static boolean explicitlyHostile(Entity attacker, Entity attackerPilot, Entity target) {
        Optional<String> attackerFaction = faction(attacker).or(() -> faction(attackerPilot));
        Optional<String> targetFaction = faction(target);
        if (attackerFaction.isEmpty() || targetFaction.isEmpty()
                || attackerFaction.get().equals(targetFaction.get())) {
            return false;
        }
        String hostileTag = HOSTILE_PREFIX + targetFaction.get();
        return hasRelationshipTag(attacker, hostileTag)
                || hasRelationshipTag(attackerPilot, hostileTag);
    }

    static boolean relationshipDefined(Entity attacker, Entity attackerPilot, Entity target) {
        return faction(attacker).or(() -> faction(attackerPilot)).isPresent()
                || faction(target).isPresent();
    }

    static boolean protectedFromFire(Entity attacker, Entity attackerPilot, Entity candidate) {
        if (sameFaction(attacker, candidate) || sameFaction(attackerPilot, candidate)) {
            return true;
        }
        if (relationshipDefined(attacker, attackerPilot, candidate)) {
            return !explicitlyHostile(attacker, attackerPilot, candidate);
        }
        return false;
    }

    private static boolean hasRelationshipTag(Entity entity, String tag) {
        if (entity == null) {
            return false;
        }
        if (entity.getTags().contains(tag)) {
            return true;
        }
        Entity vehicle = entity.getVehicle();
        if (vehicle != null && vehicle.getTags().contains(tag)) {
            return true;
        }
        if (ReflectiveAircraft.isAirplane(entity)) {
            LivingEntity pilot = entity.getControllingPassenger();
            return pilot != null && pilot.getTags().contains(tag);
        }
        return false;
    }

    private static Optional<String> tagValue(Entity entity, String prefix) {
        return entity.getTags().stream()
                .filter(tag -> tag.startsWith(prefix))
                .map(tag -> tag.substring(prefix.length()))
                .filter(value -> !value.isBlank())
                .sorted()
                .findFirst();
    }
}
