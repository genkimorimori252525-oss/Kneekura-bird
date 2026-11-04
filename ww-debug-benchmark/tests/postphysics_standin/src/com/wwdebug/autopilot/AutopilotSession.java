package com.wwdebug.autopilot;
import net.minecraft.world.phys.Vec3;
final class AutopilotSession {
    private Vec3 runwayForward;
    private FlightPhase phase;
    private int phaseTicks;
    private String transitionReason;
    private final FlightProfile profile;
    AutopilotSession(FlightPhase phase, FlightProfile profile) { this.phase = phase; this.profile = profile; }
    FlightPhase phase() { return phase; }
    FlightProfile profile() { return profile; }
}

/** Minimal profile stand-in used only by this isolated direct-call fixture. */
final class FlightProfile {
    private final Double lead;
    private final double top;
    FlightProfile(Double lead, double top) { this.lead = lead; this.top = top; }
    public Double brakeLeadBlocks() { return lead; }
    public double measuredTopSpeedBps() { return top; }
}
