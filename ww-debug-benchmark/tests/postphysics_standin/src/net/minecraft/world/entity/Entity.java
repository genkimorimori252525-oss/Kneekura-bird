package net.minecraft.world.entity;
import java.util.UUID;
import net.minecraft.world.level.Level;
import net.minecraft.world.phys.Vec3;
public class Entity {
    private final UUID uuid;
    private Level world;
    private boolean ground;
    private LivingEntity pilot;
    private Vec3 velocity = new Vec3(0, 0, 0);
    private int setterCalls;
    public Entity(UUID uuid, Level world) { this.uuid = uuid; this.world = world; }
    public net.minecraft.network.chat.Component getName() { return net.minecraft.network.chat.Component.literal("fixture"); }
    public UUID getUUID() { return uuid; }
    public Level level() { return world; }
    public boolean onGround() { return ground; }
    public LivingEntity getControllingPassenger() { return pilot; }
    public Vec3 getDeltaMovement() { return velocity; }
    public void setDeltaMovement(double x, double y, double z) { setterCalls++; velocity = new Vec3(x, y, z); }
    public void fixtureLevel(Level value) { world = value; }
    public void fixtureGround(boolean value) { ground = value; }
    public void fixturePilot(LivingEntity value) { pilot = value; }
    public void fixtureVelocity(double x, double y, double z) { velocity = new Vec3(x, y, z); }
    public void fixtureResetCalls() { setterCalls = 0; }
    public int fixtureSetterCalls() { return setterCalls; }
}
