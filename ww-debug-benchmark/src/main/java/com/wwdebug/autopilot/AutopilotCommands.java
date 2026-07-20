package com.wwdebug.autopilot;

import com.mojang.brigadier.CommandDispatcher;
import com.mojang.brigadier.arguments.StringArgumentType;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.commands.Commands;
import net.minecraft.network.chat.Component;

import java.util.List;

public final class AutopilotCommands {
    private AutopilotCommands() {
    }

    public static void register(CommandDispatcher<CommandSourceStack> dispatcher) {
        dispatcher.register(Commands.literal("wwdebug")
                .requires(source -> source.hasPermission(2))
                .then(Commands.literal("autopilot")
                        .then(Commands.literal("profiles")
                                .then(Commands.literal("reload")
                                        .executes(context -> reloadProfiles(context.getSource())))
                                .then(Commands.literal("source")
                                        .executes(context -> profileSource(context.getSource()))))
                        .then(Commands.literal("status")
                                .executes(context -> activeStatus(context.getSource())))
                        .then(Commands.literal("logs")
                                .executes(context -> logPath(context.getSource())))
                        .then(Commands.literal("validate")
                                .then(Commands.literal("fighters")
                                        .executes(context -> AutopilotValidationManager.startAll(context.getSource())))
                                .then(Commands.literal("fighter")
                                        .then(Commands.argument("entity_id", StringArgumentType.word())
                                                .executes(context -> AutopilotValidationManager.startOne(
                                                        context.getSource(),
                                                        StringArgumentType.getString(context, "entity_id")))))
                                .then(Commands.literal("status")
                                        .executes(context -> AutopilotValidationManager.status(context.getSource())))
                                .then(Commands.literal("stop")
                                        .executes(context -> AutopilotValidationManager.stop(context.getSource()))))));
    }

    private static int reloadProfiles(CommandSourceStack source) {
        int count = AutopilotProfileRegistry.reload(source.getServer());
        source.sendSuccess(() -> Component.literal(
                "Loaded " + count + " autonomous-flight profile keys from "
                        + AutopilotProfileRegistry.sourceDescription()), false);
        return count;
    }

    private static int profileSource(CommandSourceStack source) {
        source.sendSuccess(() -> Component.literal(
                "Autonomous-flight profile source: " + AutopilotProfileRegistry.sourceDescription()
                        + " (keys=" + AutopilotProfileRegistry.profileKeyCount() + ")"), false);
        return AutopilotProfileRegistry.profileKeyCount();
    }

    private static int activeStatus(CommandSourceStack source) {
        List<AutonomousFlightManager.SessionStatus> statuses = AutonomousFlightManager.activeStatuses();
        if (statuses.isEmpty()) {
            source.sendSuccess(() -> Component.literal("No mob-piloted autonomous-flight sessions are active."), false);
            return 0;
        }
        source.sendSuccess(() -> Component.literal("Active autonomous-flight sessions: " + statuses.size()), false);
        for (AutonomousFlightManager.SessionStatus status : statuses) {
            source.sendSuccess(() -> Component.literal(
                    "- " + status.aircraftName()
                            + " [" + status.aircraftUuid() + "]"
                            + " profile=" + status.profileId()
                            + " doctrine=" + status.doctrine()
                            + " phase=" + status.phase()
                            + " phaseTicks=" + status.phaseTicks()
                            + " missionTicks=" + status.missionTicks()
                            + " reason=" + status.transitionReason()), false);
        }
        return statuses.size();
    }

    private static int logPath(CommandSourceStack source) {
        source.sendSuccess(() -> Component.literal(
                "Autonomous-flight log directory: "
                        + AutopilotLogManager.currentDirectory(source.getServer())), false);
        return 1;
    }
}