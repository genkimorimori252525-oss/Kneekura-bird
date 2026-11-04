package com.wwdebug.gametestprobe;

import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.function.Consumer;
import java.lang.reflect.Field;
import net.minecraft.gametest.framework.GameTestBatch;
import net.minecraft.gametest.framework.GameTestHelper;
import net.minecraft.gametest.framework.TestFunction;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.block.Rotation;

/** Standalone tests: no world or GameTest server is constructed. */
public final class GameTestBatchGateChecks {
    private static final String BATCH = "brake_pilot_ownership_probe_only";
    private static final String TEST = "stalebrakepreservespilotauthority";
    private static final String STRUCTURE = "wwdebug_brake_probe:empty";
    private static int checked;

    private static final class CallbackFieldShapes {
        private final Consumer<ServerLevel> expected = null;
        private static final Consumer<ServerLevel> shared = null;
        private Consumer<ServerLevel> mutable = null;
        public final Consumer<ServerLevel> exposed = null;
        private final String wrongType = null;
    }

    private static TestFunction test(String batch, String name, String structure, boolean required) {
        return new TestFunction(batch, name, structure, (Rotation) null, 40, 0L,
                required, 1, 1, helper -> {});
    }

    private static TestFunction validTest() { return test(BATCH, TEST, STRUCTURE, true); }
    private static GameTestBatch batch(String name, Collection<TestFunction> tests,
            Consumer<ServerLevel> before, Consumer<ServerLevel> after) {
        return new GameTestBatch(name, tests, before, after);
    }

    private static void expect(boolean accepted, String name, Collection<GameTestBatch> batches,
            TestFunction expected, GameTestBatchGate.CallbackExpectation before,
            GameTestBatchGate.CallbackExpectation after) {
        boolean result = GameTestBatchGate.inspect(batches, expected, before, after).isEmpty();
        if (result != accepted) throw new AssertionError(name + ": " + result);
        checked++;
    }

    public static void main(String[] args) throws Exception {
        var none = GameTestBatchGate.CallbackExpectation.absent();
        var good = validTest();
        var normal = batch(BATCH + ":1", List.of(good), null, null);
        expect(true, "exact instance without callbacks", List.of(normal), good, none, none);
        expect(false, "unknown expected test", List.of(normal), null, none, none);
        expect(false, "unknown callbacks", List.of(normal), good, null, none);
        expect(false, "null batches", null, good, none, none);
        expect(false, "no batches", List.of(), good, none, none);
        expect(false, "multiple batches", List.of(normal, normal), good, none, none);
        var nullBatch = new ArrayList<GameTestBatch>(); nullBatch.add(null);
        expect(false, "null batch", nullBatch, good, none, none);
        expect(false, "wrong batch name", List.of(batch("wrong", List.of(good), null, null)), good, none, none);
        expect(false, "more than one test", List.of(batch(BATCH + ":1", List.of(good, good), null, null)), good, none, none);
        expect(false, "same name different object", List.of(normal), validTest(), none, none);
        var subclassBatch = new GameTestBatch(BATCH + ":1", List.of(good), null, null) {
            @Override public String getName() { throw new AssertionError("subclass must not be invoked"); }
        };
        expect(false, "unsupported batch subclass", List.of(subclassBatch), good, none, none);
        var subclassTest = new TestFunction(BATCH, TEST, STRUCTURE, (Rotation) null, 40, 0L,
                true, 1, 1, helper -> {}) { };
        expect(false, "unsupported test subclass", List.of(batch(BATCH + ":1", List.of(subclassTest), null, null)), subclassTest, none, none);
        Collection<GameTestBatch> throwingCollection = new ArrayList<>() {
            @Override public Object[] toArray() { throw new IllegalStateException("unreadable selection"); }
        };
        expect(false, "unreadable selection", throwingCollection, good, none, none);
        var mutableTests = new ArrayList<TestFunction>(); mutableTests.add(good);
        var mutableBatch = batch(BATCH + ":1", mutableTests, null, null);
        expect(true, "unchanged mutable list", List.of(mutableBatch), good, none, none);
        mutableTests.add(validTest());
        expect(false, "changed mutable list on a fresh inspection", List.of(mutableBatch), good, none, none);
        var wrongName = test(BATCH, "wrong", STRUCTURE, true);
        expect(false, "wrong test name", List.of(batch(BATCH + ":1", List.of(wrongName), null, null)), wrongName, none, none);
        var wrongStructure = test(BATCH, TEST, "other:empty", true);
        expect(false, "wrong structure", List.of(batch(BATCH + ":1", List.of(wrongStructure), null, null)), wrongStructure, none, none);
        var wrongTestBatch = test("other", TEST, STRUCTURE, true);
        expect(false, "wrong test batch", List.of(batch(BATCH + ":1", List.of(wrongTestBatch), null, null)), wrongTestBatch, none, none);
        var optional = test(BATCH, TEST, STRUCTURE, false);
        expect(false, "optional test", List.of(batch(BATCH + ":1", List.of(optional), null, null)), optional, none, none);
        Consumer<ServerLevel> before = level -> { throw new AssertionError("must not execute callback"); };
        Consumer<ServerLevel> after = level -> { throw new AssertionError("must not execute callback"); };
        var withCallbacks = batch(BATCH + ":1", List.of(good), before, after);
        expect(false, "unexpected before and after", List.of(withCallbacks), good, none, none);
        expect(false, "before known only", List.of(withCallbacks), good, GameTestBatchGate.CallbackExpectation.exact(before), none);
        expect(false, "wrong callback identity", List.of(withCallbacks), good, GameTestBatchGate.CallbackExpectation.exact(level -> {}), GameTestBatchGate.CallbackExpectation.exact(after));
        expect(true, "exact callbacks", List.of(withCallbacks), good, GameTestBatchGate.CallbackExpectation.exact(before), GameTestBatchGate.CallbackExpectation.exact(after));
        for (String name : List.of("expected", "shared", "mutable", "exposed", "wrongType")) {
            Field field = CallbackFieldShapes.class.getDeclaredField(name);
            boolean expectedShape = name.equals("expected");
            if (GameTestBatchGate.isCallbackFieldShape(field) != expectedShape) {
                throw new AssertionError("unexpected callback field shape acceptance: " + name);
            }
            checked++;
        }
        System.out.println("Passed " + checked + " selection checks with actual mapped Forge classes; no server started.");
    }
}
