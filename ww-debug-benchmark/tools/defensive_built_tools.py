#!/usr/bin/env python3
"""Run fixed defensive fixtures against supplied build classes; not a MOD test."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import quote, unquote, urlsplit

SUITES = ('matrix', 'exceptions', 'wrappers', 'level_exceptions', 'null')
PREFIXES = ('ControlAuthorityArbiter', 'FighterCombatFacade', 'DefensiveAirCombatManager')
SOURCE_NAMES = ('ControlAuthorityArbiter', 'FormationFlightManager', 'AirspaceSafetyProbe',
                'MobPilotGate', 'ControlOutcome', 'ControlProposal', 'FlightControlOutput',
                'FlightPhase', 'AutopilotSession', 'FlightProfile', 'AutonomousFlightManager',
                'FighterCombatFacade', 'DefensiveAirCombatManager', 'DefensiveAirCombatAction')
TARGETS = ('ControlAuthorityArbiter.class', 'ControlAuthorityArbiter$Authority.class',
           'ControlAuthorityArbiter$DefensiveAttempt.class', 'ControlAuthorityArbiter$PendingDecision.class',
           'FighterCombatFacade.class', 'FighterCombatFacade$CombatEvaluation.class',
           'DefensiveAirCombatManager.class', 'DefensiveAirCombatManager$1.class',
           'DefensiveAirCombatManager$DefensiveEvaluation.class', 'DefensiveAirCombatManager$State.class',
           'DefensiveAirCombatManager$Threat.class')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def replace_once(text, old, new):
    count = text.count(old)
    if count != 1:
        raise ValueError(f'transform anchor occurs {count} times, expected exactly one')
    return text.replace(old, new, 1)


def same_dir_uri(uri, expected):
    try:
        parsed = urlsplit(uri)
        if (parsed.scheme != 'file' or parsed.netloc or parsed.query or parsed.fragment
                or re.search(r'%(?![0-9a-fA-F]{2})', parsed.path)):
            return False
        path = unquote(parsed.path, errors='strict')
        return path == str(expected) + '/' and quote(path, safe='/') == parsed.path and '\\' not in path
    except (ValueError, UnicodeError):
        return False


def expected_case(suite, case, code, stdout, stderr):
    if suite == 'exceptions':
        if '-def-' in case or '-gate-' in case:
            return code == 1 and 'SENTINEL:' + case in stderr
        return code == 0 and 'OBSERVATION_NO_SENTINEL_THROW' in stdout and 'SENTINEL:' + case not in stderr
    if suite == 'level_exceptions':
        return code == 0 and 'OBSERVATION_NO_SENTINEL_THROW' in stdout and 'SENTINEL:' + case not in stderr
    return code == 0


def case_names(suite):
    cases = {
        'matrix': ('defense-swap', 'defense-same-uuid', 'defense-level', 'defense-same',
                   'defense-claimed', 'defense-player', 'defense-empty', 'defense-client',
                   'defense-removed', 'initial-player', 'initial-empty', 'initial-client',
                   'terrain', 'collision', 'risk-only', 'offensive', 'energy', 'energy-claimed', 'energy-direct'),
        'exceptions': tuple('defense-throw-' + site + '-' + getter + '-' + kind
                            for site in ('def', 'gate', 'rejected') for getter in ('pilot', 'level')
                            for kind in ('runtime', 'error')),
        'wrappers': ('wrapper-defensive', 'wrapper-facade', 'wrapper-defensive-empty',
                     'wrapper-facade-empty', 'wrapper-facade-risk', 'defense-same', 'defense-swap'),
        'level_exceptions': tuple('defense-throw-rejected-' + getter + '-levelswap-' + kind
                                  for getter in ('pilot', 'level') for kind in ('runtime', 'error')),
        'null': ('null-pilot', 'null-level', 'null-both', 'valid'),
    }
    if suite not in cases:
        raise ValueError('unknown suite')
    return cases[suite]


def inventory(paths):
    return {str(p): digest(p) for p in paths}


def classpath_inventory(entries):
    files = []
    for entry in entries:
        if entry.is_symlink():
            raise ValueError('classpath symlink is not supported')
        if entry.is_dir():
            children = sorted(entry.rglob('*'))
            if any(child.is_symlink() for child in children):
                raise ValueError('classpath symlink is not supported')
            files.extend(child for child in children if child.is_file())
        elif entry.is_file():
            files.append(entry)
        else:
            raise ValueError('classpath entry is not a file or directory')
    return inventory(files)


def bounded_jar_entries(archive, max_entries, max_total, max_entry):
    entries = archive.infolist()
    names = [entry.filename for entry in entries]
    if (len(entries) > max_entries or len(set(names)) != len(names)
            or any(entry.file_size > max_entry or entry.file_size < 0 for entry in entries)
            or sum(entry.file_size for entry in entries) > max_total):
        raise ValueError('jar entry count, size or duplicate-name limit exceeded')
    return entries


def require_expected(actual, expected, label):
    if not isinstance(expected, dict) or actual != expected:
        raise ValueError(label + ' hashes differ from caller manifest')


def verify_inputs(repo, build_root, dependencies, manifest):
    runners = {s: digest(repo / 'tools' / f'inspect_defensive_identity_{s}.py') for s in SUITES}
    source_dir = repo / 'src/main/java/com/wwdebug/autopilot'
    sources = {n + '.java': digest(source_dir / (n + '.java')) for n in SOURCE_NAMES}
    build_dir = build_root / 'com/wwdebug/autopilot'
    found = {p.name for p in build_dir.glob('*.class') if any(
        p.name == n + '.class' or p.name.startswith(n + '$') for n in PREFIXES)}
    if found != set(TARGETS):
        raise ValueError('build class set differs from fixed target set')
    built = {n: digest(build_dir / n) for n in TARGETS}
    deps = classpath_inventory(dependencies)
    if [str(p) for p in dependencies] != manifest.get('classpath_order'):
        raise ValueError('classpath order differs from caller manifest')
    for name, actual in (('runners', runners), ('sources', sources), ('build_classes', built), ('classpath', deps)):
        require_expected(actual, manifest.get(name), name)
    return {'runners': runners, 'sources': sources, 'build_classes': built, 'classpath': deps}


def generate(original, source_root):
    """Instrument a byte-verified upstream test runner; every insertion is exact once."""
    text = original.decode('utf-8')
    old = 'ROOT=pathlib.Path(__file__).resolve().parents[1]/"src/main/java"'
    text = replace_once(text, old, 'ROOT=pathlib.Path(' + repr(str(source_root)) + ')')
    old = "p.add_argument('--policy',choices=['baseline','candidate','actual'],required=True);a=p.parse_args()"
    new = "p.add_argument('--policy',choices=['actual'],required=True);p.add_argument('--build-classes',type=pathlib.Path,required=True);a=p.parse_args()"
    text = replace_once(text, old, new)
    old = "  r=subprocess.run(command,cwd=out,capture_output=True,text=True,timeout=30);(out/(name+'.stdout')).write_text(r.stdout);(out/(name+'.stderr')).write_text(r.stderr);report['runs'][name]={'argv':command,'exit':r.returncode};print(name,r.returncode,flush=True);return r.returncode"
    new = "  staged_before=inventory([classes]);r=subprocess.run(command,cwd=out,capture_output=True,text=True,timeout=30);stdout=out/(name+'.stdout');stderr=out/(name+'.stderr');stdout.write_text(r.stdout);stderr.write_text(r.stderr);log=out/(name+'.classes.log');outputs=[stdout,stderr]+([log] if log.exists() else []);report['runs'][name]={'argv':command,'exit':r.returncode,'stage_before':staged_before,'outputs_immediate':inventory(outputs)};print(name,r.returncode,flush=True);return r.returncode"
    text = replace_once(text, old, new)
    insertion = ''' if rc==0:
  build_dir=a.build_classes.resolve()/'com/wwdebug/autopilot';fixture_dir=classes/'com/wwdebug/autopilot';prefixes=('ControlAuthorityArbiter','FighterCombatFacade','DefensiveAirCombatManager')
  def target_names(directory):
   return sorted(x.name for x in directory.glob('*.class') if any(x.name==p+'.class' or (x.name.startswith(p+'$') and x.name.endswith('.class')) for p in prefixes))
  built_names=target_names(build_dir);fixture_names=target_names(fixture_dir)
  if not built_names or built_names!=fixture_names or not all(p+'.class' in built_names for p in prefixes):raise RuntimeError('build/fixture target class set mismatch')
  built=[build_dir/n for n in built_names];destination=[fixture_dir/n for n in built_names]
  report['build_class_before']=inventory(built);report['fixture_class_before']=inventory(destination)
  for source,target in zip(built,destination):shutil.copyfile(source,target)
  report['fixture_class_replaced']=inventory(destination);report['stage_after_replacement']=inventory([classes])
  if any(digest(x)!=digest(y) for x,y in zip(built,destination)):raise RuntimeError('build bytes replacement mismatch')
'''
    text = replace_once(text, ' if rc==0:\n  for case in CASES:', insertion + ' if rc==0:\n  for case in CASES:')
    old = "report['compiled_classes']=inventory([classes]);report['runner_snapshot_sha256']"
    new = "report['compiled_classes']=inventory([classes]);report['build_class_after']=inventory(built) if rc==0 else {};report['fixture_class_after']=inventory(destination) if rc==0 else {};report['stage_after_all']=inventory([classes]);report['runner_snapshot_sha256']"
    return replace_once(text, old, new).encode('utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ('output', 'java-home', 'dependencies-json', 'build-classes', 'manifest'):
        parser.add_argument('--' + option, type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    if output.resolve().is_relative_to(repo.resolve()):
        raise ValueError('output must be outside the checkout')
    manifest = json.loads(args.manifest.read_text())
    dependencies = [Path(x) for x in json.loads(args.dependencies_json.read_text())]
    if not dependencies or any(not x.is_absolute() or not x.exists() for x in dependencies):
        raise ValueError('classpath entries must be existing absolute paths')
    before = verify_inputs(repo, args.build_classes.resolve(), dependencies, manifest)
    manifest_hash = digest(args.manifest)
    fixed_paths = [args.manifest.resolve(), args.dependencies_json.resolve(), Path(__file__).resolve(), Path(sys.executable).resolve()]
    fixed_before = inventory(fixed_paths)
    output.mkdir(mode=0o700)
    metadata = {'scope': 'fake fixture, no runtime or build provenance proof',
                'manifest_sha256': manifest_hash, 'inputs_before': before, 'fixed_before': fixed_before, 'suites': {}}
    for suite in SUITES:
        source = repo / 'tools' / f'inspect_defensive_identity_{suite}.py'
        original = source.read_bytes()
        if hashlib.sha256(original).hexdigest() != before['runners'][suite]:
            raise ValueError('runner changed during generation')
        generated = generate(original, repo / 'src/main/java')
        runner = output / f'{suite}.py'
        runner.write_bytes(generated)
        argv = [sys.executable, str(runner), '--java-home', str(args.java_home.resolve()),
                '--dependencies-json', str(args.dependencies_json.resolve()), '--policy', 'actual',
                '--build-classes', str(args.build_classes.resolve()), '--output', str(output / suite)]
        result = subprocess.run(argv, capture_output=True, timeout=900)
        stdout, stderr = output / f'{suite}.outer.stdout', output / f'{suite}.outer.stderr'
        stdout.write_bytes(result.stdout)
        stderr.write_bytes(result.stderr)
        metadata['suites'][suite] = {'original_sha256': before['runners'][suite],
                                     'generated_sha256': hashlib.sha256(generated).hexdigest(), 'generated_sha256_after': digest(runner),
                                     'transform_anchor_counts': [1, 1, 1, 1, 1], 'argv': argv,
                                     'exit': result.returncode, 'outer_stdout_sha256': digest(stdout),
                                     'outer_stderr_sha256': digest(stderr)}
    metadata['inputs_after'] = verify_inputs(repo, args.build_classes.resolve(), dependencies, manifest)
    metadata['manifest_sha256_after'] = digest(args.manifest)
    metadata['fixed_after'] = inventory(fixed_paths)
    metadata['inputs_unchanged'] = (metadata['inputs_before'] == metadata['inputs_after']
                                    and fixed_before == metadata['fixed_after']
                                    and all(x['generated_sha256'] == x['generated_sha256_after']
                                            for x in metadata['suites'].values()))
    (output / 'generation.json').write_text(json.dumps(metadata, indent=2) + '\n')
    good = metadata['inputs_unchanged'] and all(metadata['suites'][s]['exit'] == (1 if s == 'exceptions' else 0) for s in SUITES)
    return 0 if good else 1

if __name__ == '__main__':
    sys.exit(main())
