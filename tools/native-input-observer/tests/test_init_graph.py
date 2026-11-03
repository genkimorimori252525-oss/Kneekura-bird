"""Exercise the real launcher init script against an isolated, miniature Gradle graph."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parents[1]
GRADLE = os.environ.get('OBSERVER_TEST_GRADLE')
JAVA_HOME = os.environ.get('OBSERVER_TEST_JAVA_HOME')


@unittest.skipUnless(GRADLE and JAVA_HOME, 'set OBSERVER_TEST_GRADLE and OBSERVER_TEST_JAVA_HOME')
class GradleGraphTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = self.root / 'project'
        self.project.mkdir()
        self.mods = self.project / 'flight-test-mods'
        self.mods.mkdir()
        self.observer = self.root / 'observer.jar'
        self.observer.write_bytes(b'fake observer')
        self.observer_hash = hashlib.sha256(self.observer.read_bytes()).hexdigest()
        original = (HERE / 'safe-launch.init.gradle').read_text()
        names = {
            'immersive_aircraft-1.3.3+1.20.1-forge.jar': ('d1f7cfeed3ac2cf69472ae756eb9189dad04ab21b8afbd443c82f40e51bbf065', b'fake immersive'),
            'warfare_wings-1.1.4-1.20.1-forge.jar': ('3b6b245e703862517fe7aae6acd95ccafc865e1e81ba7a26e2b9abcfe1120187', b'fake warfare'),
        }
        for name, (old_digest, content) in names.items():
            (self.mods / name).write_bytes(content)
            original = original.replace(old_digest, hashlib.sha256(content).hexdigest())
        self.init = self.root / 'init.gradle'
        self.init.write_text(original)
        (self.project / 'settings.gradle').write_text("rootProject.name='mini'\n")
        (self.project / 'build.gradle').write_text('''
import org.gradle.api.tasks.Internal
class FakeCfg {
    String workingDirectory
    Map props = [:]
    void property(String k, String v) { props[k] = v }
}
class FakeProvider {
    FakeCfg cfg
    FakeCfg get() { cfg }
}
class FakeRun extends DefaultTask {
    @Internal FakeCfg cfg
    @Internal FakeProvider getRunConfig() { new FakeProvider(cfg: cfg) }
    @Internal List getJvmArgumentProviders() { [] }
    @TaskAction void runProbe() {
        assert cfg.props['forge.enabledGameTestNamespaces'] == 'wwdebug_benchmark_stop_natural_probe'
        assert cfg.props['wwdebug.nativeInputObserver'] == 'enabled'
        project.file('server-started').text = 'fake server ran'
    }
}
tasks.register('prepareFlightGameTestRuntime') {
    doLast {
        project.file('run-gametest').mkdirs()
        project.file('run-gametest/eula.txt').text = 'fake prepare'
        if (System.getenv('WW_MINI_CONTAMINATE') == 'yes') {
            project.file('run-gametest/mods').mkdirs()
            project.file('run-gametest/mods/keep').text = 'keep'
        }
    }
}
tasks.register('runGameTestServer', FakeRun) {
    cfg = new FakeCfg(workingDirectory: project.file('run-gametest').absolutePath)
    dependsOn 'prepareFlightGameTestRuntime'
}
''')
        self.env = {'PATH': '/usr/bin:/bin', 'LC_ALL': 'C', 'JAVA_HOME': JAVA_HOME,
                    'GRADLE_USER_HOME': str(self.root / 'gradle-home'),
                    'WW_OBSERVER_PROJECT': str(self.project), 'WW_OBSERVER_SOURCE': str(self.observer),
                    'WW_OBSERVER_SHA256': self.observer_hash, 'WW_OBSERVER_ATTEMPT': 'unit-attempt'}

    def run_graph(self, *extra):
        return subprocess.run([GRADLE, '--no-daemon', '--offline', '--no-configuration-cache',
                               '--console=plain', '-p', str(self.project), '-I', str(self.init),
                               *extra, 'runGameTestServer'], env=self.env, capture_output=True, text=True, timeout=90)

    def test_prepare_then_stage_then_fake_server(self):
        result = self.run_graph()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        out = result.stdout
        self.assertLess(out.index('OBSERVER_PREPARE_GUARD'), out.index('OBSERVER_PREPARE_DONE'))
        self.assertLess(out.index('OBSERVER_PREPARE_DONE'), out.index('OBSERVER_STAGED'))
        staged = self.project / 'run-gametest/mods/wwdebug-input-probe.jar'
        self.assertEqual(staged.read_bytes(), self.observer.read_bytes())
        self.assertEqual((self.project / 'server-started').read_text(), 'fake server ran')

    def test_existing_world_is_untouched_and_server_does_not_start(self):
        run = self.project / 'run-gametest'
        run.mkdir()
        sentinel = run / 'world-keep'
        sentinel.write_bytes(b'keep')
        result = self.run_graph()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(sentinel.read_bytes(), b'keep')
        self.assertFalse((self.project / 'server-started').exists())

    def test_contaminated_prepare_output_blocks_stage_and_server(self):
        self.env['WW_MINI_CONTAMINATE'] = 'yes'
        result = self.run_graph()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.project / 'run-gametest/mods/keep').read_text(), 'keep')
        self.assertFalse((self.project / 'server-started').exists())

    def test_excluding_prepare_is_rejected(self):
        result = self.run_graph('-x', 'prepareFlightGameTestRuntime')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.project / 'run-gametest').exists())
        self.assertFalse((self.project / 'server-started').exists())

    def test_dry_run_is_rejected(self):
        result = self.run_graph('--dry-run')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.project / 'run-gametest').exists())
        self.assertFalse((self.project / 'server-started').exists())


if __name__ == '__main__':
    unittest.main()
