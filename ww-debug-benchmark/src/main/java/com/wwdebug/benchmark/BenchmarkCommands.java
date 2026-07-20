package com.wwdebug.benchmark;

import com.mojang.brigadier.CommandDispatcher;
import com.mojang.brigadier.builder.LiteralArgumentBuilder;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.commands.Commands;

public final class BenchmarkCommands {
    private BenchmarkCommands() {
    }

    public static void register(CommandDispatcher<CommandSourceStack> dispatcher) {
        LiteralArgumentBuilder<CommandSourceStack> run = Commands.literal("run")
                .executes(context -> BenchmarkManager.start(context.getSource(), BenchmarkCategory.ALL, false));
        LiteralArgumentBuilder<CommandSourceStack> runVariants = Commands.literal("run_variants")
                .executes(context -> BenchmarkManager.start(context.getSource(), BenchmarkCategory.ALL, true));

        for (BenchmarkCategory category : BenchmarkCategory.values()) {
            run.then(Commands.literal(category.id())
                    .executes(context -> BenchmarkManager.start(context.getSource(), category, false)));
            runVariants.then(Commands.literal(category.id())
                    .executes(context -> BenchmarkManager.start(context.getSource(), category, true)));
        }

        dispatcher.register(Commands.literal("wwdebug")
                .requires(source -> source.hasPermission(2))
                .then(Commands.literal("benchmark")
                        .then(run)
                        .then(runVariants)
                        .then(Commands.literal("list")
                                .executes(context -> BenchmarkManager.list(context.getSource(), false)))
                        .then(Commands.literal("list_variants")
                                .executes(context -> BenchmarkManager.list(context.getSource(), true)))
                        .then(Commands.literal("status")
                                .executes(context -> BenchmarkManager.status(context.getSource())))
                        .then(Commands.literal("stop")
                                .executes(context -> BenchmarkManager.stop(context.getSource())))));
    }
}
