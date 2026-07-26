package com.wwdebug.autopilot;

import java.util.Optional;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.Mob;
import net.minecraft.world.entity.player.Player;

/**
 * The single authority on whether an aircraft is under mob control.
 *
 * <p>A player at the controls must receive no automated input whatsoever. Before this class that
 * rule was expressed as the same two-part condition copied into eleven production sites, so a new
 * controller could omit it and nothing would notice. Every production writer now asks here
 * instead.</p>
 *
 * <p><strong>This is not target selection.</strong> Excluding a player as the <em>pilot</em> and
 * excluding a player as a <em>weapons target</em> are different rules that happen to test the same
 * Java type. Friendly-fire protection lives in {@code CombatTargetSelector} and
 * {@code CombatWeaponManager} and must not be routed through this gate: merging them would let a
 * change to one silently move the other.</p>
 */
public final class MobPilotGate {
    private MobPilotGate() {
    }

    /**
     * The mob currently flying {@code aircraft}.
     *
     * <p>Empty when a player holds the controls, when the seat is empty, and when the occupant is
     * some other entity. {@code Player} does not extend {@code Mob} in vanilla, so the type test
     * alone would already exclude it; the explicit check is kept so the intent survives a modded
     * hierarchy in which that stops being true.</p>
     */
    public static Optional<Mob> pilotOf(Entity aircraft) {
        if (aircraft == null) {
            return Optional.empty();
        }
        Entity pilot = aircraft.getControllingPassenger();
        if (pilot instanceof Player || !(pilot instanceof Mob mob)) {
            return Optional.empty();
        }
        return Optional.of(mob);
    }

    /** Whether automated control may write to {@code aircraft} at all this tick. */
    public static boolean isMobPiloted(Entity aircraft) {
        return pilotOf(aircraft).isPresent();
    }

    /**
     * Whether a player holds the controls.
     *
     * <p>Distinct from {@code !isMobPiloted}: an empty seat is neither mob-piloted nor
     * player-controlled, and the two cases call for different handling — an empty seat ends the
     * session, a player takeover surrenders authority.</p>
     */
    public static boolean isPlayerControlled(Entity aircraft) {
        return aircraft != null && aircraft.getControllingPassenger() instanceof Player;
    }
}
