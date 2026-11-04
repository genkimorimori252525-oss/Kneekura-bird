package net.minecraft.server.level;
import net.minecraft.server.MinecraftServer;
import net.minecraft.world.level.Level;
public class ServerLevel extends Level {
    public ServerLevel() { super(false); }
    public MinecraftServer getServer() { return null; }
}
