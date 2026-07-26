package com.wwdebug.autopilot;

import com.wwdebug.benchmark.ReflectiveAircraft;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.entity.Entity;

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
        if (!MobPilotGate.isMobPiloted(aircraft)) {
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
        AirCombatValidationSceneManager.tick(level, aircraft, status.get().phase());
        MutualDogfightValidationManager.tick(level, aircraft, status.get().phase());
        // The mutual scene spawns its second real fighter above. Balance the opening before either
        // aircraft's target selector sees the opponent, preventing a free six-o'clock first shot.
        MutualDogfightOpeningAdapter.apply(level, aircraft, status.get().phase());
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
        AirCombatValidationSceneManager.clear(aircraftUuid);
        MutualDogfightValidationManager.clear(aircraftUuid);
        MutualDogfightOpeningAdapter.clear(aircraftUuid);
        AirCombatManeuverManager.clear(aircraftUuid);
    }
}
