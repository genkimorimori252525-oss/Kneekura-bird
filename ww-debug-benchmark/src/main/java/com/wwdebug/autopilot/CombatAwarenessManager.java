package com.wwdebug.autopilot;

import com.wwdebug.benchmark.ReflectiveAircraft;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.Mob;
import net.minecraft.world.entity.player.Player;

import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/** Maintains conservative target awareness separately from flight actuation. */
public final class CombatAwarenessManager {
    private static final Map<UUID, CombatTargetSelector.State> STATES = new ConcurrentHashMap<>();
    private static final Map<UUID, CombatTargetSelector.Solution> SOLUTIONS = new ConcurrentHashMap<>();

    private CombatAwarenessManager() {
    }

    public static void tick(Entity aircraft) {
        if (aircraft.level().isClientSide || !ReflectiveAircraft.isAirplane(aircraft)
                || !(aircraft.level() instanceof ServerLevel level)) {
            clear(aircraft.getUUID());
            return;
        }
        Entity pilot = aircraft.getControllingPassenger();
        if (pilot instanceof Player || !(pilot instanceof Mob)) {
            clear(aircraft.getUUID());
            return;
        }

        Optional<AutonomousFlightManager.SessionStatus> status =
                AutonomousFlightManager.status(aircraft.getUUID());
        if (status.isEmpty()) {
            clear(aircraft.getUUID());
            return;
        }

        CombatValidationSceneManager.tick(level, aircraft);
        CombatTargetSelector.State state = STATES.computeIfAbsent(
                aircraft.getUUID(), ignored -> new CombatTargetSelector.State());
        CombatTargetSelector.Update update = CombatTargetSelector.update(
                level, aircraft, status.get().phase(), state);

        if (update.solution().isPresent()) {
            CombatTargetSelector.Solution solution = update.solution().get();
            SOLUTIONS.put(aircraft.getUUID(), solution);
            if (update.acquiredOrChanged()) {
                AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                        "combat_target_acquired", solution.description(), status.get().phase());
            }
        } else {
            SOLUTIONS.remove(aircraft.getUUID());
            if (update.lost()) {
                AutopilotLogManager.writeEvent(level.getServer(), aircraft,
                        "combat_target_lost", update.reason(), status.get().phase());
            }
        }
    }

    static Optional<CombatTargetSelector.Solution> currentSolution(UUID aircraftUuid) {
        return Optional.ofNullable(SOLUTIONS.get(aircraftUuid));
    }

    public static void clear(UUID aircraftUuid) {
        STATES.remove(aircraftUuid);
        SOLUTIONS.remove(aircraftUuid);
        CombatValidationSceneManager.clear(aircraftUuid);
    }
}
