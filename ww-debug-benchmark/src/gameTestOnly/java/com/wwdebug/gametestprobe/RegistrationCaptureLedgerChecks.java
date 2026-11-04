package com.wwdebug.gametestprobe;

import java.lang.reflect.Method;
import java.util.concurrent.atomic.AtomicReference;
import com.wwdebug.gametestprobe.RegistrationCaptureLedger.CallbackObservation;
import com.wwdebug.gametestprobe.RegistrationCaptureLedger.Status;

/** Caller-reported synthetic events only; does not exercise Forge registration or a server. */
public final class RegistrationCaptureLedgerChecks {
    public static final class Fixture {
        public static void valid(String argument) { }
        public static void other(String argument) { }
        public void instance(String argument) { }
        private static void hidden(String argument) { }
        public static int value(String argument) { return 0; }
    }

    private static int count;
    private static int failures;
    private static void check(boolean ok, String name) {
        count++;
        if (!ok) { failures++; System.err.println("FAIL " + name); }
    }
    private static Method method(String name) throws ReflectiveOperationException {
        return Fixture.class.getDeclaredMethod(name, String.class);
    }
    private static RegistrationCaptureLedger ledger() {
        return new RegistrationCaptureLedger(Fixture.class, "valid", String.class);
    }
    private static final class Scenario {
        final RegistrationCaptureLedger ledger = ledger();
        final Method method;
        final Object consumer = new Object();
        final Object function = new Object();
        Object token;
        Scenario() throws Exception {
            method = method("valid");
            token = ledger.begin(method);
        }
        void captureConsumer() { ledger.consumer(token, method, consumer); }
        void construct() { ledger.constructed(token, method, consumer, function); }
        void register() { ledger.registered(token, method, function); }
        void select() { ledger.selection(token, new Object[] {function}); }
        void callbacksAbsent() { ledger.callbacks(token, CallbackObservation.ABSENT, CallbackObservation.ABSENT); }
        void complete() { captureConsumer(); construct(); register(); select(); callbacksAbsent(); }
    }
    private static void tolerate(Runnable action) {
        try { action.run(); } catch (RuntimeException expected) { /* sticky status is the contract */ }
    }
    private static void inconsistent(Scenario s, Runnable bad, String name) {
        tolerate(bad);
        check(s.ledger.status() == Status.INCONSISTENT, name);
        tolerate(s::complete);
        tolerate(() -> s.ledger.finish(s.token));
        check(s.ledger.status() == Status.INCONSISTENT, name + " remains inconsistent");
    }
    private static void rejectConstructor(String name) {
        boolean rejected = false;
        try { new RegistrationCaptureLedger(Fixture.class, name, String.class); }
        catch (RuntimeException expected) { rejected = true; }
        check(rejected, "invalid expected method " + name);
    }
    public static void main(String[] args) throws Exception {
        rejectConstructor("missing");
        rejectConstructor("instance");
        rejectConstructor("hidden");
        rejectConstructor("value");

        Scenario good = new Scenario();
        check(good.ledger.status() == Status.INCOMPLETE, "begin is incomplete");
        good.complete();
        check(good.ledger.status() == Status.INCOMPLETE, "finish required");
        good.ledger.finish(good.token);
        check(good.ledger.status() == Status.CONSISTENT, "matching events consistent");
        tolerate(() -> good.ledger.finish(good.token));
        check(good.ledger.status() == Status.INCONSISTENT, "finish cannot be replayed");

        Scenario wrongStart = new Scenario();
        tolerate(() -> wrongStart.ledger.begin(methodUnchecked("other")));
        check(wrongStart.ledger.status() == Status.INCONSISTENT, "duplicate or wrong begin");
        RegistrationCaptureLedger startOther = ledger();
        tolerate(() -> startOther.begin(methodUnchecked("other")));
        check(startOther.status() == Status.INCONSISTENT, "wrong expected Method");
        RegistrationCaptureLedger startNull = ledger();
        tolerate(() -> startNull.begin(null));
        check(startNull.status() == Status.INCONSISTENT, "null begin Method");

        // Same binary name is not the same declaring class when loaded independently.
        byte[] fixtureBytes;
        try (var stream = Fixture.class.getResourceAsStream("RegistrationCaptureLedgerChecks$Fixture.class")) {
            if (stream == null) throw new AssertionError("fixture class bytes unavailable");
            fixtureBytes = stream.readAllBytes();
        }
        class SeparateLoader extends ClassLoader {
            SeparateLoader() { super(null); }
            Class<?> define() { return defineClass(Fixture.class.getName(), fixtureBytes, 0, fixtureBytes.length); }
        }
        Class<?> duplicateClass = new SeparateLoader().define();
        check(duplicateClass.getName().equals(Fixture.class.getName()) && duplicateClass != Fixture.class,
                "same class name from distinct loader");
        RegistrationCaptureLedger differentLoader = ledger();
        tolerate(() -> {
            try { differentLoader.begin(duplicateClass.getDeclaredMethod("valid", String.class)); }
            catch (ReflectiveOperationException exception) { throw new AssertionError(exception); }
        });
        check(differentLoader.status() == Status.INCONSISTENT, "same name but different defining loader");

        Scenario otherMethod = new Scenario();
        inconsistent(otherMethod, () -> otherMethod.ledger.consumer(otherMethod.token,
                methodUnchecked("other"), otherMethod.consumer), "wrong Method");
        Scenario equalDifferent = new Scenario();
        Method another = method("valid");
        check(another.equals(equalDifferent.method), "same declared method equals");
        check(another != equalDifferent.method, "fixture has distinct Method references");
        inconsistent(equalDifferent, () -> equalDifferent.ledger.consumer(equalDifferent.token,
                another, equalDifferent.consumer), "nested Method must be identical");

        Scenario unknownToken = new Scenario();
        inconsistent(unknownToken, () -> unknownToken.ledger.consumer(new Object(), unknownToken.method,
                unknownToken.consumer), "unknown token");
        Scenario nullConsumer = new Scenario();
        inconsistent(nullConsumer, () -> nullConsumer.ledger.consumer(nullConsumer.token,
                nullConsumer.method, null), "null consumer");
        Scenario outOfOrder = new Scenario();
        inconsistent(outOfOrder, outOfOrder::register, "out of order");
        Scenario repeated = new Scenario(); repeated.captureConsumer();
        inconsistent(repeated, repeated::captureConsumer, "repeated consumer");
        Scenario badConsumer = new Scenario(); badConsumer.captureConsumer();
        inconsistent(badConsumer, () -> badConsumer.ledger.constructed(badConsumer.token,
                badConsumer.method, new Object(), badConsumer.function), "consumer identity");
        Scenario badFunction = new Scenario(); badFunction.captureConsumer(); badFunction.construct();
        inconsistent(badFunction, () -> badFunction.ledger.registered(badFunction.token,
                badFunction.method, new Object()), "function identity");
        Scenario noFunction = new Scenario(); noFunction.captureConsumer();
        inconsistent(noFunction, () -> noFunction.ledger.constructed(noFunction.token,
                noFunction.method, noFunction.consumer, null), "null function");
        Scenario missing = new Scenario(); missing.captureConsumer();
        inconsistent(missing, () -> missing.ledger.finish(missing.token), "missing stage at finish");
        Scenario selectionWrong = new Scenario(); selectionWrong.captureConsumer(); selectionWrong.construct(); selectionWrong.register();
        inconsistent(selectionWrong, () -> selectionWrong.ledger.selection(selectionWrong.token,
                new Object[] {new Object()}), "selection identity");
        Scenario selectionDuplicate = new Scenario(); selectionDuplicate.captureConsumer(); selectionDuplicate.construct(); selectionDuplicate.register();
        inconsistent(selectionDuplicate, () -> selectionDuplicate.ledger.selection(selectionDuplicate.token,
                new Object[] {selectionDuplicate.function, selectionDuplicate.function}), "selection cardinality");
        for (CallbackObservation before : CallbackObservation.values()) {
            for (CallbackObservation after : CallbackObservation.values()) {
                if (before == CallbackObservation.ABSENT && after == CallbackObservation.ABSENT) continue;
                Scenario s = new Scenario(); s.captureConsumer(); s.construct(); s.register(); s.select();
                inconsistent(s, () -> s.ledger.callbacks(s.token, before, after), "callbacks " + before + "/" + after);
            }
        }
        Scenario nullCallback = new Scenario(); nullCallback.captureConsumer(); nullCallback.construct(); nullCallback.register(); nullCallback.select();
        inconsistent(nullCallback, () -> nullCallback.ledger.callbacks(nullCallback.token, null,
                CallbackObservation.ABSENT), "null callback");
        Scenario aborted = new Scenario(); aborted.captureConsumer();
        inconsistent(aborted, () -> aborted.ledger.abort(aborted.token), "explicit abort");
        Scenario noFinish = new Scenario(); noFinish.captureConsumer();
        check(noFinish.ledger.status() == Status.INCOMPLETE, "missing completion remains incomplete");
        Scenario thread = new Scenario();
        AtomicReference<Throwable> error = new AtomicReference<>();
        Thread foreign = new Thread(() -> { try { thread.captureConsumer(); } catch (Throwable t) { error.set(t); } });
        foreign.start(); foreign.join();
        check(thread.ledger.status() == Status.INCONSISTENT, "foreign thread");
        tolerate(thread::complete);
        check(thread.ledger.status() == Status.INCONSISTENT, "foreign thread failure sticky");
        if (failures != 0) throw new AssertionError(failures + " of " + count + " checks failed");
        System.out.println("Passed " + count + " caller-reported ledger checks; no Forge or server started.");
    }
    private static Method methodUnchecked(String name) {
        try { return method(name); } catch (ReflectiveOperationException e) { throw new AssertionError(e); }
    }
}
