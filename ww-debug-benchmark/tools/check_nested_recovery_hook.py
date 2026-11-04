#!/usr/bin/env python3
"""Test that a copied recovery runner rejects a missing nested cleanup hook.

The hook is removed only from an experimental source copy. No Minecraft, Gradle,
world, or production change is involved. A zero exit is a fixture check, not a
safety verdict; unexpected outcomes are INCONCLUSIVE and remain on disk.
"""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
NAMES = ('ControlAuthorityArbiter', 'FormationFlightManager', 'AirspaceSafetyProbe',
         'MobPilotGate', 'ControlOutcome', 'ControlProposal', 'FlightControlOutput',
         'FlightPhase', 'AutopilotSession', 'FlightProfile', 'AutonomousFlightManager')
NEEDLE = '    static boolean hasCaptureForTest() { return RECOVERY_CAPTURE.get()!=null; }\n'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runner', type=Path, default=ROOT / 'tools/observe_formation_recovery_frame.py')
    parser.add_argument('--java-home', type=Path, required=True)
    parser.add_argument('--dependencies-json', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.absolute()
    out.mkdir(mode=0o700)  # Existing output, including symlinks, is refused.
    report = {'classification': 'INCONCLUSIVE', 'error': None, 'checks': {}}
    try:
        runner = args.runner.resolve()
        jdk = args.java_home.resolve() / 'bin'
        deps = args.dependencies_json.resolve()
        inputs = [runner, Path(__file__).resolve(), jdk / 'java', jdk / 'javac', jdk / 'javap', deps]
        originals = [ROOT / 'src/main/java/com/wwdebug/autopilot' / (n + '.java') for n in NAMES]
        inputs += originals
        report['inputs_before'] = {str(p): sha(p) for p in inputs}
        text = runner.read_text()
        if text.count(NEEDLE) != 1:
            raise ValueError('expected exactly one generated candidate hook')
        changed = text.replace(NEEDLE, '')
        (out / 'hook-removal.patch').write_text(''.join(difflib.unified_diff(
            text.splitlines(True), changed.splitlines(True), fromfile='runner', tofile='runner_without_hook')))
        project = out / 'project'
        source = project / 'src/main/java/com/wwdebug/autopilot'
        source.mkdir(parents=True)
        (project / 'tools').mkdir()
        copied_runner = project / 'tools/runner_without_hook.py'
        copied_runner.write_text(changed)
        for original in originals:
            (source / original.name).write_bytes(original.read_bytes())
        argv = [sys.executable, '-I', '-B', str(copied_runner), '--mode', 'nested',
                '--java-home', str(args.java_home.resolve()), '--dependencies-json', str(deps),
                '--output', str(out / 'run')]
        report['runner_argv'] = argv
        with (out / 'runner.stdout').open('xb') as stdout, (out / 'runner.stderr').open('xb') as stderr:
            process = subprocess.run(argv, stdout=stdout, stderr=stderr, timeout=90)
        report['runner_exit'] = process.returncode
        run = json.loads((out / 'run/report.json').read_text())
        javap_argv = [str(jdk / 'javap'), '-p', '-classpath', str(out / 'run/production'),
                      'com.wwdebug.autopilot.AutonomousFlightManager']
        report['javap_argv'] = javap_argv
        javap = subprocess.run(javap_argv, capture_output=True, text=True, timeout=30)
        (out / 'javap.stdout').write_text(javap.stdout)
        (out / 'javap.stderr').write_text(javap.stderr)
        generated = out / 'run/source-copy/com/wwdebug/autopilot/AutonomousFlightManager.java'
        error = (out / 'run/nested-arbiter.stderr').read_text()
        report['inputs_after'] = {str(p): sha(p) for p in inputs}
        checks = {
            'runner_rejected': process.returncode == 1 and run['classification'] == 'INCONCLUSIVE',
            'compile_succeeded': run['runs']['compile-all']['exit'] == 0,
            'nested_failed': run['runs']['nested-arbiter']['exit'] == 1,
            'expected_exception': 'AssertionError: nested cleanup hook missing' in error and 'NoSuchMethodException' in error,
            'hook_missing_in_source': 'static boolean hasCaptureForTest()' not in generated.read_text(),
            'hook_missing_in_class': javap.returncode == 0 and 'hasCaptureForTest' not in javap.stdout,
            'source_inputs_unchanged': report['inputs_before'] == report['inputs_after'],
            'runner_inputs_unchanged': run['inputs_unchanged'] and run['classpath_unchanged'],
        }
        report['checks'] = checks
        if all(checks.values()):
            report['classification'] = 'EXPECTED_HOOK_REJECTION_NOT_SAFETY'
    except Exception as e:
        report['error'] = type(e).__name__ + ': ' + str(e)
    finally:
        (out / 'checker-report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(report['classification'])
    return 0 if report['classification'] == 'EXPECTED_HOOK_REJECTION_NOT_SAFETY' else 1


if __name__ == '__main__':
    sys.exit(main())
