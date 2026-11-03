#!/usr/bin/env python3
"""Fixed isolated GameTest launcher. This is not a sandbox or isolation proof."""
import argparse
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import secrets
import shutil
import stat
import subprocess
import sys
import tarfile

# Local module is resolved from this script, never from PYTHONPATH in the CLI.
sys.path.insert(0, str(Path(__file__).absolute().parent))
from safe_preflight import check_no_symlink, check_regular_file, create_private_scratch

BASE = '10923117a121382c93f2f888554e178c0478a96a'
MODS = {
    'immersive_aircraft-1.3.3+1.20.1-forge.jar': 'd1f7cfeed3ac2cf69472ae756eb9189dad04ab21b8afbd443c82f40e51bbf065',
    'warfare_wings-1.1.4-1.20.1-forge.jar': '3b6b245e703862517fe7aae6acd95ccafc865e1e81ba7a26e2b9abcfe1120187',
}


def read_private_regular(path, expected_identity=None):
    check_no_symlink(path)
    info = os.lstat(path)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 128 * 1024 * 1024:
        raise ValueError('source must be a bounded single-link regular file')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        actual = os.fstat(fd)
        identity = actual.st_dev, actual.st_ino
        if (not stat.S_ISREG(actual.st_mode) or actual.st_nlink != 1
                or identity != (info.st_dev, info.st_ino)
                or (expected_identity is not None and identity != expected_identity)):
            raise ValueError('source changed while opening')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            data = stream.read(128 * 1024 * 1024 + 1)
        if len(data) > 128 * 1024 * 1024:
            raise ValueError('source grew beyond size limit')
        return data
    finally:
        os.close(fd)


def write_new(path, data, mode=0o600):
    check_no_symlink(path.parent)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    with os.fdopen(fd, 'wb') as out:
        out.write(data)
        out.flush()
        os.fsync(out.fileno())
        info = os.fstat(out.fileno())
        return info.st_dev, info.st_ino


def open_log_append(path, expected_identity):
    check_no_symlink(path)
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or (info.st_dev, info.st_ino) != expected_identity:
            raise ValueError('log identity changed; preserve scratch')
        return os.fdopen(fd, 'ab')
    except BaseException:
        os.close(fd)
        raise


def copy_checked(source, destination, digest):
    check_regular_file(source, digest)
    content = read_private_regular(source)
    if hashlib.sha256(content).hexdigest() != digest:
        raise ValueError('input changed while copying')
    write_new(destination, content)
    check_regular_file(destination, digest)


def extract_project(archive, scratch):
    """Extract only regular files from the immutable git archive; never create run-gametest."""
    root = scratch / 'ww-debug-benchmark'
    with tarfile.open(fileobj=io.BytesIO(archive), mode='r:') as bundle:
        members = bundle.getmembers()
        if not members or len(members) > 5000:
            raise ValueError('invalid source archive')
        total = 0
        seen = set()
        for item in members:
            parts = Path(item.name).parts
            if not parts or parts[0] != 'ww-debug-benchmark' or '..' in parts or Path(item.name).is_absolute():
                raise ValueError('unexpected archive path')
            if len(parts) >= 2 and parts[1] == 'run-gametest':
                continue
            if item.name in seen:
                raise ValueError('duplicate archive member')
            seen.add(item.name)
            if not (item.isdir() or item.isfile()):
                raise ValueError('archive links and special files rejected')
            total += item.size
            if total > 32 * 1024 * 1024:
                raise ValueError('source archive exceeds size limit')
            target = scratch.joinpath(*parts)
            if item.isdir():
                target.mkdir(mode=0o700, parents=True, exist_ok=True)
            else:
                target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                data = bundle.extractfile(item)
                if data is None:
                    raise ValueError('archive member unreadable')
                write_new(target, data.read(), 0o700 if item.mode & 0o111 else 0o600)
    if not root.is_dir() or os.path.lexists(root / 'run-gametest'):
        raise ValueError('new project/run directory requirement failed')
    return root


def reject_gradle_user_config(home):
    # The Cloud environment's shared cache is not an isolated experiment home.
    shared_cloud_home = Path('/workspace/.cloud-setup/gradle-home')
    if home == shared_cloud_home or shared_cloud_home in home.parents or home in shared_cloud_home.parents:
        raise ValueError('the shared Cloud Gradle home or its ancestor/descendant is forbidden')
    check_no_symlink(home)
    if not home.is_dir():
        raise ValueError('Gradle user home must exist')
    info = os.stat(home)
    if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077:
        raise ValueError('Gradle user home must be private and owned by the current user')
    for path in (home / 'init.gradle', home / 'init.gradle.kts', home / 'gradle.properties'):
        if os.path.lexists(path):
            raise ValueError('Gradle user init/properties are not permitted')
    # A dedicated cache copy must not point or hardlink back to shared data.
    def walk_error(error):
        raise error
    for directory, names, files in os.walk(home, topdown=True, followlinks=False, onerror=walk_error):
        for name in names + files:
            entry = Path(directory) / name
            item = os.lstat(entry)
            if stat.S_ISLNK(item.st_mode) or not (stat.S_ISDIR(item.st_mode) or stat.S_ISREG(item.st_mode)):
                raise ValueError('Gradle home contains a link or special file')
            if stat.S_ISREG(item.st_mode) and item.st_nlink != 1:
                raise ValueError('Gradle home contains a hardlinked file')
    init_dir = home / 'init.d'
    if os.path.lexists(init_dir):
        check_no_symlink(init_dir)
        if not init_dir.is_dir() or any(init_dir.iterdir()):
            raise ValueError('Gradle user init.d must be absent or empty')


def reject_gradle_install_config(executable):
    if executable.name != 'gradle' or executable.parent.name != 'bin':
        raise ValueError('Gradle executable must be distribution/bin/gradle')
    root = executable.parent.parent
    check_no_symlink(root)
    if os.path.lexists(root / 'gradle.properties'):
        raise ValueError('Gradle installation properties are not permitted')
    init_dir = root / 'init.d'
    if os.path.lexists(init_dir):
        check_no_symlink(init_dir)
        if not init_dir.is_dir():
            raise ValueError('invalid Gradle installation init.d')
        for item in init_dir.iterdir():
            check_no_symlink(item)
            if not item.is_file() or item.name.endswith(('.gradle', '.gradle.kts')):
                raise ValueError('Gradle installation init scripts are not permitted')


def fixed_command(gradle, project, init):
    return [str(gradle), '--no-daemon', '--no-configuration-cache', '--offline',
            '--console=plain', '-p', str(project), '-I', str(init), 'runGameTestServer']


def parse_args(argv):
    parser = argparse.ArgumentParser(allow_abbrev=False)
    for flag in ('scratch', 'observer-jar', 'observer-sha256', 'immersive-jar', 'warfare-jar',
                 'java-home', 'java-sha256', 'gradle', 'gradle-sha256', 'gradle-user-home'):
        parser.add_argument('--' + flag, required=True)
    parser.add_argument('--isolated-single-jvm-attested', action='store_true', required=True)
    parser.add_argument('--exclusive-gradle-home-attested', action='store_true', required=True)
    parser.add_argument('--network-isolated-attested', action='store_true', required=True)
    return parser.parse_args(argv)


def launch(args):
    if not (getattr(args, 'isolated_single_jvm_attested', False)
            and getattr(args, 'exclusive_gradle_home_attested', False)
            and getattr(args, 'network_isolated_attested', False)):
        raise ValueError('independent isolation attestations are required')
    if os.name != 'posix' or not hasattr(os, 'O_NOFOLLOW'):
        raise ValueError('POSIX O_NOFOLLOW and flock required')
    source_root = Path(__file__).absolute().parents[2]
    check_no_symlink(source_root)
    script_init = Path(__file__).absolute().parent / 'safe-launch.init.gradle'
    check_no_symlink(script_init)
    for key in ('scratch', 'observer_jar', 'immersive_jar', 'warfare_jar', 'java_home', 'gradle', 'gradle_user_home'):
        if not Path(getattr(args, key)).is_absolute():
            raise ValueError('all paths must be absolute')
    scratch = Path(args.scratch)
    observer = Path(args.observer_jar)
    java_home, gradle, gradle_home = Path(args.java_home), Path(args.gradle), Path(args.gradle_user_home)
    check_no_symlink(java_home)
    check_regular_file(java_home / 'bin/java', args.java_sha256)
    check_regular_file(gradle, args.gradle_sha256)
    reject_gradle_install_config(gradle)
    reject_gradle_user_config(gradle_home)
    for path, digest in ((observer, args.observer_sha256), (Path(args.immersive_jar), MODS[next(iter(MODS))]),
                         (Path(args.warfare_jar), MODS[list(MODS)[1]])):
        check_regular_file(path, digest)
    # The source tree and cache may not reside inside the future output tree, or vice versa.
    for item in (source_root, observer, java_home, gradle, gradle.parent.parent, gradle_home,
                 Path(args.immersive_jar), Path(args.warfare_jar)):
        if scratch == item or scratch in item.parents or item in scratch.parents:
            raise ValueError('scratch must not overlap inputs, source or tooling')
    create_private_scratch(scratch)
    lock_path = scratch / 'attempt.lock'
    lockfd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    fcntl.flock(lockfd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    # Never delete scratch, lock, world or evidence, including on error.
    try:
        token = secrets.token_hex(16)
        archive = subprocess.run(['/usr/bin/git', '-C', str(source_root), 'archive', '--format=tar', BASE, '--',
                                  'ww-debug-benchmark'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'}, timeout=30).stdout
        if len(archive) > 40 * 1024 * 1024:
            raise ValueError('archive too large')
        project = extract_project(archive, scratch)
        mods = project / 'flight-test-mods'
        mods.mkdir(mode=0o700)
        copy_checked(Path(args.immersive_jar), mods / next(iter(MODS)), MODS[next(iter(MODS))])
        copy_checked(Path(args.warfare_jar), mods / list(MODS)[1], MODS[list(MODS)[1]])
        local_observer = scratch / 'observer-source.jar'
        copy_checked(observer, local_observer, args.observer_sha256)
        init = scratch / 'safe-launch.init.gradle'
        init_bytes = read_private_regular(script_init)
        write_new(init, init_bytes)
        if os.path.lexists(project / 'run-gametest'):
            raise ValueError('run directory must not preexist')
        env = {'PATH': '/usr/bin:/bin', 'LC_ALL': 'C', 'JAVA_HOME': str(java_home),
               'GRADLE_USER_HOME': str(gradle_home), 'WW_OBSERVER_PROJECT': str(project),
               'WW_OBSERVER_SOURCE': str(local_observer), 'WW_OBSERVER_SHA256': args.observer_sha256,
               'WW_OBSERVER_ATTEMPT': token}
        command = fixed_command(gradle, project, init)
        launcher_bytes = read_private_regular(Path(__file__).absolute())
        helper_bytes = read_private_regular(Path(__file__).absolute().parent / 'safe_preflight.py')
        evidence = {'base_commit': BASE, 'attempt': token, 'observer_sha256': args.observer_sha256,
                    'launcher_sha256': hashlib.sha256(launcher_bytes).hexdigest(),
                    'preflight_sha256': hashlib.sha256(helper_bytes).hexdigest(),
                    'mods': MODS, 'java_sha256': args.java_sha256, 'gradle_sha256': args.gradle_sha256,
                    'init_sha256': hashlib.sha256(init_bytes).hexdigest(), 'command': command,
                    'attestation': 'operator asserts disposable private world, exclusive JVM and dedicated Gradle home and network isolation; not independently proven'}
        write_new(scratch / 'provenance.json', (json.dumps(evidence, indent=2) + '\n').encode())
        stdout_identity = write_new(scratch / 'stdout.log', b'')
        stderr_identity = write_new(scratch / 'stderr.log', b'')
        # Recheck just before spawn. Same-UID replacement after this point remains possible.
        check_no_symlink(project)
        if os.path.lexists(project / 'run-gametest'):
            raise ValueError('run directory appeared before Gradle')
        reject_gradle_user_config(gradle_home)
        reject_gradle_install_config(gradle)
        check_regular_file(local_observer, args.observer_sha256)
        check_regular_file(java_home / 'bin/java', args.java_sha256)
        check_regular_file(gradle, args.gradle_sha256)
        for name, digest in MODS.items():
            check_regular_file(mods / name, digest)
        with open_log_append(scratch / 'stdout.log', stdout_identity) as stdout, \
                open_log_append(scratch / 'stderr.log', stderr_identity) as stderr:
            result = subprocess.run(command, cwd=project, env=env, stdout=stdout, stderr=stderr, check=False)
        write_new(scratch / 'exit-code.txt', (str(result.returncode) + '\n').encode())
        output_path = scratch / 'stdout.log'
        output = read_private_regular(output_path, expected_identity=stdout_identity).decode('utf-8', errors='replace')
        with open_log_append(scratch / 'stderr.log', stderr_identity):
            pass  # Verify the captured error log still names the originally created inode.
        markers = [f'OBSERVER_PREPARE_GUARD attempt={token}', f'OBSERVER_PREPARE_DONE attempt={token}',
                   f'OBSERVER_STAGED attempt={token} sha256={args.observer_sha256}']
        lines = output.splitlines()
        valid_markers = all(lines.count(marker) == 1 for marker in markers) and all(
            lines.index(a) < lines.index(b) for a, b in zip(markers, markers[1:]))
        status = 'launcher_completed_runtime_unverified' if result.returncode == 0 and valid_markers else 'inconclusive'
        write_new(scratch / 'launcher-status.json', (json.dumps({'status': status, 'markers_valid': valid_markers}) + '\n').encode())
        return 0 if status == 'launcher_completed_runtime_unverified' else 2
    except BaseException as failure:
        try:
            write_new(scratch / 'launcher-failure.txt', (type(failure).__name__ + ': ' + str(failure) + '\n').encode())
        except OSError:
            pass  # Never overwrite evidence or guess at a damaged scratch directory.
        raise
    finally:
        os.close(lockfd)


def main(argv=None):
    if not sys.flags.isolated:
        raise SystemExit('invoke with python3 -I; PYTHONPATH/user site must not be active')
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        return launch(args)
    except (OSError, ValueError, subprocess.SubprocessError) as failure:
        print('preflight/launch failed; preserve scratch and inspect:', failure, file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
