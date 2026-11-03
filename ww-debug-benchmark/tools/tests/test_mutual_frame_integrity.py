"""The mutual verifier must not infer safe flight from missing or invalid frames."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

VERIFIER = Path(__file__).resolve().parents[1] / 'verify_mutual_dogfight_scenario.py'
PRIMARY = 'AUTOPILOT TEST warfare_wings:a6m'
OPPONENT = 'MUTUAL BLUE P47N'


def row(name, event, tick, reason='', **extra):
    return {'aircraft_name': name, 'event': event, 'server_tick': tick,
            'reason': reason, **extra}


class MutualFrameIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.logs = self.root / 'world/wwdebug/autopilot/run/aircraft'
        self.logs.mkdir(parents=True)
        self.primary = [
            row(PRIMARY, 'mutual_dogfight_validation_started', 100),
            row(PRIMARY, 'combat_target_acquired', 101, 'target_faction=blue:explicit_faction_hostile=true'),
            row(PRIMARY, 'air_combat_action_transition', 102, 'to=INTERCEPT:doctrine=turn_fighter'),
            row(PRIMARY, 'weapon_fire', 103),
            row(PRIMARY, 'frame', 104, speed_bps=25, on_ground=False),
            row(PRIMARY, 'mutual_dogfight_validation_completed', 300,
                'minimum_separation=10.0:maximum_separation=100.0:'
                'primary_track_ticks=150:opponent_track_ticks=150:'
                'primary_combat_ticks=150:opponent_combat_ticks=150'),
        ]
        self.opponent = [
            row(OPPONENT, 'combat_target_acquired', 101, 'target_faction=red:explicit_faction_hostile=true'),
            row(OPPONENT, 'air_combat_action_transition', 102, 'to=INTERCEPT:doctrine=energy_fighter'),
            row(OPPONENT, 'weapon_fire', 103),
            row(OPPONENT, 'frame', 104, speed_bps=25, on_ground=False),
        ]
        (self.root / 'validation-summary-1.json').write_text(
            json.dumps({'state': 'complete', 'results': [{'passed': True}]}), encoding='utf-8')

    def verify(self):
        for name, rows in (('a6m.jsonl', self.primary), ('p47n.jsonl', self.opponent)):
            (self.logs / name).write_text(''.join(json.dumps(item) + '\n' for item in rows), encoding='utf-8')
        output = self.root / 'result.json'
        output.unlink(missing_ok=True)
        proc = subprocess.run([sys.executable, str(VERIFIER), '--root', str(self.root),
                               '--gradle-status', '0', '--output', str(output)],
                              capture_output=True, text=True, check=False)
        self.assertTrue(output.is_file(), proc.stderr)
        return proc.returncode, json.loads(output.read_text(encoding='utf-8'))

    def test_valid_frames_in_window_pass(self):
        code, result = self.verify()
        self.assertEqual(code, 0, result)
        self.assertTrue(result['passed'])
        self.assertEqual(result['metrics']['primary_min_speed_bps'], 25)
        self.assertEqual(result['metrics']['opponent_ground_frames'], 0)

    def test_invalid_values_outside_combat_window_do_not_change_window_result(self):
        self.primary.append(row(PRIMARY, 'frame', 99, speed_bps=None, on_ground=None))
        self.opponent.append(row(OPPONENT, 'frame', 301, speed_bps=None, on_ground=None))
        code, result = self.verify()
        self.assertEqual(code, 0, result)
        self.assertTrue(result['passed'])

    def test_each_aircraft_needs_a_frame_inside_the_combat_window(self):
        for target in ('primary', 'opponent'):
            with self.subTest(target=target):
                rows = getattr(self, target)
                frame = next(item for item in rows if item['event'] == 'frame')
                frame['server_tick'] = 301
                try:
                    code, result = self.verify()
                    self.assertNotEqual(code, 0, result)
                    self.assertFalse(result['passed'])
                    self.assertIsNone(result['metrics'][target + '_ground_frames'])
                    self.assertIsNone(result['metrics'][target + '_min_speed_bps'])
                finally:
                    frame['server_tick'] = 104

    def test_every_frame_needs_valid_nonnegative_finite_numeric_speed(self):
        for target in ('primary', 'opponent'):
            for value in (None, '25', True, -1, float('nan'), float('inf'), float('-inf')):
                with self.subTest(target=target, value=repr(value)):
                    rows = getattr(self, target)
                    rows.append(row(PRIMARY if target == 'primary' else OPPONENT, 'frame', 105,
                                    speed_bps=value, on_ground=False))
                    try:
                        code, result = self.verify()
                        self.assertNotEqual(code, 0, result)
                        self.assertFalse(result['passed'])
                        self.assertIsNone(result['metrics'][target + '_min_speed_bps'])
                    finally:
                        rows.pop()

    def test_every_frame_needs_explicit_boolean_ground(self):
        for target in ('primary', 'opponent'):
            for value in (None, 'false', 0, 1):
                with self.subTest(target=target, value=repr(value)):
                    rows = getattr(self, target)
                    rows.append(row(PRIMARY if target == 'primary' else OPPONENT, 'frame', 105,
                                    speed_bps=25, on_ground=value))
                    try:
                        code, result = self.verify()
                        self.assertNotEqual(code, 0, result)
                        self.assertFalse(result['passed'])
                        self.assertIsNone(result['metrics'][target + '_ground_frames'])
                    finally:
                        rows.pop()

    def test_missing_speed_or_ground_field_rejected(self):
        for key in ('speed_bps', 'on_ground'):
            with self.subTest(key=key):
                frame = next(item for item in self.primary if item['event'] == 'frame')
                value = frame.pop(key)
                try:
                    code, result = self.verify()
                    self.assertNotEqual(code, 0, result)
                    self.assertFalse(result['passed'])
                    self.assertIsNone(result['metrics']['primary_min_speed_bps' if key == 'speed_bps'
                                                        else 'primary_ground_frames'])
                finally:
                    frame[key] = value

    def test_unknown_frame_tick_cannot_be_excluded_from_safety_window(self):
        for target in ('primary', 'opponent'):
            for value in (None, '105', True, -1):
                with self.subTest(target=target, value=repr(value)):
                    rows = getattr(self, target)
                    rows.append(row(PRIMARY if target == 'primary' else OPPONENT, 'frame', value,
                                    speed_bps=25, on_ground=False))
                    try:
                        code, result = self.verify()
                        self.assertNotEqual(code, 0, result)
                        self.assertFalse(result['passed'])
                        self.assertIsNone(result['metrics'][target + '_ground_frames'])
                        self.assertIsNone(result['metrics'][target + '_min_speed_bps'])
                    finally:
                        rows.pop()

    def test_boundary_ticks_must_be_nonnegative_integers(self):
        for event in ('mutual_dogfight_validation_started', 'mutual_dogfight_validation_completed'):
            for value in (None, True, '105', 104.9, float('inf'), -1):
                with self.subTest(event=event, value=repr(value)):
                    boundary = next(item for item in self.primary if item['event'] == event)
                    old = boundary['server_tick']
                    boundary['server_tick'] = value
                    try:
                        code, result = self.verify()
                        self.assertNotEqual(code, 0, result)
                        self.assertFalse(result['passed'])
                        for target in ('primary', 'opponent'):
                            self.assertIsNone(result['metrics'][target + '_ground_frames'])
                            self.assertIsNone(result['metrics'][target + '_min_speed_bps'])
                    finally:
                        boundary['server_tick'] = old

    def test_missing_boundary_tick_cannot_define_a_window(self):
        for event in ('mutual_dogfight_validation_started', 'mutual_dogfight_validation_completed'):
            with self.subTest(event=event):
                boundary = next(item for item in self.primary if item['event'] == event)
                old = boundary.pop('server_tick')
                try:
                    code, result = self.verify()
                    self.assertNotEqual(code, 0, result)
                    self.assertFalse(result['passed'])
                finally:
                    boundary['server_tick'] = old

    def test_coerced_boundaries_cannot_hide_a_ground_contact_frame(self):
        start = next(item for item in self.primary
                     if item['event'] == 'mutual_dogfight_validation_started')
        end = next(item for item in self.primary
                   if item['event'] == 'mutual_dogfight_validation_completed')
        start['server_tick'] = True
        end['server_tick'] = 104.9
        self.primary.append(row(PRIMARY, 'frame', 105, speed_bps=25, on_ground=True))
        code, result = self.verify()
        self.assertNotEqual(code, 0, result)
        self.assertFalse(result['passed'])
        self.assertIsNone(result['metrics']['primary_ground_frames'])

    def test_completion_must_follow_start(self):
        boundary = next(item for item in self.primary
                        if item['event'] == 'mutual_dogfight_validation_completed')
        for value in (100, 99):
            with self.subTest(completion=value):
                boundary['server_tick'] = value
                try:
                    code, result = self.verify()
                    self.assertNotEqual(code, 0, result)
                    self.assertFalse(result['passed'])
                finally:
                    boundary['server_tick'] = 300

    def test_multiple_start_or_completion_events_are_ambiguous(self):
        for event in ('mutual_dogfight_validation_started', 'mutual_dogfight_validation_completed'):
            with self.subTest(event=event):
                boundary = next(item for item in self.primary if item['event'] == event)
                self.primary.append(dict(boundary))
                try:
                    code, result = self.verify()
                    self.assertNotEqual(code, 0, result)
                    self.assertFalse(result['passed'])
                finally:
                    self.primary.pop()

    def test_reported_ground_contact_and_unsafe_speed_still_fail(self):
        for key, value in (('on_ground', True), ('speed_bps', 8.4)):
            with self.subTest(key=key):
                frame = next(item for item in self.primary if item['event'] == 'frame')
                old = frame[key]
                frame[key] = value
                try:
                    code, result = self.verify()
                    self.assertNotEqual(code, 0, result)
                finally:
                    frame[key] = old

    def test_known_ground_contact_survives_other_invalid_ground_samples(self):
        for target, name, label in (('primary', PRIMARY, 'A6M'), ('opponent', OPPONENT, 'P-47N')):
            with self.subTest(target=target):
                rows = getattr(self, target)
                rows.extend((row(name, 'frame', 105, speed_bps=25, on_ground=True),
                             row(name, 'frame', 106, speed_bps=25, on_ground=None)))
                try:
                    code, result = self.verify()
                    self.assertNotEqual(code, 0, result)
                    self.assertIsNone(result['metrics'][target + '_ground_frames'])
                    self.assertEqual(result['metrics'][target + '_min_speed_bps'], 25)
                    self.assertTrue(any(label in error and 'missing or invalid ground' in error
                                        for error in result['errors']), result)
                    self.assertTrue(any(label in error and 'touched the ground' in error
                                        for error in result['errors']), result)
                finally:
                    del rows[-2:]

    def test_known_unsafe_speed_survives_other_invalid_speed_samples(self):
        for target, name, label in (('primary', PRIMARY, 'A6M'), ('opponent', OPPONENT, 'P-47N')):
            with self.subTest(target=target):
                rows = getattr(self, target)
                rows.extend((row(name, 'frame', 105, speed_bps=8.4, on_ground=False),
                             row(name, 'frame', 106, speed_bps=None, on_ground=False)))
                try:
                    code, result = self.verify()
                    self.assertNotEqual(code, 0, result)
                    self.assertIsNone(result['metrics'][target + '_min_speed_bps'])
                    self.assertEqual(result['metrics'][target + '_ground_frames'], 0)
                    self.assertTrue(any(label in error and 'missing or invalid speed' in error
                                        for error in result['errors']), result)
                    self.assertTrue(any(label in error and 'speed became unsafe' in error
                                        for error in result['errors']), result)
                finally:
                    del rows[-2:]

    def test_unknown_frame_tick_does_not_claim_window_ground_contact(self):
        self.primary.append(row(PRIMARY, 'frame', None, speed_bps=8.4, on_ground=True))
        code, result = self.verify()
        self.assertNotEqual(code, 0, result)
        self.assertIsNone(result['metrics']['primary_min_speed_bps'])
        self.assertIsNone(result['metrics']['primary_ground_frames'])
        self.assertFalse(any('A6M touched the ground' in error or 'A6M speed became unsafe' in error
                             for error in result['errors']), result)

    def test_observed_unsafe_speed_is_not_rounded_above_threshold_in_diagnostic(self):
        self.primary.extend((row(PRIMARY, 'frame', 105, speed_bps=8.499, on_ground=False),
                             row(PRIMARY, 'frame', 106, speed_bps=None, on_ground=False)))
        code, result = self.verify()
        self.assertNotEqual(code, 0, result)
        self.assertIsNone(result['metrics']['primary_min_speed_bps'])
        self.assertTrue(any('A6M speed became unsafe: 8.499' in error for error in result['errors']), result)

    def test_valid_window_violation_survives_other_unplaceable_frame(self):
        self.primary.extend((row(PRIMARY, 'frame', 105, speed_bps=8.4, on_ground=True),
                             row(PRIMARY, 'frame', None, speed_bps=25, on_ground=False)))
        code, result = self.verify()
        self.assertNotEqual(code, 0, result)
        self.assertIsNone(result['metrics']['primary_min_speed_bps'])
        self.assertIsNone(result['metrics']['primary_ground_frames'])
        self.assertTrue(any('A6M touched the ground' in error for error in result['errors']), result)
        self.assertTrue(any('A6M speed became unsafe' in error for error in result['errors']), result)


if __name__ == '__main__':
    unittest.main()
