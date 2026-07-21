package com.wwdebug.benchmark;

import net.minecraft.world.Container;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import net.minecraft.world.phys.Vec3;
import org.joml.Vector3f;

import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.function.Supplier;

/** Soft reflective bridge to Immersive Aircraft and Warfare Wings weapon objects. */
public final class ReflectiveArmament {
    private static final String WARFARE_WINGS_MAIN = "net.velleagle.warfare_wings.WarfareWings";
    private static final String WARFARE_WINGS_MG = "net.velleagle.warfare_wings.entity.weapon.WarfareWingsMG";
    private static final Map<Class<?>, EntityAccessors> ENTITY_ACCESSORS = new ConcurrentHashMap<>();
    private static final Map<Class<?>, WeaponAccessors> WEAPON_ACCESSORS = new ConcurrentHashMap<>();

    private ReflectiveArmament() {
    }

    public static List<MountedWeapon> machineGuns(Entity aircraft) {
        Object value = invoke(entityAccessors(aircraft).getWeapons, aircraft);
        if (!(value instanceof Map<?, ?> map)) {
            return List.of();
        }
        List<MountedWeapon> result = new ArrayList<>();
        for (Map.Entry<?, ?> entry : map.entrySet()) {
            if (!(entry.getKey() instanceof Number slotNumber) || !(entry.getValue() instanceof List<?> weapons)) {
                continue;
            }
            int slot = slotNumber.intValue();
            for (int index = 0; index < weapons.size(); index++) {
                Object weapon = weapons.get(index);
                if (weapon == null || !WARFARE_WINGS_MG.equals(weapon.getClass().getName())) {
                    continue;
                }
                WeaponAccessors accessors = weaponAccessors(weapon);
                int gunnerOffset = number(invoke(accessors.getGunnerOffset, weapon), -1);
                int loadedAmmo = number(invoke(accessors.getAmmo, weapon), -1);
                Object ammoStackValue = invoke(accessors.getAmmoStack, weapon);
                ItemStack ammoStack = ammoStackValue instanceof ItemStack stack ? stack.copy() : ItemStack.EMPTY;
                result.add(new MountedWeapon(slot, index, gunnerOffset, loadedAmmo,
                        ammoStack, weapon.getClass().getName()));
            }
        }
        return List.copyOf(result);
    }

    public static FireResult fire(Entity aircraft, MountedWeapon weapon, Vec3 direction) {
        EntityAccessors accessors = entityAccessors(aircraft);
        if (accessors.fireWeapon == null) {
            return new FireResult(false, weapon.loadedAmmo(), weapon.loadedAmmo(),
                    reserveGunpowder(aircraft), reserveGunpowder(aircraft), "fireWeapon_unavailable");
        }
        int reserveBefore = reserveGunpowder(aircraft);
        int loadedBefore = currentLoadedAmmo(aircraft, weapon);
        Vector3f vector = new Vector3f((float) direction.x, (float) direction.y, (float) direction.z);
        boolean invoked = invokeChecked(accessors.fireWeapon, aircraft,
                weapon.slot(), weapon.index(), vector);
        int reserveAfter = reserveGunpowder(aircraft);
        int loadedAfter = currentLoadedAmmo(aircraft, weapon);
        return new FireResult(invoked, loadedBefore, loadedAfter,
                reserveBefore, reserveAfter, invoked ? "server_fireWeapon" : "reflection_failed");
    }

    public static int reserveGunpowder(Entity aircraft) {
        if (!(aircraft instanceof Container inventory)) {
            return 0;
        }
        int total = 0;
        for (int slot = 0; slot < inventory.getContainerSize(); slot++) {
            ItemStack stack = inventory.getItem(slot);
            if (stack.is(Items.GUNPOWDER)) {
                total += stack.getCount();
            }
        }
        return total;
    }

    public static int estimatedShotsRemaining(Entity aircraft) {
        List<MountedWeapon> weapons = machineGuns(aircraft);
        int loadedShots = weapons.stream()
                .filter(weapon -> weapon.loadedAmmo() > 0)
                .mapToInt(weapon -> weapon.loadedAmmo() / 10)
                .sum();
        int reserveShots = reserveGunpowder(aircraft) * 10;
        return loadedShots + reserveShots;
    }

    /** GameTest-only helper. Players still equip weapons and ammunition through the normal GUI. */
    public static boolean equipTestMachineGun(Entity aircraft, int gunpowderCount) {
        if (!(aircraft instanceof Container inventory)) {
            return false;
        }
        try {
            ClassLoader loader = aircraft.getClass().getClassLoader();
            Class<?> mainClass = Class.forName(WARFARE_WINGS_MAIN, false, loader);
            Field itemField = findField(mainClass, "WW_GUN_ITEM");
            Object supplierValue = itemField == null ? null : itemField.get(null);
            Object itemValue = supplierValue instanceof Supplier<?> supplier ? supplier.get() : supplierValue;
            if (!(itemValue instanceof Item weaponItem)) {
                return false;
            }

            Object description = invoke(entityAccessors(aircraft).getInventoryDescription, aircraft);
            Method getSlots = description == null ? null : findMethod(description.getClass(), "getSlots", String.class);
            Object weaponSlotsValue = invoke(getSlots, description, "weapon");
            if (!(weaponSlotsValue instanceof Iterable<?> weaponSlots)) {
                return false;
            }
            Set<Integer> weaponIndices = ConcurrentHashMap.newKeySet();
            for (Object slot : weaponSlots) {
                int index = number(invoke(findMethod(slot.getClass(), "index"), slot), -1);
                if (index >= 0) {
                    weaponIndices.add(index);
                }
            }
            if (weaponIndices.isEmpty()) {
                return false;
            }

            int weaponSlot = weaponIndices.stream().sorted().findFirst().orElseThrow();
            inventory.setItem(weaponSlot, new ItemStack(weaponItem));
            int ammoSlot = -1;
            for (int slot = 0; slot < inventory.getContainerSize(); slot++) {
                if (!weaponIndices.contains(slot) && inventory.getItem(slot).isEmpty()) {
                    ammoSlot = slot;
                    break;
                }
            }
            if (ammoSlot < 0) {
                for (int slot = 0; slot < inventory.getContainerSize(); slot++) {
                    if (!weaponIndices.contains(slot)) {
                        ammoSlot = slot;
                        break;
                    }
                }
            }
            if (ammoSlot < 0) {
                return false;
            }
            inventory.setItem(ammoSlot, new ItemStack(Items.GUNPOWDER,
                    Math.max(1, Math.min(64, gunpowderCount))));
            inventory.setChanged();
            return true;
        } catch (ReflectiveOperationException | RuntimeException exception) {
            return false;
        }
    }

    private static int currentLoadedAmmo(Entity aircraft, MountedWeapon handle) {
        return machineGuns(aircraft).stream()
                .filter(weapon -> weapon.slot() == handle.slot() && weapon.index() == handle.index())
                .mapToInt(MountedWeapon::loadedAmmo)
                .findFirst()
                .orElse(-1);
    }

    private static EntityAccessors entityAccessors(Entity entity) {
        return ENTITY_ACCESSORS.computeIfAbsent(entity.getClass(), type -> new EntityAccessors(
                findMethod(type, "getWeapons"),
                findMethod(type, "fireWeapon", int.class, int.class, Vector3f.class),
                findMethod(type, "getInventoryDescription")
        ));
    }

    private static WeaponAccessors weaponAccessors(Object weapon) {
        return WEAPON_ACCESSORS.computeIfAbsent(weapon.getClass(), type -> new WeaponAccessors(
                findMethod(type, "getGunnerOffset"),
                findMethod(type, "getAmmo"),
                findMethod(type, "getAmmoStack")
        ));
    }

    private static int number(Object value, int fallback) {
        return value instanceof Number number ? number.intValue() : fallback;
    }

    private static Field findField(Class<?> type, String name) {
        Class<?> current = type;
        while (current != null) {
            try {
                Field field = current.getDeclaredField(name);
                if (Modifier.isStatic(field.getModifiers())) {
                    field.setAccessible(true);
                    return field;
                }
            } catch (NoSuchFieldException ignored) {
            }
            current = current.getSuperclass();
        }
        return null;
    }

    private static Method findMethod(Class<?> type, String name, Class<?>... parameters) {
        Class<?> current = type;
        while (current != null) {
            try {
                Method method = current.getDeclaredMethod(name, parameters);
                method.setAccessible(true);
                return method;
            } catch (NoSuchMethodException ignored) {
                current = current.getSuperclass();
            }
        }
        return null;
    }

    private static Object invoke(Method method, Object target, Object... arguments) {
        if (method == null || target == null) {
            return null;
        }
        try {
            return method.invoke(target, arguments);
        } catch (ReflectiveOperationException | RuntimeException ignored) {
            return null;
        }
    }

    private static boolean invokeChecked(Method method, Object target, Object... arguments) {
        if (method == null || target == null) {
            return false;
        }
        try {
            method.invoke(target, arguments);
            return true;
        } catch (ReflectiveOperationException | RuntimeException ignored) {
            return false;
        }
    }

    private record EntityAccessors(Method getWeapons, Method fireWeapon, Method getInventoryDescription) {
    }

    private record WeaponAccessors(Method getGunnerOffset, Method getAmmo, Method getAmmoStack) {
    }

    public record MountedWeapon(
            int slot,
            int index,
            int gunnerOffset,
            int loadedAmmo,
            ItemStack ammoStack,
            String className
    ) {
    }

    public record FireResult(
            boolean invoked,
            int loadedAmmoBefore,
            int loadedAmmoAfter,
            int reserveBefore,
            int reserveAfter,
            String reason
    ) {
    }
}
