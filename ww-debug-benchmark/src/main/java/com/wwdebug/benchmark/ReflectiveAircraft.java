package com.wwdebug.benchmark;

import net.minecraft.world.Container;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;

import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Soft adapter for Immersive Aircraft. This module deliberately has no compile-time
 * dependency on the mod, so it can be dropped next to different compatible builds.
 */
public final class ReflectiveAircraft {
    private static final String AIRPLANE_CLASS = "immersive_aircraft.entity.AirplaneEntity";
    private static final String VEHICLE_STAT_CLASS = "immersive_aircraft.item.upgrade.VehicleStat";
    private static final Map<Class<?>, Accessors> ACCESSORS = new ConcurrentHashMap<>();
    private static final Map<ClassLoader, Map<String, Object>> VEHICLE_STATS = new ConcurrentHashMap<>();

    private ReflectiveAircraft() {
    }

    public static boolean isAirplane(Entity entity) {
        Class<?> type = entity.getClass();
        while (type != null) {
            if (AIRPLANE_CLASS.equals(type.getName())) {
                return true;
            }
            type = type.getSuperclass();
        }
        return false;
    }

    public static boolean isControllable(Entity entity) {
        Accessors accessors = accessors(entity);
        return accessors.setInputs != null && accessors.setEngineTarget != null;
    }

    public static void applyControl(Entity entity, float x, float y, float z, float engineTarget) {
        Accessors accessors = accessors(entity);
        invoke(accessors.setInputs, entity, x, y, z);
        invoke(accessors.setEngineTarget, entity, engineTarget);
    }

    public static void resetInternalState(Entity entity) {
        Accessors accessors = accessors(entity);
        invoke(accessors.chill, entity);
        invoke(accessors.setEngineTarget, entity, 0.0f);
    }

    public static double enginePower(Entity entity) {
        Object value = invoke(accessors(entity).getEnginePower, entity);
        return value instanceof Number number ? number.doubleValue() : Double.NaN;
    }

    public static double engineTarget(Entity entity) {
        Object value = invoke(accessors(entity).getEngineTarget, entity);
        return value instanceof Number number ? number.doubleValue() : Double.NaN;
    }

    public static double rollDegrees(Entity entity) {
        Object value = invoke(accessors(entity).getZRot, entity);
        return value instanceof Number number ? number.doubleValue() : Double.NaN;
    }

    public static double fuelUtilization(Entity entity) {
        Object value = invoke(accessors(entity).getFuelUtilization, entity);
        return value instanceof Number number ? number.doubleValue() : Double.NaN;
    }

    public static void setRoll(Entity entity, float roll) {
        invoke(accessors(entity).setZRot, entity, roll);
    }

    public static int passengerSpace(Entity entity) {
        Object value = invoke(accessors(entity).getPassengerSpace, entity);
        return value instanceof Number number ? number.intValue() : entity.getPassengers().size();
    }

    public static void fillFuel(Entity entity) {
        Accessors accessors = accessors(entity);
        Object description = invoke(accessors.getInventoryDescription, entity);
        Object inventoryObject = invoke(accessors.getInventory, entity);
        if (description == null || !(inventoryObject instanceof Container inventory)) {
            return;
        }

        Method getSlots = findMethod(description.getClass(), "getSlots", String.class);
        Object slotsObject = invoke(getSlots, description, "boiler");
        if (!(slotsObject instanceof Iterable<?> slots)) {
            return;
        }

        for (Object slot : slots) {
            Method indexMethod = findMethod(slot.getClass(), "index");
            Object indexValue = invoke(indexMethod, slot);
            if (indexValue instanceof Number number) {
                inventory.setItem(number.intValue(), new ItemStack(Items.COAL, 64));
            }
        }
    }

    public static Map<String, Double> effectiveStats(Entity entity) {
        Map<String, Double> result = new LinkedHashMap<>();
        Accessors accessors = accessors(entity);
        Object properties = invoke(accessors.getProperties, entity);
        if (properties == null) {
            return result;
        }

        Method get = findSingleArgumentMethod(properties.getClass(), "get");
        Method getAdditive = findSingleArgumentMethod(properties.getClass(), "getAdditive");
        if (get == null) {
            return result;
        }

        Map<String, Object> stats = vehicleStats(entity.getClass().getClassLoader());
        for (String statName : List.of(
                "ENGINE_SPEED", "ACCELERATION", "YAW_SPEED", "PITCH_SPEED", "PUSH_SPEED",
                "LIFT", "FRICTION", "GLIDE_FACTOR", "MASS", "BRAKE_FACTOR", "GROUND_FRICTION",
                "HORIZONTAL_DECAY", "VERTICAL_DECAY", "ROTATION_DECAY", "WIND"
        )) {
            Object stat = stats.get(statName);
            Object value = invoke(get, properties, stat);
            if (value instanceof Number number) {
                result.put(toJsonName(statName), number.doubleValue());
            }
        }

        Object stabilizer = stats.get("STABILIZER");
        Object stabilizerValue = invoke(getAdditive, properties, stabilizer);
        if (stabilizerValue instanceof Number number) {
            result.put("stabilizer", number.doubleValue());
        }
        return result;
    }

    private static Accessors accessors(Entity entity) {
        return ACCESSORS.computeIfAbsent(entity.getClass(), type -> new Accessors(
                findMethod(type, "setInputs", float.class, float.class, float.class),
                findMethod(type, "setEngineTarget", float.class),
                findMethod(type, "getEnginePower"),
                findMethod(type, "getEngineTarget"),
                findMethod(type, "getZRot"),
                findMethod(type, "getFuelUtilization"),
                findMethod(type, "setZRot", float.class),
                findMethod(type, "chill"),
                findMethod(type, "getPassengerSpace"),
                findMethod(type, "getProperties"),
                findMethod(type, "getInventoryDescription"),
                findMethod(type, "getInventory")
        ));
    }

    private static Map<String, Object> vehicleStats(ClassLoader loader) {
        return VEHICLE_STATS.computeIfAbsent(loader, ignored -> {
            Map<String, Object> values = new LinkedHashMap<>();
            try {
                Class<?> statClass = Class.forName(VEHICLE_STAT_CLASS, false, loader);
                for (Field field : statClass.getFields()) {
                    if (Modifier.isStatic(field.getModifiers()) && statClass.isAssignableFrom(field.getType())) {
                        values.put(field.getName(), field.get(null));
                    }
                }
            } catch (ReflectiveOperationException ignoredException) {
                // Fail open. Declared JSON properties are still exported.
            }
            return values;
        });
    }

    private static String toJsonName(String constant) {
        StringBuilder result = new StringBuilder();
        boolean upper = false;
        for (char character : constant.toLowerCase().toCharArray()) {
            if (character == '_') {
                upper = true;
            } else if (upper) {
                result.append(Character.toUpperCase(character));
                upper = false;
            } else {
                result.append(character);
            }
        }
        return result.toString();
    }

    private static Method findSingleArgumentMethod(Class<?> type, String name) {
        Class<?> current = type;
        while (current != null) {
            for (Method method : current.getDeclaredMethods()) {
                if (method.getName().equals(name) && method.getParameterCount() == 1) {
                    method.setAccessible(true);
                    return method;
                }
            }
            current = current.getSuperclass();
        }
        return null;
    }

    private static Method findMethod(Class<?> type, String name, Class<?>... parameterTypes) {
        Class<?> current = type;
        while (current != null) {
            try {
                Method method = current.getDeclaredMethod(name, parameterTypes);
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

    private record Accessors(
            Method setInputs,
            Method setEngineTarget,
            Method getEnginePower,
            Method getEngineTarget,
            Method getZRot,
            Method getFuelUtilization,
            Method setZRot,
            Method chill,
            Method getPassengerSpace,
            Method getProperties,
            Method getInventoryDescription,
            Method getInventory
    ) {
    }
}