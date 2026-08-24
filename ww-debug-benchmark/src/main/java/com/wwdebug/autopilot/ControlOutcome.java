package com.wwdebug.autopilot;

import com.wwdebug.autopilot.ControlAuthorityArbiter.Authority;

import java.util.Optional;

/**
 * What a control layer did with a tick, during the conversion to proposals.
 *
 * <p>During the migration a layer can either <em>propose</em> — decide without writing and leave
 * the write to the arbiter — or claim the tick without a pending proposal. The latter covers both
 * a legacy layer that already wrote and a converted state machine that deliberately retains
 * ownership while producing no control output for this tick.</p>
 */
public record ControlOutcome(Authority authority, ControlProposal proposal) {

    private static final ControlOutcome NONE = new ControlOutcome(Authority.NONE, null);

    public ControlOutcome {
        if (authority == null) {
            throw new IllegalArgumentException("a control outcome must name an authority");
        }
        if (proposal != null && proposal.authority() != authority) {
            throw new IllegalArgumentException(
                    "outcome authority " + authority + " disagrees with proposal authority "
                            + proposal.authority());
        }
    }

    /** No layer claimed the tick. */
    public static ControlOutcome none() {
        return NONE;
    }

    /** A converted layer decided without writing; the arbiter performs the write. */
    public static ControlOutcome proposed(ControlProposal proposal) {
        return new ControlOutcome(proposal.authority(), proposal);
    }

    /**
     * A layer owns the tick but intentionally has no control proposal to write.
     *
     * <p>This is distinct from {@link #none()}: lower-priority layers must still remain suppressed.
     */
    public static ControlOutcome claimedWithoutProposal(Authority authority) {
        if (authority == null || authority == Authority.NONE) {
            throw new IllegalArgumentException("a claimed outcome must name a real authority");
        }
        return new ControlOutcome(authority, null);
    }

    /**
     * A legacy unconverted layer has already written to the aircraft itself.
     *
     * <p>Kept while lower layers are still being migrated. Converted layers that retain ownership
     * without producing output should use {@link #claimedWithoutProposal(Authority)} instead.</p>
     */
    public static ControlOutcome alreadyWrote(Authority authority) {
        return claimedWithoutProposal(authority);
    }

    public boolean claimed() {
        return authority != Authority.NONE;
    }

    /** The write the arbiter still owes, if any. */
    public Optional<ControlProposal> pendingWrite() {
        return Optional.ofNullable(proposal);
    }
}
