#!/usr/bin/env python3
"""Compare #214 source to one deliberately unsafe copied turn-phase gate.

Test-only: launches the existing stand-in runner, never Minecraft, Gradle, or a world.
Expected result: collision adapter assertions pass on baseline and fail on the
counterfactual; authority labels alone do not establish collision writes.
"""
import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src/main/java/com/wwdebug/autopilot'
RUNNER = ROOT / 'tools/test_formation_recorded_turn_observation.py'
EXPECTED = {
    'AirspaceSafetyProbe.java': '1fd404c89f28bd7f5238c38481a6bbc15f00a0c4d0bde88b8dbaec1bcdc8313d',
    'AutonomousFlightManager.java': '45a24a85af3d44a1d189a8e0f18fec178f1da4c19639d820b76e75a94488e177',
    'AutopilotSession.java': '6febbf679b837f67639a59f62fce9afc7c5a05093962f50ab000a3126d46d4c1',
    'ControlAuthorityArbiter.java': '090110ff9896c5020efc0a47056063f1e10dfdf57c706b2273cd29a470bc8a3f',
    'ControlOutcome.java': 'e3bb9f37ca3123dcc8e03d5a6e0f17384258063a03b553f0abe0012a7a287e00',
    'ControlProposal.java': 'adc38454260fff85fc7d4a84a4413fab4aa37e064f7b81ed0f1c902ef03fa4ae',
    'FlightControlOutput.java': '9ccdc3de853f18aafd714fdf9af337510bff828cb1084b84c3cb44b6010263fe',
    'FlightPhase.java': 'ae86d148d0345e3a6ffcb97103d98b9dd4dbc6cb45fe707d2d11ff315d61e29a',
    'FlightProfile.java': '78a24d92ba80f420596d2de5d3b83288351813314e5cbf5dbf14380bf661d406',
    'FormationFlightManager.java': 'dcd90dc80255bbfe90fc1e275345c807f899483f4c8ac71f7de83bac85b193e7',
    'MobPilotGate.java': '88929c73a9f8719313c6fccd0b40d5c2a7ea4631be1230ef747e206454278fa2',
}
RUNNER_SHA = 'f63f22e0ac54fa7d2554f81d54af0de9b820ed67ae629e8262c36b9845df40ea'
CASES = ('1549-grouped', '1549-ungrouped', '1549-terrain', '1549-collision',
         '1549-player', '1589-grouped', '1589-ungrouped', '1589-terrain',
         '1589-collision', '1589-player', '1589-timeout')
RED = {'1549-grouped', '1549-collision', '1589-grouped', '1589-collision'}
NEEDLE = 'if (!eligiblePhase(phase) || aircraft.onGround()'
REPLACEMENT = 'if (!eligiblePhase(phase) || phase == FlightPhase.TURN_RIGHT || aircraft.onGround()'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def source_inputs():
    files = {name: (SRC / name).read_bytes() for name in EXPECTED}
    files['runner'] = RUNNER.read_bytes()
    return files


def write_bytes(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as f:
        f.write(data)


def run_one(mode, output, files, jdk, deps):
    mode_dir = output / mode
    project = mode_dir / 'project'
    for name, original in files.items():
        if name == 'runner':
            target = project / 'tools' / RUNNER.name
            data = original
        else:
            target = project / 'src/main/java/com/wwdebug/autopilot' / name
            data = original
            if mode == 'early-gate' and name == 'FormationFlightManager.java':
                text = original.decode('utf-8')
                if text.count(NEEDLE) != 1:
                    raise ValueError('unexpected candidate injection point')
                altered = text.replace(NEEDLE, REPLACEMENT)
                patch = ''.join(difflib.unified_diff(text.splitlines(True), altered.splitlines(True),
                                  fromfile='baseline/FormationFlightManager.java',
                                  tofile='early-gate/FormationFlightManager.java'))
                write_bytes(output / 'injected.patch', patch.encode('utf-8'))
                data = altered.encode('utf-8')
        write_bytes(target, data)
    argv = [sys.executable, '-I', '-B', str(project / 'tools' / RUNNER.name),
            '--java-home', str(jdk), '--dependencies-json', str(deps),
            '--output', str(mode_dir / 'run')]
    info = {'argv': argv, 'status': 'starting'}
    write_bytes(mode_dir / 'invocation.json', (json.dumps(info, indent=2) + '\n').encode())
    with (mode_dir / 'outer.stdout').open('xb') as stdout, (mode_dir / 'outer.stderr').open('xb') as stderr:
        proc = subprocess.Popen(argv, stdout=stdout, stderr=stderr, start_new_session=True)
        try:
            rc = proc.wait(timeout=180)
        except subprocess.TimeoutExpired:
            # The child was created in its own session. Its PID cannot be reused before wait.
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
            info.update(status='timeout', exit=proc.returncode)
        else:
            info.update(status='finished', exit=rc)
    write_bytes(mode_dir / 'outer-result.json', (json.dumps(info, indent=2) + '\n').encode())
    return info


def line(path, prefix):
    matches = [s for s in path.read_text().splitlines() if s.startswith(prefix)]
    if len(matches) != 1:
        raise ValueError(f'{path}: expected one {prefix!r} line, got {len(matches)}')
    return matches[0]


def verify(output, modes):
    checks = {}
    reports = {}
    for mode in ('baseline', 'early-gate'):
        run = output / mode / 'run'
        report = json.loads((run / 'report.json').read_text())
        reports[mode] = report
        expected = {case: (1 if mode == 'early-gate' and case in RED else 0) for case in CASES}
        expected['compile-all'] = 0
        checks[mode + '_exit'] = modes[mode]['status'] == 'finished' and modes[mode]['exit'] == (0 if mode == 'baseline' else 1)
        checks[mode + '_case_exits'] = {k: v['exit'] for k, v in report['runs'].items()} == expected
        checks[mode + '_inputs_unchanged'] = report['inputs_unchanged'] and report['classpath_unchanged']
        for case in ('1549-collision', '1589-collision', '1549-terrain', '1589-terrain'):
            classes = (run / (case + '.classes.log')).read_text().splitlines()
            for name in ('ControlAuthorityArbiter', 'FormationFlightManager', 'AirspaceSafetyProbe', 'AutopilotSession', 'AutonomousFlightManager'):
                pattern = 'com.wwdebug.autopilot.' + name + ' source:'
                found = [s for s in classes if pattern in s]
                checks[f'{mode}_{case}_{name}_origin'] = len(found) == 1 and str(run / 'production') + '/' in found[0]
    for name, expected_hash in EXPECTED.items():
        rel = Path('project/src/main/java/com/wwdebug/autopilot') / name
        baseline = (output / 'baseline' / rel).read_bytes()
        candidate = (output / 'early-gate' / rel).read_bytes()
        checks['copy_' + name] = digest(baseline) == expected_hash and (candidate == baseline if name != 'FormationFlightManager.java' else candidate == baseline.decode('utf-8').replace(NEEDLE, REPLACEMENT).encode('utf-8'))
    checks['copy_runner'] = all(digest((output / mode / 'project/tools' / RUNNER.name).read_bytes()) == RUNNER_SHA for mode in ('baseline', 'early-gate'))
    for case in RED:
        error = (output / 'early-gate/run' / (case + '.stderr')).read_text()
        checks[case + '_expected_red'] = 'AssertionError: adapter missing' in error
    checks['same_classpath'] = reports['baseline']['classpath_before'] == reports['early-gate']['classpath_before']
    stubsets = []
    for mode in ('baseline', 'early-gate'):
        stubroot = output / mode / 'run/stubs'
        stubsets.append({str(p.relative_to(stubroot)): digest(p.read_bytes()) for p in stubroot.rglob('*.java')})
    checks['same_stubs'] = stubsets[0] == stubsets[1] and bool(stubsets[0])
    for tick in ('1549', '1589'):
        base = output / 'baseline/run' / (tick + '-collision.stdout')
        cand = output / 'early-gate/run' / (tick + '-collision.stdout')
        base_case, cand_case = line(base, 'case='), line(cand, 'case=')
        bw, cw = line(base, 'writes='), line(cand, 'writes=')
        base_parts = bw.removeprefix('writes=[').removesuffix(']').split(',')
        cand_parts = cw.removeprefix('writes=[').removesuffix(']').split(',')
        checks[tick + '_collision_label'] = all('authority=COLLISION_AVOIDANCE' in v and 'collision=true' in v for v in (base_case, cand_case))
        checks[tick + '_base_then_missing_collision_write'] = len(base_parts) == 8 and len(cand_parts) == 4 and [float(v) for v in base_parts[:4]] == [float(v) for v in cand_parts]
        checks[tick + '_collision_adapter_missing'] = 'predicted_aircraft_collision_avoidance' in line(base, 'adapters=') and line(cand, 'adapters=') == 'adapters=[]'
        err = (output / 'early-gate/run' / (tick + '-collision.stderr')).read_text()
        checks[tick + '_expected_red'] = 'AssertionError: adapter missing' in err
        bt = output / 'baseline/run' / (tick + '-terrain.stdout')
        ct = output / 'early-gate/run' / (tick + '-terrain.stdout')
        checks[tick + '_terrain_unchanged'] = all(line(bt, p) == line(ct, p) for p in ('case=', 'writes=', 'adapters='))
    return checks


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--java-home', type=Path, required=True)
    p.add_argument('--dependencies-json', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    out = args.output.absolute()
    # Do not use exist_ok: an existing output, including a symlink, is never modified.
    out.mkdir(mode=0o700)
    result = {'classification': 'INCONCLUSIVE', 'checks': {}, 'error': None}
    try:
        before = source_inputs()
        actual = {name: digest(data) for name, data in before.items()}
        result['source_before'] = actual
        result['wrapper_sha256'] = digest(Path(__file__).read_bytes())
        expected = dict(EXPECTED, runner=RUNNER_SHA)
        if actual != expected:
            raise ValueError('runner or #214 source hash mismatch; no experiment started')
        modes = {}
        result['outer_runs'] = modes
        for mode in ('baseline', 'early-gate'):
            modes[mode] = run_one(mode, out, before, args.java_home.resolve(), args.dependencies_json.resolve())
            if modes[mode]['status'] != 'finished' or (mode == 'baseline' and modes[mode]['exit'] != 0):
                raise RuntimeError(mode + ' did not complete as expected; remaining runs not started')
        result['outer_runs'] = modes
        result['checks'] = verify(out, modes)
        after = {name: digest(data) for name, data in source_inputs().items()}
        result['source_after'] = after
        result['checks']['checkout_inputs_unchanged'] = actual == after
        if all(result['checks'].values()):
            result['classification'] = 'EXPECTED_COLLISION_COUNTEREXAMPLE'
    except Exception as e:
        result['error'] = f'{type(e).__name__}: {e}'
    finally:
        write_bytes(out / 'summary.json', (json.dumps(result, indent=2) + '\n').encode())
    print(result['classification'])
    return 0 if result['classification'] == 'EXPECTED_COLLISION_COUNTEREXAMPLE' else 1


if __name__ == '__main__':
    sys.exit(main())
