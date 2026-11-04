package com.wwdebug.autopilot;

import static com.wwdebug.autopilot.MissionRestoreLifecycleModel.*;

/** Standalone sequential contract checks; no server, NBT, file or control APIs. */
public final class MissionRestoreLifecycleModelChecks {
    private MissionRestoreLifecycleModelChecks() { }

    public static void main(String[] args) {
        String scenario = args[0];
        Object server = new Object();
        State initial = initial();
        switch (scenario) {
            case "ready-existing", "ready-new" -> {
                State loading = accepted(begin(initial, server), Phase.RESTORING);
                Source source = scenario.equals("ready-existing") ? Source.VERIFIED_EXISTING : Source.VERIFIED_NEW_WORLD;
                State ready = accepted(complete(loading, server, loading.token(), evidence(server, loading.token(), source)), Phase.READY);
                check(ready.token() == loading.token(), "READY must retain the exact epoch token");
            }
            case "absent", "io", "unknown-source", "clean-alone", "missing-diagnostic", "missing-datafix",
                    "missing-cache", "missing-writer", "missing-stability", "missing-restore",
                    "route-absent", "route-io", "route-diagnostic", "route-datafix", "route-cache",
                    "route-writer", "route-stability", "route-restore", "route-mismatch", "route-null" -> {
                State loading = accepted(begin(initial, server), Phase.RESTORING);
                SyntheticEvidence e = switch (scenario) {
                    case "absent" -> evidence(server, loading.token(), Source.ABSENT_UNPROVEN);
                    case "io" -> evidence(server, loading.token(), Source.IO_FAILURE);
                    case "unknown-source" -> evidence(server, loading.token(), Source.UNVERIFIED);
                    case "clean-alone" -> missionAssumptions(server, loading.token(), Source.UNVERIFIED, true, false, false, false, false, false);
                    case "missing-diagnostic" -> missionAssumptions(server, loading.token(), Source.VERIFIED_EXISTING, false, true, true, true, true, true);
                    case "missing-datafix" -> missionAssumptions(server, loading.token(), Source.VERIFIED_EXISTING, true, false, true, true, true, true);
                    case "missing-cache" -> missionAssumptions(server, loading.token(), Source.VERIFIED_EXISTING, true, true, false, true, true, true);
                    case "missing-writer" -> missionAssumptions(server, loading.token(), Source.VERIFIED_EXISTING, true, true, true, false, true, true);
                    case "missing-stability" -> missionAssumptions(server, loading.token(), Source.VERIFIED_EXISTING, true, true, true, true, false, true);
                    case "missing-restore" -> missionAssumptions(server, loading.token(), Source.VERIFIED_EXISTING, true, true, true, true, true, false);
                    case "route-absent" -> routeAssumptions(server, loading.token(), Source.ABSENT_UNPROVEN, true, true, true, true, true, true, true);
                    case "route-io" -> routeAssumptions(server, loading.token(), Source.IO_FAILURE, true, true, true, true, true, true, true);
                    case "route-diagnostic" -> routeAssumptions(server, loading.token(), Source.VERIFIED_EXISTING, false, true, true, true, true, true, true);
                    case "route-datafix" -> routeAssumptions(server, loading.token(), Source.VERIFIED_EXISTING, true, false, true, true, true, true, true);
                    case "route-cache" -> routeAssumptions(server, loading.token(), Source.VERIFIED_EXISTING, true, true, false, true, true, true, true);
                    case "route-writer" -> routeAssumptions(server, loading.token(), Source.VERIFIED_EXISTING, true, true, true, false, true, true, true);
                    case "route-stability" -> routeAssumptions(server, loading.token(), Source.VERIFIED_EXISTING, true, true, true, true, false, true, true);
                    case "route-restore" -> routeAssumptions(server, loading.token(), Source.VERIFIED_EXISTING, true, true, true, true, true, false, true);
                    case "route-mismatch" -> routeAssumptions(server, loading.token(), Source.VERIFIED_EXISTING, true, true, true, true, true, true, false);
                    case "route-null" -> new SyntheticEvidence(store(server, loading.token(), Source.VERIFIED_EXISTING), null, true);
                    default -> throw new AssertionError();
                };
                accepted(complete(loading, server, loading.token(), e), Phase.UNKNOWN);
            }
            case "mission-other-epoch", "route-other-epoch", "mission-other-server", "route-other-server" -> {
                State first = accepted(begin(initial, server), Phase.RESTORING);
                Token old = first.token();
                State stopping = accepted(stop(first, server, old), Phase.STOPPING);
                State unbound = accepted(finishStop(stopping, server, old), Phase.UNBOUND);
                State current = accepted(begin(unbound, server), Phase.RESTORING);
                Object otherServer = new Object();
                Token token = current.token();
                boolean wrongMission = scenario.startsWith("mission");
                boolean wrongEpoch = scenario.endsWith("epoch");
                StoreEvidence valid = store(server, token, Source.VERIFIED_EXISTING);
                StoreEvidence foreign = store(wrongEpoch ? server : otherServer,
                        wrongEpoch ? old : token, Source.VERIFIED_EXISTING);
                SyntheticEvidence mixed = new SyntheticEvidence(wrongMission ? foreign : valid,
                        wrongMission ? valid : foreign, true);
                accepted(complete(current, server, token, mixed), Phase.UNKNOWN);
            }
            case "wrong-server" -> {
                Object left = new String("same"), right = new String("same");
                check(left.equals(right) && left != right, "fixture requires equal values but different identities");
                State current = accepted(begin(initial, left), Phase.RESTORING);
                State other = accepted(begin(initial(), right), Phase.RESTORING);
                rejected(current, complete(current, right, current.token(), evidence(right, current.token(), Source.VERIFIED_EXISTING)));
                rejected(current, complete(current, left, other.token(), evidence(left, other.token(), Source.VERIFIED_EXISTING)));
                rejected(current, stop(current, right, current.token()));
                rejected(current, stop(current, left, other.token()));
            }
            case "duplicate-start" -> {
                State loading = accepted(begin(initial, server), Phase.RESTORING);
                rejected(loading, begin(loading, server));
                rejected(loading, begin(loading, new Object()));
                State ready = accepted(complete(loading, server, loading.token(), evidence(server, loading.token(), Source.VERIFIED_EXISTING)), Phase.READY);
                rejected(ready, begin(ready, server));
                rejected(ready, complete(ready, server, ready.token(), evidence(server, ready.token(), Source.VERIFIED_EXISTING)));
            }
            case "out-of-order" -> {
                Token foreign = accepted(begin(initial(), new Object()), Phase.RESTORING).token();
                rejected(initial, complete(initial, server, foreign, evidence(server, foreign, Source.VERIFIED_EXISTING)));
                rejected(initial, stop(initial, server, foreign));
                rejected(initial, finishStop(initial, server, foreign));
                State loading = accepted(begin(initial, server), Phase.RESTORING);
                rejected(loading, finishStop(loading, server, loading.token()));
            }
            case "same-server-rebind" -> {
                State first = accepted(begin(initial, server), Phase.RESTORING);
                Token old = first.token();
                State stopping = accepted(stop(first, server, old), Phase.STOPPING);
                State unbound = accepted(finishStop(stopping, server, old), Phase.UNBOUND);
                State second = accepted(begin(unbound, server), Phase.RESTORING);
                check(second.token().epoch() > old.epoch(), "rebind must advance epoch");
                rejected(second, complete(second, server, old, evidence(server, old, Source.VERIFIED_EXISTING)));
                rejected(second, invalidate(second, server, old));
                rejected(second, stop(second, server, old));
                rejected(second, finishStop(second, server, old));
                accepted(complete(second, server, second.token(), evidence(server, second.token(), Source.VERIFIED_EXISTING)), Phase.READY);
            }
            case "invalidate" -> {
                State loading = accepted(begin(initial, server), Phase.RESTORING);
                State ready = accepted(complete(loading, server, loading.token(), evidence(server, loading.token(), Source.VERIFIED_EXISTING)), Phase.READY);
                State unknown = accepted(invalidate(ready, server, ready.token()), Phase.UNKNOWN);
                rejected(unknown, complete(unknown, server, ready.token(), evidence(server, ready.token(), Source.VERIFIED_EXISTING)));
                rejected(unknown, invalidate(unknown, server, ready.token()));
            }
            case "invalidate-restoring" -> {
                State loading = accepted(begin(initial, server), Phase.RESTORING);
                State unknown = accepted(invalidate(loading, server, loading.token()), Phase.UNKNOWN);
                rejected(unknown, complete(unknown, server, loading.token(), evidence(server, loading.token(), Source.VERIFIED_EXISTING)));
            }
            case "stop-unbind" -> {
                State loading = accepted(begin(initial, server), Phase.RESTORING);
                State ready = accepted(complete(loading, server, loading.token(), evidence(server, loading.token(), Source.VERIFIED_EXISTING)), Phase.READY);
                State stopping = accepted(stop(ready, server, ready.token()), Phase.STOPPING);
                rejected(stopping, stop(stopping, server, stopping.token()));
                rejected(stopping, complete(stopping, server, stopping.token(), evidence(server, stopping.token(), Source.VERIFIED_EXISTING)));
                State unbound = accepted(finishStop(stopping, server, stopping.token()), Phase.UNBOUND);
                rejected(unbound, finishStop(unbound, server, stopping.token()));
            }
            case "unknown-rebind" -> {
                State loading = accepted(begin(initial, server), Phase.RESTORING);
                State unknown = accepted(complete(loading, server, loading.token(), evidence(server, loading.token(), Source.IO_FAILURE)), Phase.UNKNOWN);
                State stopping = accepted(stop(unknown, server, unknown.token()), Phase.STOPPING);
                State unbound = accepted(finishStop(stopping, server, stopping.token()), Phase.UNBOUND);
                State next = accepted(begin(unbound, server), Phase.RESTORING);
                rejected(next, complete(next, server, unknown.token(), evidence(server, unknown.token(), Source.VERIFIED_EXISTING)));
                accepted(complete(next, server, next.token(), evidence(server, next.token(), Source.VERIFIED_EXISTING)), Phase.READY);
            }
            case "overflow" -> {
                State max = initialForTesting(Long.MAX_VALUE);
                rejected(max, begin(max, server));
                State near = initialForTesting(Long.MAX_VALUE - 1);
                State loading = accepted(begin(near, server), Phase.RESTORING);
                check(loading.token().epoch() == Long.MAX_VALUE, "last epoch should remain representable");
                State stopping = accepted(stop(loading, server, loading.token()), Phase.STOPPING);
                State done = accepted(finishStop(stopping, server, stopping.token()), Phase.UNBOUND);
                rejected(done, begin(done, server));
            }
            default -> throw new IllegalArgumentException("unknown scenario " + scenario);
        }
        System.out.println("PASS " + scenario);
    }

    private static StoreEvidence store(Object server, Token token, Source source) {
        return new StoreEvidence(server, token, source, true, true, true, true, true, true);
    }
    private static SyntheticEvidence evidence(Object server, Token token, Source source) {
        return new SyntheticEvidence(store(server, token, source), store(server, token, Source.VERIFIED_EXISTING), true);
    }
    private static SyntheticEvidence missionAssumptions(Object server, Token token, Source source,
                                                        boolean diagnostic, boolean datafix, boolean cache,
                                                        boolean writer, boolean stable, boolean restored) {
        return new SyntheticEvidence(new StoreEvidence(server, token, source, diagnostic, datafix, cache, writer, stable, restored),
                store(server, token, Source.VERIFIED_EXISTING), true);
    }
    private static SyntheticEvidence routeAssumptions(Object server, Token token, Source source,
                                                      boolean diagnostic, boolean datafix, boolean cache,
                                                      boolean writer, boolean stable, boolean restored, boolean matches) {
        return new SyntheticEvidence(store(server, token, Source.VERIFIED_EXISTING),
                new StoreEvidence(server, token, source, diagnostic, datafix, cache, writer, stable, restored), matches);
    }
    private static State accepted(Transition transition, Phase phase) {
        check(transition.accepted() && transition.state().phase() == phase, "expected accepted " + phase);
        return transition.state();
    }
    private static void rejected(State original, Transition transition) {
        check(!transition.accepted() && transition.state() == original, "rejection must leave state unchanged");
    }
    private static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }
}
