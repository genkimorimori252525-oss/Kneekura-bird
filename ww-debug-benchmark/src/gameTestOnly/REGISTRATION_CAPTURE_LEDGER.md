# Registration capture ledger: synthetic model only

`RegistrationCaptureLedger` is a test-only, one-shot consistency check for
events reported by its caller. It does not hook Forge or inspect a real
registry. `CONSISTENT` means only that the supplied event sequence agrees with
the model; it is **not authentication, runtime evidence, or permission to start
a GameTest**.

The caller supplies an independently chosen declaring class, method name and
argument class. The ledger resolves a declared `public static void` method;
the classes supplied to it are assumptions, not authenticated inputs. The
first reported Method must equal that definition. Separately resolving an equal
Method can produce another object, so `Method.equals` is used for this initial
comparison. Later observations must use the exact Method object passed at begin,
the same opaque token and owner thread, and the same consumer and function
object references in the required order. A caller reports construction and
registration; the ledger does not invoke or inspect those operations. In
particular, the reported consumer is not read from a function field and its
actual association with the function is not established by this model.

One selected function matching the captured reference and explicit `ABSENT`
observations for both callbacks are required. `UNKNOWN`, `PRESENT`, null,
additional selections, missing stages, duplicates, wrong order or references,
and cross-thread events are inconsistent. Explicit abort is terminal; a
missing finish remains incomplete. Inconsistency is sticky. A selection array
is observed only at that call; later mutation or another thread changing the
source is not prevented. Callback absence is the caller's assertion, not a
callback inspection. No selection is filtered or changed.

`CONSISTENT` is an observation at the moment of `finish`, not a lasting
invariant: a subsequent event makes the ledger inconsistent. It provides no
execution authorization and does not make later selection, callback or object
state immutable.

The fixed mapped Forge implementation currently passes one Method through
`turnMethodIntoTestFunction` and its nested `turnMethodIntoConsumer`; callback
and generator paths are separate. This model neither proves an adapter captures
those events accurately nor rules out generator code, initialization side
effects, alternate class loaders, transformed bytecode, concurrent mutation,
or unreported events. `GameTestBatchGate` has its own separate inspection and
provenance requirements; these classes are not connected. Main's static
call-site check also does not prove a runtime hook. World isolation, player
takeover, forced chunks and cleanup remain unverified.

For a deterministic standalone check using JDK 17, compile only
`RegistrationCaptureLedger.java` and `RegistrationCaptureLedgerChecks.java`
into a new temporary directory, with an empty classpath and sourcepath, and run
`com.wwdebug.gametestprobe.RegistrationCaptureLedgerChecks` from that directory.
No Minecraft/Forge classes, GameTest, network or world are needed. The test
uses synthetic caller events; it does not authenticate their origin.
