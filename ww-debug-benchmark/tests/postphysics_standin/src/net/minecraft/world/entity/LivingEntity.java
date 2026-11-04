package net.minecraft.world.entity;
import net.minecraft.world.level.Level;
import java.util.UUID;
public class LivingEntity extends Entity {
    public LivingEntity() { super(new UUID(0, 2), new Level(false)); }
}
