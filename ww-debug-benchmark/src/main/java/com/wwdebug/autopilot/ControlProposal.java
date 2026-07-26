package com.wwdebug.autopilot;

import com.wwdebug.autopilot.ControlAuthorityArbiter.Authority;
import net.minecraft.util.Mth;

/**
 * One layer's bid to fly the aircraft this tick.
 *
 * <p>Today every control layer writes straight to the aircraft, seven of them in fixed statement
 * order, and whichever runs last wins. Priority is therefore an emergent property of the order the
 * calls happen to appear in — adding a bomber or damage authority means inserting a statement at
 * the right index and hoping.</p>
 *
 * <p>A proposal separates <em>deciding</em> from <em>writing</em>. A layer says what it wants and
 * why; the arbiter picks the highest authority and performs the single write. Nothing produces
 * proposals yet — the writers are converted one at a time in later changes.</p>
 *
 * @param authority    the layer's position in the priority stack
 * @param x            final roll input, already sign-corrected by the producer
 * @param y            final pitch input
 * @param z            final yaw input
 * @param engineTarget final engine target, 0..1
 * @param reason       short machine-readable cause, carried into telemetry
 */
public record ControlProposal(Authority authority, float x, float y, float z,
                              float engineTarget, String reason) {

    public ControlProposal {
        if (authority == null || authority == Authority.NONE) {
            throw new IllegalArgumentException(
                    "a proposal must name a real authority; use Optional.empty() to abstain");
        }
        // The same clamps FlightControlOutput applies. A proposal may be built from raw floats by
        // a layer that has no FlightControlOutput, so the guarantee has to hold here too.
        x = Mth.clamp(x, -1.0f, 1.0f);
        y = Mth.clamp(y, -1.0f, 1.0f);
        z = Mth.clamp(z, -1.0f, 1.0f);
        engineTarget = Mth.clamp(engineTarget, 0.0f, 1.0f);
        reason = reason == null || reason.isBlank() ? "unspecified" : reason;
    }

    /**
     * Builds a proposal from a computed flight output, applying the roll-sign correction every
     * guidance layer performs today.
     *
     * <p>Six of the seven production writers pass {@code -output.x()} and the remaining one
     * ({@code BenchmarkManager}) passes its stored input unnegated. Putting the negation here, in
     * the path the guidance layers use, keeps that asymmetry from being re-derived — and
     * misremembered — at each call site.</p>
     */
    public static ControlProposal fromGuidance(Authority authority, FlightControlOutput output) {
        return new ControlProposal(authority, -output.x(), output.y(), output.z(),
                output.engineTarget(), output.reason());
    }

    /** Builds a proposal from already-final inputs, with no sign correction. */
    public static ControlProposal ofRawInputs(Authority authority, float x, float y, float z,
                                              float engineTarget, String reason) {
        return new ControlProposal(authority, x, y, z, engineTarget, reason);
    }

    /** Whether this proposal beats {@code other}. A null loses; equal authorities keep the incumbent. */
    public boolean outranks(ControlProposal other) {
        return other == null || authority.outranks(other.authority());
    }
}
