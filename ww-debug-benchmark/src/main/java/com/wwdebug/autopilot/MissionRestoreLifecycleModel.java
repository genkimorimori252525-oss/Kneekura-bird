package com.wwdebug.autopilot;

import java.util.Objects;

/**
 * Package-private, sequential model for synthetic restore-lifecycle experiments only.
 * Neither READY nor accepted is an authorization to load, save, control aircraft, or fire.
 * Evidence values are hypothetical inputs, not an attestation or a production integration.
 * Epochs do not repeat within one continuously retained state chain; fresh chains or JVM restarts
 * require separate identity design. Callers must pass the latest state in one sequential chain;
 * old states can be replayed. This class does not synchronize concurrent callers.
 */
final class MissionRestoreLifecycleModel {
    enum Phase { UNBOUND, RESTORING, UNKNOWN, READY, STOPPING }
    enum Source { VERIFIED_EXISTING, VERIFIED_NEW_WORLD, ABSENT_UNPROVEN, IO_FAILURE, UNVERIFIED }

    /** Opaque per-bind correlation token; it does not authenticate external evidence. */
    static final class Token {
        private final Object serverIdentity;
        private final long epoch;

        private Token(Object serverIdentity, long epoch) {
            this.serverIdentity = serverIdentity;
            this.epoch = epoch;
        }

        long epoch() { return epoch; }
    }

    static final class State {
        private final Phase phase;
        private final Token token;
        private final long lastEpoch;

        private State(Phase phase, Token token, long lastEpoch) {
            this.phase = phase;
            this.token = token;
            this.lastEpoch = lastEpoch;
        }

        Phase phase() { return phase; }
        Token token() { return token; }
    }

    /** Accepted describes a model transition only; it grants no operational permission. */
    record Transition(State state, boolean accepted) { }

    /** All members are synthetic test assumptions, not independently verified evidence. */
    record StoreEvidence(Object serverIdentity, Token token, Source source,
                         boolean diagnosticClean, boolean dataFixerVerified,
                         boolean cacheOwned, boolean writerExclusive,
                         boolean stableSnapshot, boolean restored) {
        boolean complete(Object expectedServer, Token expectedToken) {
            return serverIdentity == expectedServer && token == expectedToken
                    && (source == Source.VERIFIED_EXISTING || source == Source.VERIFIED_NEW_WORLD)
                    && diagnosticClean && dataFixerVerified && cacheOwned && writerExclusive
                    && stableSnapshot && restored;
        }
    }

    record SyntheticEvidence(StoreEvidence mission, StoreEvidence route, boolean routeMatchesMission) {
        boolean complete(Object expectedServer, Token expectedToken) {
            return mission != null && mission.complete(expectedServer, expectedToken)
                    && route != null && route.complete(expectedServer, expectedToken) && routeMatchesMission;
        }
    }

    private MissionRestoreLifecycleModel() { }

    static State initial() {
        return new State(Phase.UNBOUND, null, 0L);
    }

    /** Used only for bounded counter tests; not a restore or persistence API. */
    static State initialForTesting(long lastEpoch) {
        if (lastEpoch < 0) throw new IllegalArgumentException("negative model epoch");
        return new State(Phase.UNBOUND, null, lastEpoch);
    }

    static Transition begin(State state, Object serverIdentity) {
        Objects.requireNonNull(state, "state");
        Objects.requireNonNull(serverIdentity, "serverIdentity");
        if (state.phase != Phase.UNBOUND || state.lastEpoch == Long.MAX_VALUE) {
            return rejected(state);
        }
        long epoch = state.lastEpoch + 1;
        return accepted(new State(Phase.RESTORING, new Token(serverIdentity, epoch), epoch));
    }

    static Transition complete(State state, Object serverIdentity, Token token, SyntheticEvidence evidence) {
        if (!matches(state, serverIdentity, token) || state.phase != Phase.RESTORING) {
            return rejected(state);
        }
        Phase phase = evidence != null && evidence.complete(serverIdentity, token) ? Phase.READY : Phase.UNKNOWN;
        return accepted(new State(phase, state.token, state.lastEpoch));
    }

    static Transition invalidate(State state, Object serverIdentity, Token token) {
        if (!matches(state, serverIdentity, token) || (state.phase != Phase.RESTORING && state.phase != Phase.READY)) {
            return rejected(state);
        }
        return accepted(new State(Phase.UNKNOWN, state.token, state.lastEpoch));
    }

    static Transition stop(State state, Object serverIdentity, Token token) {
        if (!matches(state, serverIdentity, token) || (state.phase != Phase.RESTORING
                && state.phase != Phase.READY && state.phase != Phase.UNKNOWN)) {
            return rejected(state);
        }
        return accepted(new State(Phase.STOPPING, state.token, state.lastEpoch));
    }

    static Transition finishStop(State state, Object serverIdentity, Token token) {
        if (!matches(state, serverIdentity, token) || state.phase != Phase.STOPPING) {
            return rejected(state);
        }
        return accepted(new State(Phase.UNBOUND, null, state.lastEpoch));
    }

    private static boolean matches(State state, Object serverIdentity, Token token) {
        Objects.requireNonNull(state, "state");
        return token != null && state.token == token
                && token.serverIdentity == serverIdentity;
    }

    private static Transition accepted(State state) { return new Transition(state, true); }
    private static Transition rejected(State state) { return new Transition(state, false); }
}
