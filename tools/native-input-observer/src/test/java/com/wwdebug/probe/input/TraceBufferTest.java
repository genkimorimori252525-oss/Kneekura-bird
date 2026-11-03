package com.wwdebug.probe.input;

import java.util.List;
import java.util.concurrent.CountDownLatch;

/** JDK-only contract; it does not simulate Forge or prove mixin application. */
public final class TraceBufferTest {
    private static TraceBuffer.Sample event(TraceBuffer.Point point, String caller, boolean truncated) {
        return new TraceBuffer.Sample(point, 2, 3, 4, "server", "fake_server_player", false,
                new TraceBuffer.Axes(1, 2, 3),
                point == TraceBuffer.Point.SET_HEAD || point == TraceBuffer.Point.SET_RETURN
                        ? new TraceBuffer.Axes(1, 2, 3) : null,
                4, caller, caller == null ? List.of() : List.of(caller), truncated, null);
    }
    public static void main(String[] args) throws Exception {
        TraceBuffer good = new TraceBuffer(16);
        good.mark(1, 1, 1, "setup");
        good.record(event(TraceBuffer.Point.TICK_HEAD, null, false));
        good.record(event(TraceBuffer.Point.SET_HEAD, "native_tick_pilot", false));
        good.record(event(TraceBuffer.Point.SET_RETURN, "native_tick_pilot", false));
        good.record(event(TraceBuffer.Point.TICK_TAIL, null, false));
        TraceBuffer.Report r = good.close();
        check(r.ready(), "balanced positive including same-value setter and boundary");
        check(r.events().size() == 5 && r.events().get(0).sequence() == 1
                && r.events().get(4).sequence() == 5, "one sequence for hooks and boundary");
        check(r.events().get(2).sample().axes().equals(r.events().get(2).sample().arguments()), "same-value recorded");
        check(!new TraceBuffer(8).close().ready(), "no hooks is not success");
        TraceBuffer different = new TraceBuffer(8);
        different.mark(1, 1, 1, "boundary");
        different.record(event(TraceBuffer.Point.TICK_HEAD, null, false));
        var changed = new TraceBuffer.Sample(TraceBuffer.Point.SET_HEAD, 2, 3, 4, "server", "none", null,
                new TraceBuffer.Axes(0, 0, 0), new TraceBuffer.Axes(1, 2, 3), 4, "other", List.of("other"), false, null);
        different.record(changed);
        different.record(event(TraceBuffer.Point.SET_RETURN, "other", false));
        different.record(event(TraceBuffer.Point.TICK_TAIL, null, false));
        check(!different.close().ready(), "different-value setter is not same-value positive control");
        try { new TraceBuffer.Sample(TraceBuffer.Point.TICK_HEAD, 1, 1, 1, "server", "none", null,
                null, null, null, null, java.util.Collections.nCopies(9, "frame"), false, null);
            throw new AssertionError("unbounded frames");
        } catch (IllegalArgumentException expected) { }
        TraceBuffer unknown = new TraceBuffer(8);
        unknown.record(event(TraceBuffer.Point.SET_HEAD, "unknown", false));
        check(!unknown.close().ready() && unknown.snapshot().unknownCallers() == 1, "unknown differs from zero calls");
        TraceBuffer clipped = new TraceBuffer(8);
        clipped.record(event(TraceBuffer.Point.SET_HEAD, "other", true));
        check(clipped.snapshot().truncatedStacks() == 1 && !clipped.close().ready(), "stack truncation invalidates");
        TraceBuffer mismatch = new TraceBuffer(8);
        mismatch.record(event(TraceBuffer.Point.SET_RETURN, "other", false));
        check(!mismatch.close().ready() && mismatch.snapshot().unmatched() > 0, "unmatched return invalidates");
        TraceBuffer overflow = new TraceBuffer(1);
        overflow.mark(1, 1, 1, "one"); overflow.mark(1, 1, 1, "two");
        check(!overflow.close().ready() && overflow.snapshot().dropped() == 1, "overflow invalidates");
        TraceBuffer error = new TraceBuffer(4);
        error.error("observer_exception");
        check(error.snapshot().errors() == 1 && !error.close().ready(), "errors invalidate");
        try { new TraceBuffer(0); throw new AssertionError("zero capacity"); }
        catch (IllegalArgumentException expected) { }
        TraceBuffer threads = new TraceBuffer(512);
        CountDownLatch start = new CountDownLatch(1);
        Runnable worker = () -> { try { start.await(); } catch (InterruptedException e) { throw new RuntimeException(e); }
            for (int i = 0; i < 100; i++) threads.mark(1, 1, 1, "marker"); };
        Thread a = new Thread(worker), b = new Thread(worker); a.start(); b.start(); start.countDown(); a.join(); b.join();
        var tr = threads.close();
        check(tr.events().size() == 200 && tr.dropped() == 0, "concurrent markers retained");
        for (int i = 0; i < tr.events().size(); i++) check(tr.events().get(i).sequence() == i + 1, "ordered sequence");
        System.out.println("TraceBufferTest PASS");
    }
    private static void check(boolean condition, String message) { if (!condition) throw new AssertionError(message); }
}
