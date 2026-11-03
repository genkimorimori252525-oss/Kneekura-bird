"""Interior frame coverage is a necessary, not continuous-physics, safety condition."""
import json
import subprocess
import sys
import unittest

import test_mutual_frame_integrity as fixture_mod


class MutualFrameCoverageTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture_mod.MutualFrameIntegrityTests('test_valid_frames_in_window_pass')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def verify(self):
        return self.fixture.verify()

    def test_one_frame_each_interior_tick_passes_without_boundary_frames(self):
        code, result = self.verify()
        self.assertEqual(code, 0, result)
        self.assertTrue(result['passed'])
        self.assertEqual(result['metrics']['primary_ground_frames'], 0)
        self.assertEqual(result['metrics']['opponent_min_speed_bps'], 25)

    def test_missing_single_interior_tick_on_either_plane_is_unverified(self):
        for role in ('primary', 'opponent'):
            with self.subTest(role=role):
                rows = getattr(self.fixture, role)
                missing = next(r for r in rows if r['event'] == 'frame' and r['server_tick'] == 120)
                index = rows.index(missing)
                rows.pop(index)
                try:
                    code, result = self.verify()
                    self.assertNotEqual(code, 0, result)
                    self.assertTrue(any('coverage' in e for e in result['errors']), result)
                    for prefix in ('primary', 'opponent'):
                        self.assertIsNone(result['metrics'][prefix + '_ground_frames'])
                        self.assertIsNone(result['metrics'][prefix + '_min_speed_bps'])
                finally:
                    rows.insert(index, missing)

    def test_duplicate_frame_cannot_replace_missing_tick(self):
        rows = self.fixture.opponent
        missing = next(r for r in rows if r['event'] == 'frame' and r['server_tick'] == 120)
        index = rows.index(missing)
        rows.pop(index)
        original = next(r for r in rows if r['event'] == 'frame' and r['server_tick'] == 121)
        duplicate_index = rows.index(original) + 1
        rows.insert(duplicate_index, dict(original))
        try:
            code, result = self.verify()
            self.assertNotEqual(code, 0, result)
            self.assertTrue(any('coverage' in e for e in result['errors']), result)
        finally:
            rows.pop(duplicate_index)
            rows.insert(index, missing)

    def test_extra_valid_frame_does_not_invalidate_covered_tick(self):
        rows = self.fixture.primary
        original = next(r for r in rows if r['event'] == 'frame' and r['server_tick'] == 121)
        rows.insert(rows.index(original) + 1, dict(original))
        code, result = self.verify()
        self.assertEqual(code, 0, result)
        self.assertEqual(result['metrics']['primary_interior_missing_ticks'], 0)

    def test_empty_interior_is_unverified(self):
        end = next(r for r in self.fixture.primary if r['event'] == 'mutual_dogfight_validation_completed')
        end['server_tick'] = 101
        code, result = self.verify()
        self.assertNotEqual(code, 0, result)
        self.assertTrue(any('interior' in e for e in result['errors']), result)

    def test_observed_unsafe_frame_is_still_reported_when_other_plane_has_a_gap(self):
        frame = next(r for r in self.fixture.primary if r['event'] == 'frame')
        rows = self.fixture.opponent
        rows.remove(next(r for r in rows if r['event'] == 'frame' and r['server_tick'] == 120))
        for field, value, message in (('on_ground', True, 'touched the ground'),
                                      ('speed_bps', 8.4, 'speed became unsafe')):
            with self.subTest(field=field):
                old = frame[field]
                frame[field] = value
                code, result = self.verify()
                self.assertNotEqual(code, 0, result)
                self.assertTrue(any(message in e for e in result['errors']), result)
                self.assertIsNone(result['metrics']['primary_ground_frames'])
                self.assertIsNone(result['metrics']['opponent_ground_frames'])
                self.assertIsNone(result['metrics']['primary_min_speed_bps'])
                self.assertIsNone(result['metrics']['opponent_min_speed_bps'])
                frame[field] = old

    def test_known_violation_and_invalid_frame_survive_coverage_gaps(self):
        known = next(r for r in self.fixture.primary if r['event'] == 'frame' and r['server_tick'] == 121)
        invalid = next(r for r in self.fixture.primary if r['event'] == 'frame' and r['server_tick'] == 122)
        other = self.fixture.opponent
        other.remove(next(r for r in other if r['event'] == 'frame' and r['server_tick'] == 120))
        for field, danger, message in (('on_ground', True, 'touched the ground'),
                                       ('speed_bps', 8.4, 'speed became unsafe')):
            with self.subTest(field=field):
                original_known, original_invalid = known[field], invalid[field]
                known[field], invalid[field] = danger, None
                code, result = self.verify()
                self.assertNotEqual(code, 0, result)
                self.assertTrue(any(message in e for e in result['errors']), result)
                self.assertTrue(any('missing or invalid' in e for e in result['errors']), result)
                self.assertTrue(any('frame coverage is incomplete' in e for e in result['errors']), result)
                for role in ('primary', 'opponent'):
                    self.assertIsNone(result['metrics'][role + '_ground_frames'])
                    self.assertIsNone(result['metrics'][role + '_min_speed_bps'])
                known[field], invalid[field] = original_known, original_invalid

    def test_huge_tick_window_has_bounded_computation(self):
        end = next(r for r in self.fixture.primary if r['event'] == 'mutual_dogfight_validation_completed')
        end['server_tick'] = 10 ** 50
        for name, rows in (('a6m.jsonl', self.fixture.primary), ('p47n.jsonl', self.fixture.opponent)):
            (self.fixture.logs / name).write_text(''.join(json.dumps(r) + '\n' for r in rows), encoding='utf-8')
        output = self.fixture.root / 'bounded-result.json'
        proc = subprocess.run([sys.executable, str(fixture_mod.VERIFIER), '--root', str(self.fixture.root),
                               '--gradle-status', '0', '--output', str(output)],
                              capture_output=True, text=True, check=False, timeout=5)
        self.assertTrue(output.exists(), proc.stderr)
        result = json.loads(output.read_text())
        self.assertNotEqual(proc.returncode, 0, result)
        self.assertTrue(any('coverage' in e for e in result['errors']), result)


if __name__ == '__main__':
    unittest.main()
