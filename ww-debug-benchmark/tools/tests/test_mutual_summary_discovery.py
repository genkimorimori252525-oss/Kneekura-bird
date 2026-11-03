"""Post-combat completion must belong to the actual primary fighter."""
import json
import copy
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


VERIFIER = Path(__file__).resolve().parents[1] / "verify_mutual_dogfight_scenario.py"
PRIMARY = "15a7c379-1310-4def-b8a0-fdaa8b1787b1"
OPPONENT = "f93acc19-18a9-44de-9f33-f0ddc38f7095"
OTHER = "7bd32675-6cff-4a29-a777-0e76c2348004"
PRIMARY_PILOT = "2a8ad002-ac1b-4f83-8903-60fb4366ddee"
OPPONENT_PILOT = "696d5d49-c397-4b53-a30d-f7eeaa531887"


class MutualSummaryDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        logs = self.root / "world/wwdebug/autopilot/run/aircraft"
        logs.mkdir(parents=True)
        primary = "AUTOPILOT TEST warfare_wings:a6m"
        opponent = "MUTUAL BLUE P47N"

        def row(name, aircraft_id, event, tick, reason="", **extra):
            return {"aircraft_name": name, "aircraft_uuid": aircraft_id,
                    "pilot_uuid": PRIMARY_PILOT if aircraft_id == PRIMARY else OPPONENT_PILOT, "event": event,
                    "server_tick": tick, "reason": reason, **extra}

        self.primary_path = logs / "primary.jsonl"
        self.primary_rows = [
            row(primary, PRIMARY, "mutual_dogfight_validation_started", 100,
                f"primary_uuid={PRIMARY}:primary_pilot_uuid={PRIMARY_PILOT}:"
                f"opponent_uuid={OPPONENT}:opponent_pilot_uuid={OPPONENT_PILOT}"),
            row(primary, PRIMARY, "combat_target_acquired", 101,
                f"uuid={OPPONENT_PILOT}:target_faction=blue:explicit_faction_hostile=true"),
            row(primary, PRIMARY, "air_combat_action_transition", 102,
                "to=INTERCEPT:doctrine=turn_fighter"),
            row(primary, PRIMARY, "weapon_fire", 103, f"target_uuid={OPPONENT_PILOT}"),
            row(primary, PRIMARY, "frame", 104, speed_bps=25, on_ground=False),
            row(primary, PRIMARY, "control_adapter", 104, f"other_uuid={OPPONENT}:current=9.0",
                applied_safety_override="collision_avoidance"),
            row(primary, PRIMARY, "mutual_dogfight_validation_completed", 300,
                "age_ticks=200:minimum_separation=10.0:maximum_separation=100.0:"
                "primary_track_ticks=150:opponent_track_ticks=150:"
                "primary_combat_ticks=150:opponent_combat_ticks=150"),
            row(primary, PRIMARY, "phase_transition", 400,
                "BRAKE->PARKED:complete_stop_stable_for_40_ticks", phase="PARKED"),
            row(primary, PRIMARY, "frame", 400, phase="PARKED", on_ground=True,
                horizontal_speed_bps=0.0),
            row(primary, PRIMARY, "session_end", 400,
                "validation_aircraft_cleanup", phase="PARKED"),
        ]
        self.write_primary()
        rows = [
            row(opponent, OPPONENT, "combat_target_acquired", 101,
                f"uuid={PRIMARY_PILOT}:target_faction=red:explicit_faction_hostile=true"),
            row(opponent, OPPONENT, "air_combat_action_transition", 102,
                "to=INTERCEPT:doctrine=energy_fighter"),
            row(opponent, OPPONENT, "weapon_fire", 103, f"target_uuid={PRIMARY_PILOT}"),
            row(opponent, OPPONENT, "frame", 104, speed_bps=25, on_ground=False),
            row(opponent, OPPONENT, "control_adapter", 104, f"other_uuid={PRIMARY}:current=9.0",
                applied_safety_override="collision_avoidance"),
        ]
        (logs / "opponent.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows),
                                            encoding="utf-8")
        self.summary = {"state": "complete", "total": 1, "completed": 1, "results": [{
            "entity_id": "warfare_wings:a6m", "aircraft_uuid": PRIMARY, "passed": True,
            "reason": "completed_full_mission", "final_phase": "PARKED",
            "last_transition_reason": "complete_stop_stable_for_40_ticks"}]}

    def write_primary(self):
        self.primary_path.write_text("".join(json.dumps(r) + "\n" for r in self.primary_rows),
                                     encoding="utf-8")

    def run_verifier(self, injection=None):
        import contextlib
        import importlib.util
        import io
        from unittest import mock

        spec = importlib.util.spec_from_file_location('mutual_verifier', VERIFIER)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        output = self.root / 'report.json'
        output.unlink(missing_ok=True)
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(sys, 'argv', ['verifier', '--root', str(self.root),
                                '--gradle-status', '0', '--output', str(output)]))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            stack.enter_context(contextlib.redirect_stderr(io.StringIO()))
            if injection:
                stack.enter_context(injection)
            code = module.main()
        self.assertTrue(output.is_file(), 'verification must persist a result JSON')
        return code, json.loads(output.read_text(encoding='utf-8'))

    def test_single_readable_summary_passes(self):
        (self.root / 'validation-summary-1.json').write_text(json.dumps(self.summary))
        code, report = self.run_verifier()
        self.assertEqual(code, 0, report)
        self.assertTrue(report['passed'])

    def test_multiple_summary_files_cannot_use_stale_success(self):
        import os
        success = self.root / 'validation-summary-old.json'
        success.write_text(json.dumps(self.summary))
        failed = copy.deepcopy(self.summary)
        failed['results'][0]['passed'] = False
        (self.root / 'validation-summary-new.json').write_text(json.dumps(failed))
        os.utime(success, (4102444800, 4102444800))
        code, report = self.run_verifier()
        self.assertNotEqual(code, 0)
        self.assertFalse(report['passed'])
        self.assertIn('expected exactly one validation summary in the artifact tree, found 2', report['errors'])

    def test_summary_named_directory_cannot_coexist_with_valid_summary(self):
        (self.root / 'validation-summary-1.json').write_text(json.dumps(self.summary))
        (self.root / 'validation-summary-2.json').mkdir()
        code, report = self.run_verifier()
        self.assertNotEqual(code, 0)
        self.assertFalse(report['passed'])
        self.assertTrue(any('not a regular file' in error for error in report['errors']))

    def test_summary_named_directory_cannot_supply_nested_summary(self):
        container = self.root / 'validation-summary-2.json'
        container.mkdir()
        (container / 'validation-summary-1.json').write_text(json.dumps(self.summary))
        code, report = self.run_verifier()
        self.assertNotEqual(code, 0)
        self.assertFalse(report['passed'])
        self.assertTrue(any('not a regular file' in error for error in report['errors']))

    def test_named_pipe_summary_is_rejected_without_reading(self):
        import os
        if not hasattr(os, 'mkfifo'):
            self.skipTest('named pipes unavailable')
        (self.root / 'validation-summary-1.json').write_text(json.dumps(self.summary))
        os.mkfifo(self.root / 'validation-summary-2.json')
        code, report = self.run_verifier()
        self.assertNotEqual(code, 0)
        self.assertFalse(report['passed'])
        self.assertTrue(any('not a regular file' in error for error in report['errors']))

    def test_unreadable_nested_directory_cannot_hide_summary(self):
        import os
        from unittest import mock
        (self.root / 'validation-summary-1.json').write_text(json.dumps(self.summary))
        hidden = self.root / 'hidden'
        hidden.mkdir()
        (hidden / 'validation-summary-2.json').write_text('{}')
        real_scandir = os.scandir
        def deny_hidden(path):
            if Path(path) == hidden:
                raise PermissionError('injected directory denial')
            return real_scandir(path)
        code, report = self.run_verifier(mock.patch('os.scandir', deny_hidden))
        self.assertNotEqual(code, 0)
        self.assertFalse(report['passed'])
        self.assertIn(f'cannot inspect summary tree {hidden}: PermissionError', report['errors'])

    def test_summary_stat_failure_still_writes_failed_result(self):
        from unittest import mock
        path = self.root / 'validation-summary-1.json'
        path.write_text(json.dumps(self.summary))
        real_stat = Path.stat
        def deny_summary(self, *args, **kwargs):
            if self == path:
                raise PermissionError('injected stat denial')
            return real_stat(self, *args, **kwargs)
        code, report = self.run_verifier(mock.patch.object(Path, 'stat', deny_summary))
        self.assertNotEqual(code, 0)
        self.assertFalse(report['passed'])
        self.assertIn(f'cannot inspect summary tree {path}: PermissionError', report['errors'])

    def test_summary_read_failure_still_writes_failed_result(self):
        from unittest import mock
        path = self.root / 'validation-summary-1.json'
        path.write_text(json.dumps(self.summary))
        real_read = Path.read_text
        def deny_summary(self, *args, **kwargs):
            if self == path:
                raise PermissionError('injected read denial')
            return real_read(self, *args, **kwargs)
        code, report = self.run_verifier(mock.patch.object(Path, 'read_text', deny_summary))
        self.assertNotEqual(code, 0)
        self.assertFalse(report['passed'])
        self.assertIn(f'cannot read validation summary {path}: PermissionError', report['errors'])

    def test_partial_directory_iteration_cannot_pass(self):
        import os
        from unittest import mock
        (self.root / 'validation-summary-1.json').write_text(json.dumps(self.summary))
        hidden = self.root / 'incomplete'
        hidden.mkdir()
        (hidden / 'ordinary.txt').write_text('x')
        real_scandir = os.scandir
        class InterruptedScan:
            def __init__(self, path):
                self.iterator = real_scandir(path)
            def __enter__(self):
                return self
            def __exit__(self, *args):
                self.iterator.close()
            def __iter__(self):
                yield next(self.iterator)
                raise OSError('injected iteration failure')
        def scan(path):
            return InterruptedScan(path) if Path(path) == hidden else real_scandir(path)
        code, report = self.run_verifier(mock.patch('os.scandir', scan))
        self.assertNotEqual(code, 0)
        self.assertFalse(report['passed'])
        self.assertIn(f'cannot inspect summary tree {hidden}: OSError', report['errors'])

    def test_missing_summary_fails(self):
        code, report = self.run_verifier()
        self.assertNotEqual(code, 0)
        self.assertFalse(report['passed'])
        self.assertIn('expected exactly one validation summary in the artifact tree, found 0', report['errors'])

    def test_invalid_summary_encoding_still_writes_failure(self):
        (self.root / 'validation-summary-1.json').write_bytes(b'\xff')
        code, report = self.run_verifier()
        self.assertNotEqual(code, 0)
        self.assertFalse(report['passed'])
        self.assertIn(f'cannot read validation summary {self.root / "validation-summary-1.json"}: UnicodeDecodeError',
                      report['errors'])

    def test_unscanned_symlink_directory_cannot_hide_summary(self):
        (self.root / 'validation-summary-1.json').write_text(json.dumps(self.summary))
        with tempfile.TemporaryDirectory() as external:
            (Path(external) / 'validation-summary-2.json').write_text('{}')
            try:
                (self.root / 'linked').symlink_to(external, target_is_directory=True)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f'symlink unavailable: {exc}')
            code, report = self.run_verifier()
        self.assertNotEqual(code, 0)
        self.assertFalse(report['passed'])
        self.assertIn(f'cannot inspect summary tree link: {self.root / "linked"}', report['errors'])

if __name__ == '__main__':
    unittest.main()
