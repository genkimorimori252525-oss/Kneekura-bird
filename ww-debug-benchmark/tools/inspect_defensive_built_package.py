#!/usr/bin/env python3
"""Inspect known build descriptors and exact fake bytes, not runtime behavior."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import zipfile

import defensive_built_tools as tools

EXPECTED = {
    'ControlAuthorityArbiter': '(Lnet/minecraft/world/entity/Entity;)Lcom/wwdebug/autopilot/ControlAuthorityArbiter$Authority;',
    'FighterCombatFacade': '(Lnet/minecraft/world/entity/Entity;Z)Lcom/wwdebug/autopilot/ControlOutcome;',
    'DefensiveAirCombatManager': '(Lnet/minecraft/world/entity/Entity;)Ljava/util/Optional;',
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ('evidence', 'manifest', 'build-classes', 'java-home', 'jar', 'report'):
        parser.add_argument('--' + option, type=Path, required=True)
    parser.add_argument('--jar-sha256', required=True)
    args = parser.parse_args()
    evidence, build, jar = args.evidence.resolve(strict=True), args.build_classes.resolve(strict=True), args.jar.resolve(strict=True)
    manifest = json.loads(args.manifest.read_text())
    javap = args.java_home.resolve(strict=True) / 'bin/javap'
    if not re.fullmatch(r'[0-9a-f]{64}', args.jar_sha256) or tools.digest(jar) != args.jar_sha256:
        raise ValueError('jar hash mismatch before inspection')
    target_dir = build / 'com/wwdebug/autopilot'
    targets = [target_dir / n for n in tools.TARGETS]
    before = tools.inventory(targets + [javap, jar])
    if {x.name: tools.digest(x) for x in targets} != manifest['build_classes']:
        raise ValueError('build class hashes differ from caller manifest')
    descriptors = {}
    for name, expected in EXPECTED.items():
        argv = [str(javap), '-classpath', str(build), '-p', '-s', 'com.wwdebug.autopilot.' + name]
        result = subprocess.run(argv, capture_output=True, text=True, timeout=30)
        lines = result.stdout.splitlines()
        matches = [(line.strip(), lines[i + 1].strip()) for i, line in enumerate(lines[:-1])
                   if re.search(r'\bapplyControl\(', line) and line.strip().startswith('public static ')
                   and lines[i + 1].strip() == 'descriptor: ' + expected]
        descriptors[name] = {'argv': argv, 'exit': result.returncode, 'matches': len(matches),
                             'stdout_sha256': hashlib.sha256(result.stdout.encode()).hexdigest(),
                             'stderr_sha256': hashlib.sha256(result.stderr.encode()).hexdigest()}
        if result.returncode != 0 or len(matches) != 1:
            raise ValueError('descriptor mismatch for ' + name)
    fake_hashes, fixture_files = set(), []
    for suite in tools.SUITES:
        root = evidence / suite
        report = json.loads((root / 'report.json').read_text())
        stage = root / 'classes'
        if report['stage_after_all'] != tools.inventory(sorted(p for p in stage.rglob('*') if p.is_file())):
            raise ValueError('fixture class hashes changed')
        for source in (root / 'stubs').rglob('*.java'):
            directory, name = stage / source.relative_to(root / 'stubs').parent, source.stem
            matches = [p for p in directory.glob('*.class')
                       if p.name == name + '.class' or p.name.startswith(name + '$')]
            if not matches:
                raise ValueError('fake source has no matching class')
            fixture_files.extend([source, *matches])
            fake_hashes.update(tools.digest(p) for p in matches)
    fake_before = tools.inventory(fixture_files)
    with zipfile.ZipFile(jar) as archive:
        entries = tools.bounded_jar_entries(archive, 20000, 64 * 1024 * 1024, 16 * 1024 * 1024)
        names = {entry.filename for entry in entries}
        expected_entries = {'com/wwdebug/autopilot/' + n for n in tools.TARGETS}
        forbidden = [name for name in names if name == 'com/wwdebug/autopilot/Probe.class'
                     or name.startswith('com/wwdebug/autopilot/Probe$')]
        hits = [entry.filename for entry in entries if entry.filename.endswith('.class')
                and hashlib.sha256(archive.read(entry)).hexdigest() in fake_hashes]
        if expected_entries - names or forbidden or hits:
            raise ValueError('missing target, known fake name or exact fake byte hash in jar')
    after = tools.inventory(targets + [javap, jar])
    fake_after = tools.inventory(fixture_files)
    if before != after or fake_before != fake_after:
        raise ValueError('inspection inputs changed')
    report_path = args.report.resolve()
    repo = Path(__file__).resolve().parents[1]
    if report_path.is_relative_to(evidence) or report_path.is_relative_to(repo):
        raise ValueError('report must be outside evidence and checkout')
    with report_path.open('x', encoding='utf-8') as f:
        json.dump({'valid': True, 'descriptors': descriptors, 'jar_sha256': args.jar_sha256,
                   'target_entries': len(tools.TARGETS), 'fake_unique_hashes': len(fake_hashes),
                   'inputs_before': before, 'inputs_after': after, 'fake_before': fake_before, 'fake_after': fake_after,
                   'scope': 'entry presence, Probe name and exact fake bytes only; reobfuscation and runtime unproved'}, f, indent=2)
        f.write('\n')
    print('inspected supplied build package')
    return 0

if __name__ == '__main__':
    sys.exit(main())
