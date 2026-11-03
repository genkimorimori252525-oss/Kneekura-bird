package com.wwdebug.probe.input;

import immersive_aircraft.entity.EngineVehicle;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.gametest.framework.GameTestServer;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.player.Player;
import net.minecraftforge.common.util.FakePlayer;

import java.lang.StackWalker.StackFrame;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.UUID;

/** Explicitly armed, fixed-version GameTest observer. It never writes vehicle state. */
public final class NativeInputObserver {
    private static final String FLAG = "wwdebug.nativeInputObserver";
    private static final String VEHICLE = "immersive_aircraft.entity.VehicleEntity";
        private static final StackWalker WALKER = StackWalker.getInstance(StackWalker.Option.SHOW_REFLECT_FRAMES);
    private static Scope scope;

    private NativeInputObserver() { }

    private record Scope(UUID runToken, UUID aircraftId, Entity aircraft, ServerLevel level,
                         MinecraftServer server, Thread thread, String dimension, UUID negativeId, Entity negative, TraceBuffer buffer) { }
    public record ObservationReport(UUID runToken, UUID aircraftId, UUID negativeId, String dimension, TraceBuffer.Report trace) { }

    /** Called by an isolated fixture before the target's observed tick. */
    public static synchronized void arm(UUID runToken, ServerLevel level, UUID aircraftId,
                                        Entity aircraft, UUID negativeId, Entity negative, int capacity) {
        if (scope != null) throw new IllegalStateException("observer already armed");
        if (!"enabled".equals(System.getProperty(FLAG))) throw new IllegalStateException("observer opt-in absent");
        if (runToken == null || level == null || aircraftId == null || aircraft == null || negativeId == null || negative == null)
            throw new IllegalArgumentException("missing observer identity");
        MinecraftServer server = level.getServer();
        if (!(server instanceof GameTestServer) || !server.isSameThread() || level.isClientSide
                || aircraft.level() != level || aircraft.isRemoved() || !aircraftId.equals(aircraft.getUUID())
                || !"warfare_wings:d4y".equals(String.valueOf(BuiltInRegistries.ENTITY_TYPE.getKey(aircraft.getType())))
                || !(aircraft instanceof EngineVehicle) || negative == aircraft || negativeId.equals(aircraftId)
                || negative.level() != level || negative.isRemoved() || !negativeId.equals(negative.getUUID())
                || !(negative instanceof EngineVehicle)
                || !"warfare_wings:d4y".equals(String.valueOf(BuiltInRegistries.ENTITY_TYPE.getKey(negative.getType())))) {
            throw new IllegalStateException("observer requires the exact D4Y on the GameTest server thread");
        }
        scope = new Scope(runToken, aircraftId, aircraft, level, server, Thread.currentThread(), level.dimension().location().toString(), negativeId, negative, new TraceBuffer(capacity));
    }

    /** A fixture boundary shares the hook sequence. Labels are restricted and never written to disk here. */
    public static synchronized void mark(UUID runToken, String label) {
        Scope s = requireScope(runToken);
        if (Thread.currentThread() != s.thread()) { s.buffer().error("boundary_wrong_thread"); return; }
        try {
            if (!validContext(s)) { s.buffer().error("boundary_context_changed"); return; }
            s.buffer().mark(s.server().getTickCount(), s.level().getGameTime(), s.aircraft().tickCount, label);
        } catch (Throwable ignored) { s.buffer().error("boundary_exception"); }
    }

    /** The fixture must check ready() and preserve the report; non-disarm is not a successful observation. */
    public static synchronized ObservationReport disarm(UUID runToken) {
        Scope s = requireScope(runToken);
        if (Thread.currentThread() != s.thread()) {
            s.buffer().error("disarm_wrong_thread");
            throw new IllegalStateException("observer disarm must use the armed server thread");
        }
        TraceBuffer.Report report = s.buffer().close();
        scope = null;
        return new ObservationReport(s.runToken(), s.aircraftId(), s.negativeId(), s.dimension(), report);
    }

    public static synchronized boolean isArmed() { return scope != null; }

    private static Scope requireScope(UUID token) {
        if (scope == null || token == null || !token.equals(scope.runToken()))
            throw new IllegalStateException("observer scope/token mismatch");
        return scope;
    }

    private static boolean validContext(Scope s) {
        return "enabled".equals(System.getProperty(FLAG)) && s.level().getServer() == s.server()
                && s.server() instanceof GameTestServer && !s.level().isClientSide
                && s.aircraft().level() == s.level() && !s.aircraft().isRemoved()
                && s.aircraftId().equals(s.aircraft().getUUID())
                && "warfare_wings:d4y".equals(String.valueOf(BuiltInRegistries.ENTITY_TYPE.getKey(s.aircraft().getType())));
    }

    /** Called only by non-cancellable mixin callbacks; failures are retained and never thrown outward. */
    public static synchronized void capture(Entity aircraft, TraceBuffer.Point point,
                                     float x, float y, float z, Float ax, Float ay, Float az) {
        Scope s = scope;
        if (s == null) return;
        try {
            if (aircraft != s.aircraft() && aircraft != s.negative()) {
                if (aircraft != null && (s.aircraftId().equals(aircraft.getUUID()) || s.negativeId().equals(aircraft.getUUID())))
                    s.buffer().error("uuid_identity_collision");
                return;
            }
            if (Thread.currentThread() != s.thread()) { s.buffer().error("hook_wrong_thread"); return; }
            if (!validContext(s)) { s.buffer().error("hook_context_changed"); return; }
            if (aircraft == s.negative()) {
                if (aircraft.level() != s.level() || aircraft.isRemoved() || !s.negativeId().equals(aircraft.getUUID())) {
                    s.buffer().error("negative_context_changed"); return;
                }
                s.buffer().excluded(s.server().getTickCount(), s.level().getGameTime(), aircraft.tickCount, point);
                return;
            }
            Entity pilot = aircraft.getControllingPassenger();
            String kind = pilot instanceof FakePlayer ? "fake_server_player"
                    : pilot instanceof ServerPlayer ? "server_player"
                    : pilot instanceof Player ? "other_player"
                    : pilot == null ? "none" : "non_player";
            Boolean local = pilot instanceof Player player ? player.isLocalPlayer() : null;
            boolean setter = point == TraceBuffer.Point.SET_HEAD || point == TraceBuffer.Point.SET_RETURN;
            TraceBuffer.Caller caller = setter ? caller() : new TraceBuffer.Caller(null, List.of(), false);
            TraceBuffer.Axes args = setter ? axes(ax, ay, az) : null;
            int engineBits = Float.floatToRawIntBits(((EngineVehicle) aircraft).getEngineTarget());
            s.buffer().record(new TraceBuffer.Sample(point, s.server().getTickCount(), s.level().getGameTime(),
                    aircraft.tickCount, "server", kind, local, axes(x, y, z), args, engineBits,
                    caller.classification(), caller.frames(), caller.truncated(), null));
        } catch (Throwable ignored) {
            try { s.buffer().error("hook_exception"); } catch (Throwable ignoredAgain) { /* external evidence fails closed */ }
        }
    }

    public static synchronized void hookFailure() {
        try { if (scope != null) scope.buffer().error("mixin_callback_exception"); }
        catch (Throwable ignored) { /* the fixture must require a complete report */ }
    }

    private static TraceBuffer.Axes axes(float x, float y, float z) {
        return new TraceBuffer.Axes(Float.floatToRawIntBits(x), Float.floatToRawIntBits(y), Float.floatToRawIntBits(z));
    }

    /** Scans up to 128 callers; stores only the first relevant and first benchmark frame. */
    private static TraceBuffer.Caller caller() {
        return WALKER.walk(stream -> {
            Iterator<StackFrame> frames = stream.iterator();
            boolean setter = false;
            int skipped = 0;
            while (frames.hasNext() && skipped++ < 32) {
                StackFrame f = frames.next();
                if (f.getClassName().equals(VEHICLE) && f.getMethodName().equals("setInputs")) {
                    setter = true; break;
                }
            }
            if (!setter) return new TraceBuffer.Caller("unknown", List.of(), frames.hasNext());
            List<String> observed = new ArrayList<>();
            while (frames.hasNext() && observed.size() < 128) {
                StackFrame f = frames.next();
                String frame = f.getClassName() + "#" + f.getMethodName();
                if (frame.length() > 256) return new TraceBuffer.Caller("unknown", List.of(), true);
                observed.add(frame);
            }
            return TraceBuffer.classifyCaller(observed, frames.hasNext());
        });
    }
}
