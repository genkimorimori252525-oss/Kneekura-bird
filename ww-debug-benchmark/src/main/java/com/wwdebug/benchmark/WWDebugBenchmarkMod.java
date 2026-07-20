package com.wwdebug.benchmark;

import com.mojang.logging.LogUtils;
import com.wwdebug.autopilot.AutonomousFlightManager;
import com.wwdebug.autopilot.AutopilotCommands;
import net.minecraftforge.common.MinecraftForge;
import net.minecraftforge.event.RegisterCommandsEvent;
import net.minecraftforge.event.TickEvent;
import net.minecraftforge.event.server.ServerStoppingEvent;
import net.minecraftforge.eventbus.api.SubscribeEvent;
import net.minecraftforge.fml.common.Mod;
import org.slf4j.Logger;

@Mod(WWDebugBenchmarkMod.MOD_ID)
public final class WWDebugBenchmarkMod {
    public static final String MOD_ID = "wwdebug_benchmark";
    public static final Logger LOGGER = LogUtils.getLogger();

    public WWDebugBenchmarkMod() {
        MinecraftForge.EVENT_BUS.register(this);
    }

    @SubscribeEvent
    public void registerCommands(RegisterCommandsEvent event) {
        BenchmarkCommands.register(event.getDispatcher());
        AutopilotCommands.register(event.getDispatcher());
    }

    @SubscribeEvent
    public void serverTick(TickEvent.ServerTickEvent event) {
        if (event.phase == TickEvent.Phase.END) {
            BenchmarkManager.tick(event.getServer());
            AutonomousFlightManager.serverTick(event.getServer());
        }
    }

    @SubscribeEvent
    public void serverStopping(ServerStoppingEvent event) {
        BenchmarkManager.stopSilently(event.getServer());
        AutonomousFlightManager.stopAll(event.getServer());
    }
}