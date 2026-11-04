package com.wwdebug.gametestprobe;

import java.lang.reflect.Field;
import java.lang.reflect.Modifier;
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.Objects;
import java.util.function.Consumer;
import net.minecraft.gametest.framework.GameTestBatch;
import net.minecraft.gametest.framework.TestFunction;
import net.minecraft.server.level.ServerLevel;

/** Test-only snapshot inspection; does not authorize or start a GameTest run. */
public final class GameTestBatchGate {
    private static final String BATCH = "brake_pilot_ownership_probe_only";
    private static final String TEST = "stalebrakepreservespilotauthority";
    private static final String STRUCTURE = "wwdebug_brake_probe:empty";

    private GameTestBatchGate() { }

    /** A caller must choose known absence or provide the exact trusted callback object. */
    public static final class CallbackExpectation {
        private final Consumer<ServerLevel> identity;

        private CallbackExpectation(Consumer<ServerLevel> identity) { this.identity = identity; }
        public static CallbackExpectation absent() { return new CallbackExpectation(null); }
        public static CallbackExpectation exact(Consumer<ServerLevel> callback) {
            return new CallbackExpectation(Objects.requireNonNull(callback, "callback"));
        }
    }

    /**
     * Inspect trusted Forge collection objects at one instant; an empty list means only that
     * these checks passed. The caller must independently establish expected object provenance,
     * source/classpath isolation and that the inspected selection cannot change before use.
     */
    public static List<String> inspect(Collection<GameTestBatch> batches, TestFunction expected,
            CallbackExpectation before, CallbackExpectation after) {
        List<String> errors = new ArrayList<>();
        if (batches == null || expected == null || before == null || after == null) {
            return List.of("selection or expected identity is unknown");
        }
        try {
            var selected = List.copyOf(batches);
            if (selected.size() != 1) return List.of("expected exactly one batch");
            var batch = selected.get(0);
            if (batch.getClass() != GameTestBatch.class || expected.getClass() != TestFunction.class) {
                return List.of("unsupported batch or test implementation");
            }
            if (!(BATCH + ":1").equals(batch.getName())) errors.add("unexpected batch name");
            var tests = List.copyOf(batch.getTestFunctions());
            if (tests.size() != 1 || tests.get(0) != expected) {
                errors.add("expected test identity is absent or not unique");
            } else {
                if (!TEST.equals(expected.getTestName())) errors.add("unexpected test name");
                if (!STRUCTURE.equals(expected.getStructureName())) errors.add("unexpected structure name");
                if (!BATCH.equals(expected.getBatchName())) errors.add("unexpected test batch name");
                if (!expected.isRequired()) errors.add("test is not required");
            }
            if (callback(batch, "beforeBatchFunction") != before.identity) errors.add("unexpected before callback");
            if (callback(batch, "afterBatchFunction") != after.identity) errors.add("unexpected after callback");
        } catch (ReflectiveOperationException | RuntimeException exception) {
            errors.add("could not inspect the batch selection");
        }
        return List.copyOf(errors);
    }

    private static Object callback(GameTestBatch batch, String name) throws ReflectiveOperationException {
        Field field = GameTestBatch.class.getDeclaredField(name);
        if (!isCallbackFieldShape(field) || !field.trySetAccessible()) {
            throw new IllegalAccessException("callback field inaccessible or changed");
        }
        return field.get(batch);
    }

    static boolean isCallbackFieldShape(Field field) {
        int flags = field.getModifiers();
        return field.getType() == Consumer.class && Modifier.isPrivate(flags)
                && Modifier.isFinal(flags) && !Modifier.isStatic(flags);
    }
}
