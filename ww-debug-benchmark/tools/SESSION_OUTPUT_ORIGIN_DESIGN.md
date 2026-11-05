# Session output origin: boundaries for a future control decision

This is a design note based on the test-only #235 phase observation and #214
production source. It is **not** an implementation, approval of a control
policy, safety proof or real-MOD qualification. #235's trace is a private
source-copy experiment; its synthetic observations do not provide an authority
token or demonstrate runtime Mixin behavior. This note changes no code.

## Existing behavior and duplicate work

`AutopilotSession.tick(MinecraftServer, Entity)` returns a `FlightControlOutput`.
It increments clocks, runs mission-timeout/stall/approach guards, dispatches
`plan` by the then-current phase, and may replace that plan with a low-AGL
emergency output. A plan branch can transition the session before returning an
output created by the old branch. #226 already observed the turn transition
boundaries and #235 distinguishes tick entry, guard-adjusted plan dispatch,
phase after plan and post-plan emergency in fake state. #231 tested a different
recovery capture and exposed extra-getter, reentry, fallback and logging limits;
it is **not** a production design to copy. #233/#234 tested two slot-throttle
hypotheses, not a safe selection rule. Do not repeat these as new fixes.

There are multiple later layers. A `@ModifyVariable` on `AutonomousFlightManager`
`applyControl`, `STORE` ordinal 0, `require=1`, can replace the returned session
output with owned-route guidance. A separate `AutopilotSession.tick` RETURN
Mixin can adjust route clocks. The manager then captures another snapshot, runs
terrain handling and native-flight adaptation, and calls the reflective setter.
The arbiter has already called the benchmark writer, calls the base manager,
then the mutual hold and formation evaluation; collision avoidance can write
directly. Combat, collision-risk-only, terrain, formation proposal and base
outcomes follow the existing arbiter branches. This is a migration with prior
direct writes, not an atomic single-writer transaction.

`lastOutput` describes a session-level return before route/manager adaptation;
it has no invocation identifier. After an exception before assignment it can
remain null or retain a previous tick's value. Reentry can replace it and a
server tick or UUID alone does not prove it belongs to the current call. Current
frame phase is the phase when logging happens, not automatically the plan's
dispatch phase. Adapter telemetry and authority labels are not proof that a
native setter succeeded; formation logs can be emitted before the arbiter
accepts or writes its proposal.

## Invariants a future mechanism must establish

* Distinguish entry phase, **post-guard dispatch phase**, phase after `plan`,
  whether the session emergency replaced the plan, and the exact session
  return. Terminal early returns have no ordinary dispatch. Never infer the
  source phase from an output reason string or from the post-plan phase alone.
* Tie any usable metadata to the same session object, aircraft and one
  completed invocation and its returned output. Explicitly represent absent,
  incomplete, exceptional, reentered and stale observations as unknown; do not
  carry them into a later tick. A field containing only the most recent output,
  a cached authority marker, a UUID or value equality cannot establish this.
* Distinguish the **pre-Mixin** session return from the manager's **post-Mixin**
  mission value, the terrain/native-adapted value and any eventual proposal.
  If route guidance or another hook replaces a value, do not silently attach the
  old origin to it. Reference mismatch can conservatively expose some replacement
  as unknown; reference equality alone cannot rule out aliasing, reentry or ABA.
* Preserve `tick`'s old descriptor, its RETURN-hook semantics and the
  `FlightControlOutput` STORE targeted by route guidance in `applyControl`.
  Static descriptor/bytecode inspection is necessary, not proof that the
  transformed Mixin executes correctly. The older #207-style body move removes
  that STORE (#232). A new first STORE of the same type could also change the
  ordinal target. Changing a public record can alter constructors, equality,
  reflection and external consumers even when selected descriptors remain.
* Do not add unsafe reads before the existing base path: #231 showed an added
  pilot getter can move an injected exception before the old base call. Preserve
  player/non-mob, client/removed, pilot and level checks, collision direct and
  risk-only paths, terrain and combat/firing gates. Unknown provenance must not
  be called safe merely because existing fallback ran. Earlier writes cannot
  be rolled back by a later rejection.
* Distinguish proposal generation, arbiter selection, setter **attempt** and
  any separately established native effect. `ReflectiveAircraft.applyControl`
  is void and its individual setters can partially fail or be no-ops (#230).
  Replaying values may duplicate effects. Do not label an attempted call as a
  successful native write or report one set of values while attempting another.

## Design boundary to investigate, not an accepted implementation

An immutable per-invocation observation could group dispatch phase,
post-plan phase, emergency/terminal state and the original session output.
The manager would need to associate it with the actual `tick` call while
retaining the required public and Mixin-visible boundaries. An explicit scoped
call result may be safer to reason about than a UUID-keyed global cache, but its
concrete transport remains undecided: simply adding a helper that moves the
manager body, wrapping `tick` with a changed descriptor, or reading a `last*`
field after the fact can break hooks or bind stale data. Any reference-based
association must allow route replacement and nested/reentrant calls to become
unknown, without treating that unknown as a reason to weaken an existing gate.
No new status getter or pilot/level getter before base control is assumed here.

This boundary by itself answers only what produced the original session output.
It does not determine whether formation, combat, collision or terrain should
own a tick, pause or advance a mission clock, or how an aircraft should recover
speed. Those decisions need separate contracts, not inference from provenance.

## Staged evidence before any control change

1. Keep #235's baseline/synthetic trace comparisons and add only new
   counterexamples: session already has a prior `lastOutput`, early exceptions,
   guards before plan, transition within plan, terminal return, post-plan
   emergency and same-session nested/reentrant calls. Compare phase/clocks,
   selected output, event/frame ordering and exception propagation with the
   unmodified source; an unreached case is incomplete.
2. For a proposed transport, demonstrate unchanged `tick` and public method
   descriptors and the exact manager STORE location on compiled classes. Verify
   route active/inactive/completed, output replaced/unchanged, pre/post route
   clocks and exception paths. Then run the fixed Forge/Mixin transformation;
   bytecode inspection and stand-ins alone cannot establish runtime compatibility.
3. Separately exercise arbiter's real selected paths with fake setters: baseline,
   prior benchmark/base write, formation pending and absent, actual collision
   writer versus risk-only label, terrain, combat claims, player/mob/level change,
   removed/client, phase transition, nested calls and partial/no-op setters.
   Preserve the #230 fault matrix and do not equate attempted input with success.
4. Only after the behavior and identity contract is reviewable, build, run
   deterministic checks and a fresh fixed-MOD scenario with matching inputs,
   complete logs, verified cleanup and separate process/checker statuses. If
   capacity, permissions, observation coverage or cleanup is unknown, preserve
   evidence and mark it incomplete. Do not claim all 24 aircraft from this case.
