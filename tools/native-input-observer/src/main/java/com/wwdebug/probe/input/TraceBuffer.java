package com.wwdebug.probe.input;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.List;

/** Bounded, thread-safe evidence buffer. A closed report is not a flight verdict. */
public final class TraceBuffer {
    public enum Point { TICK_HEAD, TICK_TAIL, SET_HEAD, SET_RETURN, BOUNDARY, EXCLUDED }
    /** Raw float bits preserve NaN payloads and signed zero. */
    public record Axes(int x, int y, int z) { }
    public record Sample(Point point, int serverTick, long gameTime, int entityTick, String side,
                         String pilot, Boolean local, Axes axes, Axes arguments, Integer engineBits,
                         String caller, List<String> frames, boolean truncated, String label) {
        public Sample {
            if (frames == null || frames.size() > 8 || frames.stream().anyMatch(f -> f == null || f.length() > 256))
                throw new IllegalArgumentException("unbounded frames");
            frames = List.copyOf(frames);
        }
    }
    public record Event(long sequence, Sample sample) { }
    public record Report(List<Event> events, boolean closed, long dropped, long errors,
                         long unknownCallers, long truncatedStacks, long unmatched,
                         long tickHeads, long tickTails, long setterHeads, long setterReturns,
                         long boundaries, long excludedHooks, long sameValueCompleted, boolean saturated, String lastError) {
        /** Positive hook hits, matching returns and no lost observations; not a safety verdict. */
        public boolean ready() {
            return closed && !saturated && dropped == 0 && errors == 0 && unknownCallers == 0
                    && truncatedStacks == 0 && unmatched == 0 && tickHeads > 0 && tickTails > 0
                    && setterHeads > 0 && setterReturns > 0 && boundaries > 0 && sameValueCompleted > 0;
        }
    }

    private final Event[] events;
    private final Deque<Sample> openings = new ArrayDeque<>();
    private int size;
    private long sequence, dropped, errors, unknown, truncated, unmatched;
    private long tickHeads, tickTails, setterHeads, setterReturns, boundaries, excludedHooks, sameValueCompleted;
    private boolean closed, saturated;
    private String lastError = "none";

    public TraceBuffer(int capacity) {
        if (capacity < 1 || capacity > 4096) throw new IllegalArgumentException("capacity out of bounds");
        events = new Event[capacity];
    }

    public synchronized void mark(int serverTick, long gameTime, int entityTick, String label) {
        if (label == null || !label.matches("[a-zA-Z0-9_.-]{1,48}")) {
            error("invalid_boundary_label");
            return;
        }
        record(new Sample(Point.BOUNDARY, serverTick, gameTime, entityTick, "server", "not_sampled",
                null, null, null, null, null, List.of(), false, label));
    }

    /** Explicitly registered negative-control hook; never included in target hook counts. */
    public synchronized void excluded(int serverTick, long gameTime, int entityTick, Point hook) {
        if (hook != Point.TICK_HEAD && hook != Point.TICK_TAIL && hook != Point.SET_HEAD && hook != Point.SET_RETURN) {
            error("invalid_excluded_hook"); return;
        }
        record(new Sample(Point.EXCLUDED, serverTick, gameTime, entityTick, "server", "not_sampled",
                null, null, null, null, null, List.of(), false, hook.name()));
    }

    /** Scans a bounded complete caller suffix; benchmark evidence takes precedence. */
    public record Caller(String classification, List<String> frames, boolean truncated) { }
    public static Caller classifyCaller(List<String> frames, boolean truncated) {
        if (frames == null || frames.size() > 128) return new Caller("unknown", List.of(), true);
        String first = null, benchmark = null;
        for (String frame : frames) {
            if (frame == null || frame.length() > 256) return new Caller("unknown", List.of(), true);
            if (frame.startsWith("com.wwdebug.benchmark.") && benchmark == null) benchmark = frame;
            if (first == null && !frame.startsWith("java.lang.reflect.") && !frame.startsWith("jdk.internal.reflect.")) first = frame;
        }
        List<String> evidence = new ArrayList<>();
        if (first != null) evidence.add(first);
        if (benchmark != null && !benchmark.equals(first)) evidence.add(benchmark);
        // A benchmark frame can be an outer fixture caller, not the setter's writer.
        String kind = "unknown";
        if (!truncated && first != null) {
            if (first.startsWith("com.wwdebug.benchmark.")) kind = "benchmark_direct_context";
            else if ("immersive_aircraft.entity.VehicleEntity#tickPilot".equals(first))
                kind = benchmark != null ? "native_with_benchmark_context" : "native_tick_pilot";
        }
        return new Caller(kind, List.copyOf(evidence), truncated);
    }

    public synchronized void record(Sample sample) {
        if (closed) { error("record_after_close"); return; }
        if (sample == null || sample.point() == null) { error("invalid_sample"); return; }
        if (sequence == Long.MAX_VALUE) { saturated = true; return; }
        sequence++;
        switch (sample.point()) {
            case TICK_HEAD -> { tickHeads = increment(tickHeads); push(sample); }
            case TICK_TAIL -> { tickTails = increment(tickTails); pop(Point.TICK_HEAD, sample); }
            case SET_HEAD -> { setterHeads = increment(setterHeads); caller(sample); push(sample); }
            case SET_RETURN -> { setterReturns = increment(setterReturns); caller(sample); pop(Point.SET_HEAD, sample); }
            case BOUNDARY -> boundaries = increment(boundaries);
            case EXCLUDED -> excludedHooks = increment(excludedHooks);
        }
        if (size == events.length) { dropped = increment(dropped); return; }
        events[size++] = new Event(sequence, sample);
    }

    private void caller(Sample sample) {
        if (!"native_tick_pilot".equals(sample.caller()) && !"native_with_benchmark_context".equals(sample.caller())
                && !"benchmark_direct_context".equals(sample.caller())) unknown = increment(unknown);
        if (sample.truncated()) truncated = increment(truncated);
    }
    private void push(Sample sample) {
        if (openings.size() == events.length) { unmatched = increment(unmatched); return; }
        openings.push(sample);
    }
    private void pop(Point expected, Sample end) {
        if (openings.isEmpty() || openings.peek().point() != expected) { unmatched = increment(unmatched); return; }
        Sample start = openings.pop();
        if (expected == Point.SET_HEAD) {
            if (start.arguments() == null || !start.arguments().equals(end.arguments())) { unmatched = increment(unmatched); return; }
            if (start.arguments().equals(start.axes())) sameValueCompleted = increment(sameValueCompleted);
        }
    }
    private long increment(long value) {
        if (value == Long.MAX_VALUE) { saturated = true; return value; }
        return value + 1;
    }
    public synchronized void error(String reason) {
        errors = increment(errors);
        lastError = reason == null ? "unknown" : reason.substring(0, Math.min(reason.length(), 80));
    }
    public synchronized Report snapshot() {
        List<Event> copy = new ArrayList<>(size);
        for (int i = 0; i < size; i++) copy.add(events[i]);
        long open = openings.size();
        long unmatchedTotal = unmatched > Long.MAX_VALUE - open ? Long.MAX_VALUE : unmatched + open;
        return new Report(List.copyOf(copy), closed, dropped, errors, unknown, truncated, unmatchedTotal,
                tickHeads, tickTails, setterHeads, setterReturns, boundaries, excludedHooks, sameValueCompleted, saturated, lastError);
    }
    public synchronized Report close() { closed = true; return snapshot(); }
}
