# Continuation brief for an autonomous session

You are taking over work on Issue #7: every one of the 24 base aircraft, flown by a mob, must
take off, navigate, avoid terrain, execute its role and doctrine, fight, return, land and stop —
while a player at the controls receives zero AI input.

Read `/AGENTS.md` and `docs/AI_HANDOFF.md` first. This file is the operating brief that sits
between them: what to do next, in what order, and which mistakes are already known.

Live GitHub state overrides everything written here.

---

## Set expectations honestly

You will not finish Issue #7 in one session, and you should not pretend otherwise in your
reports. Every behavioural change needs an exact-physics run on a **single self-hosted runner**,
serially, at roughly 7–8 minutes per scenario. That is the hard throughput ceiling.

What a long session can realistically deliver:

- finish the arbiter conversion (six writers remain);
- add the damage / pilot-loss authority;
- possibly begin the doctrine split.

Bombing, dive bombing, torpedo and escort work sits behind all of that. Say so plainly rather
than reporting partial work as completion.

---

## The one rule that will silently break things

**The converted set must always be the top-K layers by priority.**

Seven layers write control directly, in fixed statement order, and the last one wins. That order
*is* the priority mechanism today. The conversion replaces it with selection, but mid-conversion
the arbiter writes the winning proposal **last** — after every unconverted layer has already
written.

So converting a *low*-priority layer first makes its proposal overwrite the higher layers that
wrote earlier. That is a priority inversion introduced by the refactor meant to prevent them, and
no existing test would catch it.

Conversion order, highest first. Do not deviate:

| Order | Layer | Authority | Site |
| --- | --- | --- | --- |
| done | `DefensiveAirCombatManager` | `DEFENSIVE_COMBAT` (50) | PR #95 |
| 1 | `AirCombatManeuverManager` | `OFFENSIVE_COMBAT` (40) | `:101` |
| 2 | `EnergyFighterApexYawAdapter` | `ENERGY_FIGHTER_REENGAGEMENT` (40) | `:481` |
| 3 | `FormationFlightManager` formation slot | `FORMATION` (20) | `:212` |
| 4 | `AutonomousFlightManager` | `BASE_AUTONOMY` (10) | `:104` |
| 5 | `BenchmarkManager` | `BENCHMARK_CONTROL` (5) | `:82` |
| 6 | `FormationFlightManager` collision path | `COLLISION_AVOIDANCE` (70) | `:122` |

Order 6 is last on purpose. It is the highest priority of the group, so it is safe at any point —
and doing it last means the step that closes the loop is also the one that makes the invariant
checkable.

**When the last one lands**, `ReflectiveAircraft.applyControl` must have exactly one production
caller: `ControlAuthorityArbiter.write`. Add a GameTest asserting one write per aircraft per tick,
delete `ControlOutcome`, and delete `ControlOutcome.alreadyWrote` — every remaining call to it is
a layer still unconverted, which is why it is named that way.

### The conversion pattern

Mechanical. For each layer:

1. change `applyControl` to return `Optional<ControlProposal>`;
2. every early `return;` becomes `return Optional.empty();`
3. delete the `ReflectiveAircraft.applyControl(...)` call;
4. `return Optional.of(ControlProposal.fromGuidance(Authority.X, output));`
5. keep **all** logging, state updates and telemetry exactly where they are — they are the
   layer's own bookkeeping, not the arbiter's business;
6. update the caller (`FighterCombatFacade` or `ControlAuthorityArbiter`) to
   `ControlOutcome.proposed(...)`.

`fromGuidance` applies the roll negation (`-output.x()`). `ofRawInputs` does not.
`BenchmarkManager` is the one writer that does not negate — use `ofRawInputs` there.

---

## After the conversion, in this order

1. **`AircraftDamageAuthority`** at priority levels 2–3. There is no health or damage logic
   anywhere in the autopilot package, though `MissionOrder.AbortCondition` already declares
   `PILOT_LOST`, `AIRCRAFT_DESTROYED` and `CRITICAL_DAMAGE`. Insert it *by priority*, which is
   only possible after the conversion — that is the whole reason the conversion comes first.
2. **`MissionOrder.type()` has zero behavioural readers.** Give it one by routing
   `RETURN_TO_BASE` and `LAND` through the already-qualified landing chain
   (`RETURN_TO_PATTERN → DOWNWIND → BASE → FINAL → FLARE → TOUCHDOWN → BRAKE → PARKED`).
3. **Split `ATTACKER`** into dive-bomber (D4Y, Ju 87, SBD) and ground-attacker (IL-2), and replace
   the semantically empty `escort` doctrine on the five bombers and G4M. Before migrating, harden
   `BenchmarkCategory.fromRole` — its `dive_bomber -> BOMBER` mapping would silently reclassify
   the three dive bombers as bombers and trip the heavy-aircraft turn-floor clamp.
4. Only then: level bombing, dive bombing, IL-2 low-level attack, G4M torpedo, escort formations.

---

## Runner discipline

One self-hosted Windows runner named `ジョリー`, id 22, on the owner's PC. It is the throughput
ceiling and the single most common source of lost hours.

**Prove it is alive before dispatching.** A job assigned to a stopped runner sits queued for
hours and then dies with an unhelpful internal error. That cost 3h49m once (run `30154656783`:
`runner_id: 0`, empty `steps`, no log archive).

```bash
gh api repos/:owner/:repo/actions/runners -q '.runners[]|"\(.name) \(.status) busy=\(.busy)"'
```

After dispatch, confirm `runner_id != 0` on the job. **A run whose `runner_id` stays 0 is
orphaned, not slow.** `timeout-minutes` is an *execution* timeout that arms at "Set up job", so it
never fires on an undispatched job.

**Never run a local Gradle build while the runner has a job.** Both use
`GRADLE_USER_HOME=C:\Users\genki\.gradle` and will corrupt each other's ForgeGradle caches. Wait
for `busy=false`.

**Dispatch route qualifications without a no-op commit** — `workflow_dispatch` is enabled:

```bash
gh workflow run ww-local-route-validation.yml --ref main \
  -f ref=<40-char behaviour commit> -f aircraft=warfare_wings:<id>
```

A serial driver with liveness gating, orphan detection and a two-consecutive-failure stop is at
`scratchpad/qualify-remaining.sh` from the session that reached 24/24. Rebuild it if the
scratchpad is gone; the logic is described above.

---

## Local validation loop

Faster than CI and costs no Actions minutes. Use it before every push.

```
JAVA_HOME = C:\Program Files\Java\jdk-17
gradle    = C:\Users\genki\.gradle\wrapper\dists\gradle-8.8-bin\dl7vupf4psengwqhwktix4v1\gradle-8.8\bin\gradle
cwd       = <worktree>/ww-debug-benchmark

gradle --no-daemon --console=plain build          # ~25-40 s
```

There is **no Gradle wrapper** in this repository — invoke the cached distribution directly. A
fresh worktree needs the two gitignored runtime jars copied into
`ww-debug-benchmark/flight-test-mods/`; copy them from any existing worktree.

---

## Regression baseline

`docs/validation/2026-07-26/route-regression-signatures.json` holds one signature per base
aircraft: exact match on role, verdict, reason, final phase and terminal reason; tolerance match
on tick counts and geometry.

**Diff against it rather than re-arguing whether a change was harmless.** A boolean suite only
catches an aircraft that stops reaching `PARKED`; it cannot catch drift, and drift is the
realistic failure mode of everything on the list above.

Control ownership is recorded as `control_authority_change` telemetry on every handover. Compare
the handover sequence before and after a change — that is the cheapest evidence that a conversion
preserved behaviour.

Its known limit: it records only the *winner*, so it cannot detect a case where a higher-priority
condition holds while a lower layer owns the tick. Detecting that needs the set of layers that
*claimed* the tick, which the completed conversion makes possible.

---

## Merge rules

- Draft PRs by default; mark ready only when checks are green.
- Each PR triggers two self-hosted jobs (`build`, `Headless flight (dogfight_mutual)`), serially.
  Docs-only PRs trigger none and can merge immediately.
- Never merge a behaviour change while required checks are unexecutable.
- One commit tests one behavioural hypothesis. Hard ceiling **10 files / 800 lines** per patch.
- `gh pr update-branch <n>` before merging if main moved.

---

## Traps already hit — do not rediscover these

- **`gh pr create --body-file`, never a heredoc.** A heredoc after a pipe hangs the call, times
  out, and leaves the branch pushed with no PR. Write the body to a file first.
- **`export MSYS_NO_PATHCONV=1`** in every Git Bash command touching `gh api` paths or
  `git show rev:path`. Without it MSYS mangles `/repos/...` into a filesystem path.
- **Windows MAX_PATH breaks artifact downloads** into the scratchpad. Use a short directory such
  as `C:/wwtmp`, and pass it as `C:/wwtmp`, not `/c/wwtmp` — with path conversion disabled, `gh`
  does not understand the MSYS form.
- **The build no longer rewrites its own source** (PR #81). If `git status` shows modified tracked
  sources after a build, that is a regression, not normal.
- **A dropped TLS handshake to `maven.minecraftforge.net`** fails the build in ~20 s and, because
  the build step carries `continue-on-error`, surfaces only as the terminal failure step — it
  reads exactly like an aircraft failure. One bounded retry is wired in; if you see
  `SSLHandshakeException`, it is the network, not the code.
- **The owner's local branch `agent/p47-local-validation`** is 505 commits behind main with 33
  unpushed commits. Leave it alone. Its subject — the P-47N mutual dogfight — is resolved on main.
  Work in worktrees created off `origin/main`.

---

## Safety invariants — never weaken to make something pass

- a player at the controls receives no automated input;
- no firing at a target behind the fixed forward guns;
- no initial rear free shot in the reciprocal dogfight qualification;
- line-of-sight, range, friendly-fire, terrain and collision checks stay authoritative;
- both aircraft remain autonomous participants, never scripted firing dummies;
- no ground contact or aircraft collision during a combat window;
- minimum 8-block separation;
- energy fighters must not escape indefinitely beyond the useful simulation area.

`MobPilotGate` is the single pilot gate. Do **not** route the two friendly-fire checks
(`CombatTargetSelector:104`, `CombatWeaponManager:273`) through it — excluding a player as the
*pilot* and excluding a player as a *target* are different rules that happen to test the same Java
type, and merging them would let a change to one silently move the other.

---

## Reporting

Close every unit with a human-readable checkpoint on Issue #7: current commit, what was validated,
the exact failing acceptance condition if any, and the next single hypothesis. Never end on a
tool call or a poll.

If something is blocked, say what is blocked and why, finish everything that is not blocked, and
leave the blocked item stated plainly. Partial work reported as completion is worse than slow
progress.
