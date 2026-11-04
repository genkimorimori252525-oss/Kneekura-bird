package com.wwdebug.gametestprobe;

import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.Objects;

/**
 * A one-shot consistency check for caller-reported observations only.
 * CONSISTENT does not authenticate the caller, a registration, or a class and
 * does not authorize starting a server or a GameTest. No event is intercepted here.
 */
public final class RegistrationCaptureLedger {
    public enum Status { INCOMPLETE, INCONSISTENT, CONSISTENT }
    public enum CallbackObservation { UNKNOWN, ABSENT, PRESENT }

    private final Method expected;
    private final Thread owner = Thread.currentThread();
    private final Object token = new Object();
    private Status status = Status.INCOMPLETE;
    private int stage;
    private Method observed;
    private Object capturedConsumer;
    private Object capturedFunction;
    private String reason;

    /** The supplied class and argument type must be independently established by the caller. */
    public RegistrationCaptureLedger(Class<?> declaringClass, String methodName, Class<?> argumentType) {
        Objects.requireNonNull(declaringClass, "declaringClass");
        Objects.requireNonNull(methodName, "methodName");
        Objects.requireNonNull(argumentType, "argumentType");
        try {
            expected = declaringClass.getDeclaredMethod(methodName, argumentType);
        } catch (NoSuchMethodException exception) {
            throw new IllegalArgumentException("expected method not found", exception);
        }
        int modifiers = expected.getModifiers();
        if (expected.getDeclaringClass() != declaringClass || expected.getReturnType() != void.class
                || !Modifier.isPublic(modifiers) || !Modifier.isStatic(modifiers)) {
            throw new IllegalArgumentException("expected method is not public static void");
        }
    }

    public synchronized Object begin(Method method) {
        if (status != Status.INCOMPLETE || stage != 0 || Thread.currentThread() != owner
                || !expected.equals(method)) {
            reject("invalid begin");
            return null;
        }
        observed = method;
        stage = 1;
        return token;
    }

    public synchronized void consumer(Object receipt, Method method, Object consumer) {
        if (!ready(receipt, 1) || method != observed || consumer == null) {
            reject("invalid consumer observation");
            return;
        }
        capturedConsumer = consumer;
        stage = 2;
    }

    public synchronized void constructed(Object receipt, Method method, Object consumer, Object function) {
        if (!ready(receipt, 2) || method != observed || consumer != capturedConsumer || function == null) {
            reject("invalid construction observation");
            return;
        }
        capturedFunction = function;
        stage = 3;
    }

    public synchronized void registered(Object receipt, Method method, Object function) {
        if (!ready(receipt, 3) || method != observed || function != capturedFunction) {
            reject("invalid registration observation");
            return;
        }
        stage = 4;
    }

    public synchronized void selection(Object receipt, Object[] functions) {
        if (!ready(receipt, 4) || functions == null || functions.length != 1
                || functions[0] != capturedFunction) {
            reject("invalid selection observation");
            return;
        }
        stage = 5;
    }

    public synchronized void callbacks(Object receipt, CallbackObservation before, CallbackObservation after) {
        if (!ready(receipt, 5) || before != CallbackObservation.ABSENT || after != CallbackObservation.ABSENT) {
            reject("callbacks are present or not observed absent");
            return;
        }
        stage = 6;
    }

    public synchronized void finish(Object receipt) {
        if (!ready(receipt, 6)) {
            reject("incomplete or invalid finish");
            return;
        }
        status = Status.CONSISTENT;
        stage = 7;
    }

    /** Report an incomplete or failed capture; no subsequent event can restore consistency. */
    public synchronized void abort(Object receipt) {
        reject(receipt == token && Thread.currentThread() == owner ? "capture aborted" : "invalid abort");
    }

    public synchronized Status status() { return status; }

    /** A stable reason code for the first inconsistency, or null if none was observed. */
    public synchronized String reason() { return reason; }

    private boolean ready(Object receipt, int expectedStage) {
        return status == Status.INCOMPLETE && stage == expectedStage
                && receipt == token && Thread.currentThread() == owner;
    }

    private void reject(String why) {
        status = Status.INCONSISTENT;
        if (reason == null) reason = why;
    }
}
