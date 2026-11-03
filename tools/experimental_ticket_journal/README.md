# Experimental ticket journal model

This is a pure, single-process, in-memory experiment. It imports no Forge or
Minecraft API, performs no filesystem, network or world operations, and is not
wired to production. Its synthetic events do not authorize any real operation.
It models one owner UUID, one world/dimension/mod/backend/chunk/ticking key,
one operation at a time, and no migration of vanilla boolean forced chunks.

Run the dependency-free tests with Python 3:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 tools/experimental_ticket_journal/test_ticket_journal.py
```

`Key` and `Event` are immutable. Every event must match the key, process epoch,
operation ID and next sequence. Fields use strict types; malformed events or
out-of-order, duplicate, inconsistent or unexpected events enter `UNKNOWN`, which
is absorbing. A remove has a fresh operation UUID. Different dimensions,
world identifiers, owner UUIDs, chunk coordinates and ticking flags are distinct.

A new model starts in `UNKNOWN` unless its caller explicitly supplies
`assume_exclusive=True`. This is **only a hypothetical assumption**, not proof
of owner exclusivity, world identity, backend support or any right to remove a
real ticket. The caller must use `CONTEXT_UNCERTAIN` / `EXTERNAL_OWNER` to model
uncertainty or a suspected competing writer; absence of such an event is not
proof that no other writer exists. UUIDs and epoch values are caller-supplied;
a cloned world or reused/forged epoch can carry the same identifiers. The backend
field is an opaque consistency label; the model does not validate versions.

For either operation, the synthetic sequence is intent, externally asserted
`DURABLE`, `DISPATCH`, then `RETURN_TRUE`. Before `DURABLE`, dispatch is rejected.
`DURABLE` is a caller assertion; the model performs no write, fsync or validation.
`simulated_dispatch()` is a repeatable read of the next hypothetical action,
not a one-shot permit or synchronization primitive. Recording `DISPATCH` consumes
that model transition; actual atomicity, reentry and cross-thread/process locking
are outside this model. True produces only `ADD_RETURNED_VOLATILE` or
`REMOVE_RETURNED_VOLATILE`, never a saved, exclusive, recovered or entity-ticking
claim. False, exception, crash, corruption, external-owner suspicion, context
uncertainty or restart produces `UNKNOWN`; later events cannot escape it.

A process after restart must use `Model.after_restart(...)`, which starts in
`UNKNOWN` and cannot grant a simulated dispatch. Replaying old events into a new
model with a different epoch also halts. The model cannot detect a caller that
incorrectly reuses the old epoch and constructs a supposedly fresh model with
`assume_exclusive=True`; it is not a crash-safe journal or replay implementation.
It does not parse/checksum a file or authenticate any event. `CORRUPT` is an
external report, not automatic corruption detection.

Fixed Forge has separate tracker, chunk load, dirty-data and provider operations;
an exception can leave partial state and a repeated call may not finish it. A
real design needs an independently verified immutable world identity, exclusive
writer protocol, durable write-ahead records and storage ordering, version checks,
startup reconciliation and a plan for unresolved state. Even fsync of a separate
journal cannot atomically commit Forge SavedData. Callback absence does not prove
an empty set, and retained tickets may be reinstalled on world startup. No such
mechanism is implemented here. Real Forge/GameTest and crash/restart validation
in fresh isolated worlds remain necessary before making any operational claim.
