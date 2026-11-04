#!/usr/bin/env python3
"""Check local built-fixture observations; never use on untrusted evidence paths."""
import argparse
import json
import os
from pathlib import Path
import re
import sys

import defensive_built_tools as tools


def read_text(path, limit=64 * 1024 * 1024):
    if path.stat().st_size > limit:
        raise ValueError('evidence file exceeds size limit')
    return path.read_text(encoding='utf-8')


def verify_suite(root, suite, manifest, generation, source_root, java_home, dependencies_json, build_classes, dependencies):
    directory = root / suite
    report = json.loads(read_text(directory / 'report.json'))
    entry = generation['suites'][suite]
    expected_source = source_root / 'tools' / f'inspect_defensive_identity_{suite}.py'
    generated = root / f'{suite}.py'
    if (tools.digest(expected_source) != manifest['runners'][suite]
            or entry['original_sha256'] != manifest['runners'][suite]
            or entry['transform_anchor_counts'] != [1, 1, 1, 1, 1]
            or generated.read_bytes() != tools.generate(expected_source.read_bytes(), source_root / 'src/main/java')
            or tools.digest(generated) != entry['generated_sha256']
            or entry['generated_sha256'] != entry['generated_sha256_after']
            or report['runner_snapshot_sha256'] != entry['generated_sha256']):
        raise ValueError(suite + ': runner generation mismatch')
    for label in ('stdout', 'stderr'):
        path = root / f'{suite}.outer.{label}'
        if tools.digest(path) != entry[f'outer_{label}_sha256']:
            raise ValueError(suite + ': outer output changed')
    expected_wrapper = [sys.executable, str(generated), '--java-home', str(java_home),
                        '--dependencies-json', str(dependencies_json), '--policy', 'actual',
                        '--build-classes', str(build_classes), '--output', str(directory)]
    if entry['argv'] != expected_wrapper:
        raise ValueError(suite + ': wrapper argv mismatch')
    if entry['exit'] != (1 if suite == 'exceptions' else 0):
        raise ValueError(suite + ': unexpected outer exit')
    if (report['policy'] != 'actual' or not report['source_copy_equal'] or report['patch_files']
            or list(directory.glob('*.patch')) or not report['inputs_unchanged']
            or report['inputs_before'] != report['inputs_after'] or not report['classpath_unchanged']
            or report['classpath_before'] != report['classpath_after']
            or report['classpath_before'] != manifest['classpath']):
        raise ValueError(suite + ': source/classpath precondition failed')
    copies = directory / 'source-copy/com/wwdebug/autopilot'
    for name, expected in manifest['sources'].items():
        if tools.digest(copies / name) != expected:
            raise ValueError(suite + ': copied source differs from manifest')
    if report['build_class_before'] != report['build_class_after']:
        raise ValueError(suite + ': supplied build changed')
    build = {Path(k).name: v for k, v in report['build_class_before'].items()}
    replaced = {Path(k).name: v for k, v in report['fixture_class_replaced'].items()}
    if (build != manifest['build_classes'] or replaced != build
            or report['fixture_class_replaced'] != report['fixture_class_after']):
        raise ValueError(suite + ': target class hash mismatch')
    stage = directory / 'classes'
    stage_now = tools.inventory(sorted(p for p in stage.rglob('*') if p.is_file()))
    if (not stage_now or report['stage_after_replacement'] != stage_now
            or report['stage_after_all'] != stage_now):
        raise ValueError(suite + ': staged class files changed')
    expected_cases = set(tools.case_names(suite))
    runs = report['runs']
    if set(runs) != expected_cases | {'compile'} or runs['compile']['exit'] != 0:
        raise ValueError(suite + ': case set or compile result differs')
    classpath = os.pathsep.join(str(p) for p in dependencies)
    copies_list = [str(copies / (n + '.java')) for n in tools.SOURCE_NAMES]
    stub_dir = directory / 'stubs'
    stub_files = {str(p) for p in stub_dir.rglob('*.java')}
    if any(report['inputs_before'].get(path) != tools.digest(path) for path in stub_files):
        raise ValueError(suite + ': fake source changed after observation')
    compile_argv = runs['compile']['argv']
    expected_prefix = [str(java_home / 'bin/javac'), '-proc:none', '--release', '17', '-cp',
                       classpath, '-sourcepath', str(directory / 'empty'), '-d', str(stage)]
    if (compile_argv[:len(expected_prefix)] != expected_prefix
            or compile_argv[len(expected_prefix):len(expected_prefix) + len(copies_list)] != copies_list):
        raise ValueError(suite + ': compile argv mismatch')
    stub_args = compile_argv[len(expected_prefix) + len(copies_list):]
    if len(stub_args) != len(stub_files) or set(stub_args) != stub_files:
        raise ValueError(suite + ': compile stub argv mismatch')
    compile_outputs = [directory / 'compile.stdout', directory / 'compile.stderr']
    if tools.inventory(compile_outputs) != runs['compile']['outputs_immediate']:
        raise ValueError(suite + ': compile output changed')
    targets = {'com.wwdebug.autopilot.' + n.removesuffix('.class') for n in tools.TARGETS}
    observed = set()
    for name in sorted(expected_cases):
        case = runs[name]
        expected_argv = [str(java_home / 'bin/java'), '-Xmx128m', '-Xverify:all',
                         '-Xlog:class+load=info:file=' + str(directory / (name + '.classes.log')),
                         '-cp', str(stage) + os.pathsep + classpath, 'com.wwdebug.autopilot.Probe', name]
        if case['argv'] != expected_argv:
            raise ValueError(suite + ': case argv mismatch for ' + name)
        if case['stage_before'] != stage_now:
            raise ValueError(suite + ': stage changed before ' + name)
        paths = [directory / (name + suffix) for suffix in ('.stdout', '.stderr', '.classes.log')]
        if tools.inventory(paths) != case['outputs_immediate']:
            raise ValueError(suite + ': observed output changed for ' + name)
        stdout, stderr, log = (read_text(p) for p in paths)
        if not tools.expected_case(suite, name, case['exit'], stdout, stderr):
            raise ValueError(suite + ': unexpected exit or sentinel in ' + name)
        loaded = set()
        for line in log.splitlines():
            match = re.match(r'^\[[^]]+\]\[info\]\[class,load\] (\S+) source: (\S+)$', line)
            if not match:
                if '[class,load]' in line and any(p in line for p in tools.PREFIXES):
                    raise ValueError(suite + ': malformed target class-load line')
                continue
            clazz, uri = match.groups()
            if '$$Lambda$' in clazz:
                continue  # dynamically generated class source is not proven here
            fake = clazz in ('com.wwdebug.autopilot.Probe', 'net.minecraft.world.entity.Entity',
                             'com.wwdebug.benchmark.ReflectiveAircraft')
            if clazz in targets or fake:
                if clazz in loaded or not tools.same_dir_uri(uri, stage):
                    raise ValueError(suite + ': class origin mismatch for ' + clazz)
                loaded.add(clazz)
                if clazz in targets:
                    observed.add(clazz)
            elif any(clazz.startswith('com.wwdebug.autopilot.' + p + '$') for p in tools.PREFIXES):
                raise ValueError(suite + ': unknown target nested class')
        if not {'com.wwdebug.autopilot.Probe', 'net.minecraft.world.entity.Entity'} <= loaded:
            raise ValueError(suite + ': fixture class was not observed')
    return observed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ('evidence', 'manifest', 'build-classes', 'dependencies-json', 'java-home', 'report'):
        parser.add_argument('--' + option, type=Path, required=True)
    args = parser.parse_args()
    root, repo = args.evidence.resolve(strict=True), Path(__file__).resolve().parents[1]
    manifest = json.loads(read_text(args.manifest))
    dependencies = [Path(x) for x in json.loads(read_text(args.dependencies_json))]
    current_inputs = tools.verify_inputs(repo, args.build_classes.resolve(), dependencies, manifest)
    generation = json.loads(read_text(root / 'generation.json'))
    fixed_paths = [args.manifest.resolve(), args.dependencies_json.resolve(), Path(tools.__file__).resolve(), Path(sys.executable).resolve()]
    if (generation['fixed_before'] != tools.inventory(fixed_paths)
            or generation['inputs_before'] != current_inputs
            or tools.digest(args.manifest) != generation['manifest_sha256']
            or generation['manifest_sha256'] != generation['manifest_sha256_after']
            or not generation['inputs_unchanged'] or generation['inputs_before'] != generation['inputs_after']
            or generation['fixed_before'] != generation['fixed_after']):
        raise ValueError('generation manifest or inputs changed')
    observed = set()
    for suite in tools.SUITES:
        observed.update(verify_suite(root, suite, manifest, generation, repo, args.java_home.resolve(),
                                     args.dependencies_json.resolve(), args.build_classes.resolve(), dependencies))
    expected = {'com.wwdebug.autopilot.' + n.removesuffix('.class') for n in tools.TARGETS}
    if observed != expected:
        raise ValueError('observed target class union differs from expected')
    report_path = args.report.resolve()
    if report_path.is_relative_to(root) or report_path.is_relative_to(repo.resolve()):
        raise ValueError('report must be outside evidence and checkout')
    with report_path.open('x', encoding='utf-8') as f:
        json.dump({'valid': True, 'suites': list(tools.SUITES), 'targets': sorted(observed),
                   'scope': 'local fake fixtures; observations do not prove runtime or build provenance'}, f, indent=2)
        f.write('\n')
    print('verified local fake fixture evidence')
    return 0

if __name__ == '__main__':
    sys.exit(main())
