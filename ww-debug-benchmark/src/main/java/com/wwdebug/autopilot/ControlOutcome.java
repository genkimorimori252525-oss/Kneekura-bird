package com.wwdebug.autopilot;

import com.wwdebug.autopilot.ControlAuthorityArbiter.Authority;

import java.util.Optional;

/**
 * What a control layer did with a tick, during the conversion to proposals.
 *
 * <p>Seven layers write straight to the aircraft today and are converted one at a time. Until that
 * finishes, a layer either <em>proposed</em> — decided without writing, leaving the write to the
 * arbiter — or <em>already wrote</em>, the old behaviour. This type makes that difference explicit
 * so the remaining work is visible to the compiler rather than tracked in someone's head.</p>
 *
 * <p>{@link #alreadyWrote(Authority)} is deliberately awkward to read. Every remaining use of it is
 * a layer still to convert, and it disappears when the last one lands.</p>
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
     * An unconverted layer has already written to the aircraft itself.
     *
     * <p>The arbiter must not write again for this tick — it only records who owned it.</p>
     */
    public static ControlOutcome alreadyWrote(Authority authority) {
        return new ControlOutcome(authority, null);
    }

    public boolean claimed() {
        return authority != Authority.NONE;
    }

    /** The write the arbiter still owes, if any. Empty when the layer wrote for itself. */
    public Optional<ControlProposal> pendingWrite() {
        return Optional.ofNullable(proposal);
    }
}
