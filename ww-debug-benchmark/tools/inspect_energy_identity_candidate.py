#!/usr/bin/env python3
"""Compare a private source-copy energy identity candidate; never run a MOD.

The candidate is generated under a new evidence directory. It is not a patch
to the checkout. All dependencies and source/fixture inputs must be trusted.
"""
import argparse
import difflib
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "src/main/java/com/wwdebug/autopilot"
RUNNER = HERE / "inspect_energy_doctrine_identity.py"
PROBE = HERE / "energy_candidate_fixture/Probe.java"
EXTRA_CASES = ("fallback-level", "fallback-outer-a-inner-b-final-a",
               "fallback-outer-level-inner-other-final-outer", "empty-claimed",
               "climb-same", "climb-swap", "pivot-same", "pivot-swap", "capture-same", "capture-swap",
               "empty-aim-alignment-same", "empty-aim-alignment-swap",
               "throw-energy-pilot", "throw-offensive-pilot")


def replace_once(text, old, new, label):
    if text.count(old) != 1:
        raise ValueError(f"candidate anchor mismatch: {label}: {text.count(old)}")
    return text.replace(old, new, 1)


def transform(name, text):
    if name == "AirCombatManeuverManager":
        start = text.index("        Optional<CombatTargetSelector.Solution> selected =")
        end = text.index("    public static boolean active(Entity aircraft)", start)
        before, section, after = text[:start], text[start:end], text[end:]
        old = "return new OffensiveEvaluation(Optional.empty(), null, null);"
        if section.count(old) != 6:
            raise ValueError("offensive post-gate returns changed")
        return before + section.replace(old, "return new OffensiveEvaluation(Optional.empty(), pilot, level);") + after

    if name == "EnergyFighterApexYawAdapter":
        start = text.index("    public static Optional<ControlProposal> applyControl(Entity aircraft) {")
        end = text.index("    private static boolean canStart(", start)
        before, section, after = text[:start], text[start:end], text[end:]
        section = replace_once(section,
            "    public static Optional<ControlProposal> applyControl(Entity aircraft) {",
            """    public static Optional<ControlProposal> applyControl(Entity aircraft) {
        return evaluateWithPilot(aircraft).proposal();
    }

    record EnergyEvaluation(Optional<ControlProposal> proposal, Mob pilot, ServerLevel level,
                            AirCombatManeuverManager.OffensiveEvaluation offensive, boolean doctrine) { }

    static EnergyEvaluation evaluateWithPilot(Entity aircraft) {""", "energy wrapper")
        if section.count("return Optional.empty();") != 11:
            raise ValueError("energy empty returns changed")
        section = section.replace("return Optional.empty();",
                                  "return new EnergyEvaluation(Optional.empty(), null, null, null, false);")
        section = replace_once(section, "        Optional<ControlProposal> proposal = switch (state.stage) {",
            """        AirCombatManeuverManager.OffensiveEvaluation offensive = null;
        boolean doctrineStage = state.stage == Stage.DOCTRINE;
        Optional<ControlProposal> proposal = switch (state.stage) {""", "energy stage")
        section = replace_once(section,
            "                Optional<ControlProposal> doctrine = AirCombatManeuverManager.applyControl(aircraft);",
            """                offensive = AirCombatManeuverManager.evaluateWithPilot(aircraft);
                Optional<ControlProposal> doctrine = offensive.proposal();""", "inner evaluation")
        section = replace_once(section, "        return proposal;",
            "        return new EnergyEvaluation(proposal, pilot, level, offensive, doctrineStage);", "energy result")
        return before + section + after

    if name == "FighterCombatFacade":
        text = replace_once(text,
            """                            boolean defensiveProposal, AirCombatManeuverManager.OffensiveEvaluation offensive) {
        CombatEvaluation(ControlOutcome outcome, Mob defensivePilot, ServerLevel defensiveLevel,
                         boolean defensiveProposal) {
            this(outcome, defensivePilot, defensiveLevel, defensiveProposal, null);
        }""",
            """                            boolean defensiveProposal, AirCombatManeuverManager.OffensiveEvaluation offensive,
                            EnergyFighterApexYawAdapter.EnergyEvaluation energy) {
        CombatEvaluation(ControlOutcome outcome, Mob defensivePilot, ServerLevel defensiveLevel,
                         boolean defensiveProposal) {
            this(outcome, defensivePilot, defensiveLevel, defensiveProposal, null, null);
        }
        CombatEvaluation(ControlOutcome outcome, Mob defensivePilot, ServerLevel defensiveLevel,
                         boolean defensiveProposal, AirCombatManeuverManager.OffensiveEvaluation offensive) {
            this(outcome, defensivePilot, defensiveLevel, defensiveProposal, offensive, null);
        }""", "facade record")
        return replace_once(text,
            """        Optional<ControlProposal> energy = EnergyFighterApexYawAdapter.applyControl(aircraft);
        if (energy.isPresent()) {
            return new CombatEvaluation(ControlOutcome.proposed(energy.get()), null, null, false);
        }""",
            """        EnergyFighterApexYawAdapter.EnergyEvaluation energy = EnergyFighterApexYawAdapter.evaluateWithPilot(aircraft);
        if (energy.proposal().isPresent()) {
            return new CombatEvaluation(ControlOutcome.proposed(energy.proposal().get()), null, null, false, null, energy);
        }""", "facade energy")

    if name == "ControlAuthorityArbiter":
        text = replace_once(text,
            """                } else if (combatEvaluation.offensive() != null
                        && combatEvaluation.offensive().proposal().isPresent()) {""",
            """                } else if (combatEvaluation.energy() != null) {
                    DefensiveAttempt attempt = attemptPendingWrite(
                            aircraft, combat.pendingWrite().get(), combatEvaluation.energy());
                    if (attempt == DefensiveAttempt.IDENTITY_MISMATCH) {
                        return new PendingDecision(Authority.NONE, false);
                    }
                    if (attempt == DefensiveAttempt.REJECTED) {
                        return rejected(aircraft);
                    }
                } else if (combatEvaluation.offensive() != null
                        && combatEvaluation.offensive().proposal().isPresent()) {""", "arbiter dispatch")
        marker = "    // True means the adapter was called, not that the native setters succeeded.\n"
        helper = """    private static DefensiveAttempt attemptPendingWrite(Entity aircraft, ControlProposal proposal,
            EnergyFighterApexYawAdapter.EnergyEvaluation energy) {
        if (aircraft.isRemoved()) return DefensiveAttempt.REJECTED;
        var level = aircraft.level();
        if (level.isClientSide) return DefensiveAttempt.REJECTED;
        var pilot = MobPilotGate.pilotOf(aircraft);
        if (pilot.isEmpty() || energy.pilot() == null || energy.level() == null)
            return DefensiveAttempt.REJECTED;
        if (pilot.get() != energy.pilot() || level != energy.level())
            return DefensiveAttempt.IDENTITY_MISMATCH;
        if (energy.doctrine()) {
            var inner = energy.offensive();
            if (inner == null || inner.pilot() == null || inner.level() == null)
                return DefensiveAttempt.REJECTED;
            if (pilot.get() != inner.pilot() || level != inner.level())
                return DefensiveAttempt.IDENTITY_MISMATCH;
        }
        ReflectiveAircraft.applyControl(aircraft, proposal.x(), proposal.y(), proposal.z(), proposal.engineTarget());
        return DefensiveAttempt.ATTEMPTED;
    }

"""
        return replace_once(text, marker, helper + marker, "arbiter energy helper")
    return text


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--java-home", required=True)
    parser.add_argument("--dependencies-json", required=True)
    parser.add_argument("--mode", choices=("baseline", "candidate"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.absolute()
    out.mkdir(mode=0o700)
    spec = importlib.util.spec_from_file_location("energy_red_runner", RUNNER)
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    source_root = out / "candidate-source"
    source_dir = source_root / "com/wwdebug/autopilot"
    source_dir.mkdir(parents=True)
    records = {}
    patches = []
    for name in runner.SOURCE_NAMES:
        original = SOURCE / (name + ".java")
        target = source_dir / original.name
        original_text = original.read_text(encoding="utf-8")
        candidate = transform(name, original_text) if args.mode == "candidate" else original_text
        target.write_text(candidate, encoding="utf-8")
        records[name] = {"original_sha256": sha(original), "candidate_sha256": sha(target),
                         "modified": original_text != candidate}
        if original_text != candidate:
            patches.extend(difflib.unified_diff(original_text.splitlines(keepends=True),
                candidate.splitlines(keepends=True), fromfile="baseline/" + original.name,
                tofile="candidate/" + original.name))
    (out / "candidate.patch").write_text("".join(patches), encoding="utf-8")
    shutil.copyfile(__file__, out / "candidate-runner-snapshot.py")
    probe_text = replace_once(PROBE.read_text(encoding="utf-8"),
        'stack("EnergyFighterApexYawAdapter", "applyControl")) {',
        '(stack("EnergyFighterApexYawAdapter", "applyControl") || '
        'stack("EnergyFighterApexYawAdapter", "evaluateWithPilot"))) {', "probe energy stack")
    candidate_probe = out / "probe-input.java"
    candidate_probe.write_text(probe_text, encoding="utf-8")
    original_fixture = runner.FIXTURE
    fake_fixture = out / "fake-fixture.py"
    fake_fixture.write_text(original_fixture.read_text(encoding="utf-8") + '''
_log_key = "com/wwdebug/autopilot/AutopilotLogManager.java"
_log_old = 'Probe.events.add("log:"+t);'
if STUBS[_log_key].count(_log_old) != 1:
    raise ValueError("fake logger reentry anchor changed")
STUBS[_log_key] = STUBS[_log_key].replace(_log_old, _log_old + 'Probe.onFakeLog(t,e);', 1)
_entity_key = "net/minecraft/world/entity/Entity.java"
_level_old = 'public Level level(){return world;}'
if STUBS[_entity_key].count(_level_old) != 1:
    raise ValueError("fake level getter anchor changed")
STUBS[_entity_key] = STUBS[_entity_key].replace(_level_old, 'public Level level(){com.wwdebug.autopilot.Probe.onLevel(this);return world;}', 1)
''', encoding="utf-8")
    (out / "candidate-manifest.json").write_text(json.dumps({"sources": records,
        "scope": "private source-copy " + args.mode + "; caller supplied inputs are not authenticated",
        "runner_sha256": sha(RUNNER), "probe_sha256": sha(PROBE),
        "candidate_probe_sha256": sha(candidate_probe),
        "original_fake_fixture_sha256": sha(original_fixture), "fake_fixture_sha256": sha(fake_fixture),
        "probe_change": "recognize candidate energy wrapper stack name and deliberate fake logger reentry"}, indent=2) + "\n")
    runner.ROOT = source_root
    runner.PROBE = candidate_probe
    runner.FIXTURE = fake_fixture
    runner.CASES = runner.CASES + EXTRA_CASES
    sys.argv = [str(RUNNER), "--java-home", args.java_home, "--dependencies-json", args.dependencies_json,
                "--output", str(out / "run")]
    return runner.main()


if __name__ == "__main__":
    sys.exit(main())
