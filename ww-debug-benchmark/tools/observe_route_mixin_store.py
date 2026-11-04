#!/usr/bin/env python3
"""Test-only fixed-input bytecode observation; does not run or emulate Mixin."""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OBSERVE = ROOT / 'tools/route_mixin_store/Observe.java'
MANAGER = ROOT / 'src/main/java/com/wwdebug/autopilot/AutonomousFlightManager.java'
MIXIN = ROOT / 'src/main/java/com/wwdebug/benchmark/mixin/AutonomousFlightRouteGuidanceMixin.java'
EXPECTED = {
    'baseline_source': '45a24a85af3d44a1d189a8e0f18fec178f1da4c19639d820b76e75a94488e177',
    'mixin_source': 'f22c5f92edc67dab0443a21cc1fc1c66097abc7f4f4609e9b8a94f8c0b227adb',
    'baseline_class': '0983d9f4662772d2887afd72b7344b14fb3d9173773921d978618954b3225aa5',
    'candidate_source': '121ae543eddbb1841690db670bbe89bd3921a214b84409b9ddcdff2ee25d1ae4',
    'candidate_class': '98fc32d25a7ba64a88accc3f8075159c81000e904417a3dd4663fd97dd69fc93',
}

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def method_instructions(text, method, descriptor, access):
    header = 'METHOD ' + method + descriptor + ' access=' + str(access)
    lines = text.splitlines()
    prefix = 'METHOD ' + method + descriptor + ' access='
    starts = [i for i, line in enumerate(lines) if line.startswith(prefix)]
    if len(starts) != 1:
        raise ValueError('INCONCLUSIVE: expected exactly one method: ' + header)
    if lines[starts[0]] != header:
        raise ValueError('INCONCLUSIVE: unexpected method access: ' + header)
    result = []
    for line in lines[starts[0] + 1:]:
        if line.startswith('METHOD '):
            raise ValueError('INCONCLUSIVE: missing method end: ' + header)
        if line.startswith('MAX '):
            return result
        if re.match(r'^\d+ (?:VAR|INVOKE|INSN) ', line):
            result.append(line)
    raise ValueError('INCONCLUSIVE: missing method end: ' + header)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('baseline-class', 'baseline-provenance', 'candidate-class', 'candidate-source',
                 'candidate-provenance', 'asm-jar', 'java-home', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args()
    output = Path(os.path.abspath(a.output))
    resolved_output = output.resolve()
    if (output == ROOT.parent or ROOT.parent in output.parents
            or resolved_output == ROOT.parent or ROOT.parent in resolved_output.parents):
        raise ValueError('output must be outside the checkout')
    jdk = a.java_home.resolve() / 'bin'
    inputs = {'baseline_source': MANAGER, 'mixin_source': MIXIN,
              'baseline_class': a.baseline_class, 'candidate_source': a.candidate_source,
              'candidate_class': a.candidate_class, 'baseline_provenance': a.baseline_provenance,
              'candidate_provenance': a.candidate_provenance, 'asm_jar': a.asm_jar,
              'java': jdk / 'java', 'javac': jdk / 'javac', 'javap': jdk / 'javap',
              'runner': Path(__file__), 'observer_source': OBSERVE}
    inputs = {k: v.resolve(strict=True) for k, v in inputs.items()}
    before = {k: {'path': str(v), 'sha256': digest(v)} for k, v in inputs.items()}
    for k, expected in EXPECTED.items():
        if before[k]['sha256'] != expected:
            raise ValueError('unexpected fixed-input SHA-256: ' + k)
    baseline = json.loads(inputs['baseline_provenance'].read_text())
    cand = json.loads(inputs['candidate_provenance'].read_text())
    if baseline.get('commit') != '80eab064420c217df66c2d42c3f8772ff4216add':
        raise ValueError('baseline provenance has unexpected commit')
    if baseline['tracked_files_sha256']['ww-debug-benchmark/src/main/java/com/wwdebug/autopilot/AutonomousFlightManager.java'] != EXPECTED['baseline_source']:
        raise ValueError('baseline source not in build provenance')
    if baseline['build_artifacts']['classes/java/main/com/wwdebug/autopilot/AutonomousFlightManager.class']['sha256'] != EXPECTED['baseline_class']:
        raise ValueError('baseline class not in build provenance')
    if not (cand['inputs_unchanged'] and cand['classpath_unchanged']
            and EXPECTED['candidate_source'] in cand['inputs_before'].values()
            and EXPECTED['candidate_class'] in cand['compiled_production'].values()):
        raise ValueError('candidate inputs do not match recorded source-copy build')
    output.mkdir(mode=0o700)
    (output / 'inputs').mkdir(mode=0o700)
    (output / 'classes').mkdir(mode=0o700)
    (output / 'empty').mkdir(mode=0o700)
    snapshots = {}
    for key in ('baseline_source', 'mixin_source', 'baseline_class', 'candidate_source',
                'candidate_class', 'baseline_provenance', 'candidate_provenance', 'observer_source', 'runner'):
        name = key + '.class' if key.endswith('_class') else ('Observe.java' if key == 'observer_source' else key)
        dest = output / 'inputs' / name
        shutil.copyfile(inputs[key], dest)
        if digest(dest) != before[key]['sha256']:
            raise ValueError('input changed while copying: ' + key)
        snapshots[key] = str(dest)
    (output / 'inputs-before.json').write_text(json.dumps(before, indent=2) + '\n')
    commands = {}
    clean_env = {k: v for k, v in os.environ.items() if k not in ('JAVA_TOOL_OPTIONS', '_JAVA_OPTIONS', 'JDK_JAVA_OPTIONS', 'CLASSPATH')}
    def run(label, argv):
        result = subprocess.run(list(map(str, argv)), capture_output=True, env=clean_env, timeout=30)
        (output / (label + '.stdout')).write_bytes(result.stdout)
        (output / (label + '.stderr')).write_bytes(result.stderr)
        commands[label] = {'argv': list(map(str, argv)), 'exit': result.returncode}
        (output / 'commands.json').write_text(json.dumps(commands, indent=2) + '\n')
        if result.returncode:
            raise RuntimeError(label + ' exited ' + str(result.returncode))
    try:
        run('java-version', [inputs['java'], '-version'])
        run('compile', [inputs['javac'], '-encoding', 'UTF-8', '-proc:none', '--release', '17',
                        '-cp', inputs['asm_jar'], '-sourcepath', output / 'empty', '-d', output / 'classes', snapshots['observer_source']])
        for variant in ('baseline', 'candidate'):
            cls = Path(snapshots[variant + '_class'])
            run(variant + '-asm', [inputs['java'], '-verbose:class', '-cp', str(output / 'classes') + os.pathsep + str(inputs['asm_jar']), 'Observe', cls])
            run(variant + '-javap', [inputs['javap'], '-p', '-c', '-l', cls])
        def tick_store(lines):
            for i, line in enumerate(lines[:-1]):
                if ('AutopilotSession.tick(' in line and ')Lcom/wwdebug/autopilot/FlightControlOutput;' in line
                        and re.search(r' VAR opcode=58 slot=\d+ ASTORE$', lines[i + 1])):
                    call_index = int(line.split()[0]); store_index = int(lines[i + 1].split()[0])
                    if store_index == call_index + 1:
                        return {'call': line, 'store': lines[i + 1]}
            raise ValueError('tick return followed by ASTORE not observed')
        baseline_text = (output / 'baseline-asm.stdout').read_text()
        candidate_text = (output / 'candidate-asm.stdout').read_text()
        entity = '(Lnet/minecraft/world/entity/Entity;)'
        base_lines = method_instructions(baseline_text, 'applyControl', entity + 'V', 9)
        candidate_lines = method_instructions(candidate_text, 'applyControl', entity + 'V', 9)
        moved_lines = method_instructions(candidate_text, 'captureControl', entity + 'Lcom/wwdebug/autopilot/AutonomousFlightManager$RecoveryToken;', 8)
        base_tick = tick_store(base_lines)
        moved_tick = tick_store(moved_lines)
        if any(re.search(r' VAR opcode=(?:54|55|56|57|58) ', line) for line in candidate_lines):
            raise ValueError('candidate applyControl unexpectedly contains a STORE')
        if not any('AutonomousFlightManager.captureControl(' in line for line in candidate_lines):
            raise ValueError('candidate wrapper call missing')
        after = {k: {'path': str(v), 'sha256': digest(v)} for k, v in inputs.items()}
        (output / 'inputs-after.json').write_text(json.dumps(after, indent=2) + '\n')
        if before != after:
            raise ValueError('inputs changed during observation')
        result = {'scope': 'Static bytecode only: no transformed Mixin, real aircraft, server, or world',
                  'fixed_sources_and_classes': EXPECTED, 'snapshots': snapshots,
                  'baseline_kind': '#214 Gradle build class; metadata records source and artifact hashes',
                  'candidate_kind': '#207 private stand-in compilation; report records source and class hashes',
                  'baseline_tick_store': base_tick, 'candidate_moved_tick_store': moved_tick,
                  'candidate_apply_store_count': 0,
                  'note': 'Inspect ASM/javap raw methods; type-based Mixin ordinal is not emulated.'}
        (output / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
        artifacts = {str(f.relative_to(output)): digest(f) for f in sorted(output.rglob('*')) if f.is_file()}
        (output / 'artifact-hashes.json').write_text(json.dumps(artifacts, indent=2) + '\n')
    except Exception as exc:
        (output / 'failure.json').write_text(json.dumps({'classification': 'INCONCLUSIVE', 'type': type(exc).__name__, 'message': str(exc)}, indent=2) + '\n')
        raise
    print('Saved observation to', output)
    return 0

if __name__ == '__main__':
    sys.exit(main())
