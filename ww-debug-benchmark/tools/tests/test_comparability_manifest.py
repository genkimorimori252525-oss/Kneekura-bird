"""Public manifests summarize explicit synthetic telemetry without exposing its contents."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

CLI = Path(__file__).resolve().parents[1] / "comparability_manifest.py"
AIRCRAFT = "15a7c379-1310-4def-b8a0-fdaa8b1787b1"
OTHER = "f93acc19-18a9-44de-9f33-f0ddc38f7095"
PRIVATE = "private-person-name-Zephyr"


class ComparabilityManifestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="private-manifest-case-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve(strict=True)
        self.telemetry = self.root / "telemetry.jsonl"
        self.provenance = self.root / "provenance.json"
        self.other = self.root / "not-an-input.jsonl"
        self.other.write_text("{private sentinel must not be read or modified", encoding="utf-8")
        self.rows = [self.frame(tick) for tick in (3, 4, 7)]
        self.provenance_data = {"source_head": "a" * 40, "mod_sha256": "b" * 64,
                                "config_sha256": "c" * 64, "profile_sha256": "d" * 64}

    @staticmethod
    def frame(tick):
        return {"aircraft_uuid": AIRCRAFT, "aircraft_entity_id": "warfare_wings:a6m", "run_id": "run-Zephyr",
                "event": "frame", "server_tick": tick, "position": {"x": 1.0, "y": 2.0, "z": 3.0},
                "velocity_bpt": {"x": 0.1, "y": 0.0, "z": -0.1}, "control_x": 0.0,
                "control_y": 0.1, "control_z": -0.1, "speed_bps": 20.0, "engine_target_command": 0.8,
                "reason": PRIVATE, "custom_field": "private-arbitrary-field"}

    def verify(self, *, raw_telemetry=None, raw_provenance=None, timeout=3):
        self.telemetry.write_text(raw_telemetry if raw_telemetry is not None else
                                  "".join(json.dumps(row) + "\n" for row in self.rows), encoding="utf-8")
        self.provenance.write_text(raw_provenance if raw_provenance is not None else
                                   json.dumps(self.provenance_data), encoding="utf-8")
        before = {path: path.read_bytes() for path in (self.telemetry, self.provenance, self.other)}
        proc = subprocess.run([sys.executable, str(CLI), "--telemetry", str(self.telemetry),
                               "--provenance", str(self.provenance)], capture_output=True,
                              text=True, timeout=timeout, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        for path, content in before.items():
            self.assertEqual(path.read_bytes(), content, f"input or unrelated sentinel changed: {path.name}")
        try:
            manifest = json.loads(proc.stdout)
        except json.JSONDecodeError:
            self.fail(f"stdout must contain one JSON manifest, exit={proc.returncode}; stderr={proc.stderr}")
        self.assertIsInstance(manifest, dict)
        self.assertEqual(manifest.get("status"), "NOT_COMPARABLE", manifest)
        public = proc.stdout + proc.stderr
        for forbidden in (str(self.root), str(self.telemetry), str(self.provenance), AIRCRAFT,
                          OTHER, PRIVATE, "private-arbitrary-field", "run-Zephyr", "different-private-run",
                          "not-a-uuid", "warfare_wings:p47n"):
            self.assertNotIn(forbidden, public, f"private input leaked: {forbidden!r}")
        return proc, manifest

    def assert_invalid(self, **kwargs):
        proc, manifest = self.verify(**kwargs)
        self.assertNotEqual(proc.returncode, 0, manifest)
        self.assertEqual(manifest.get("integrity"), "INVALID", manifest)
        return manifest

    def test_observed_frame_ranges_and_gaps_remain_not_comparable(self):
        proc, manifest = self.verify()
        self.assertEqual(proc.returncode, 0, manifest)
        self.assertEqual(manifest.get("integrity"), "VALID")
        ticks = manifest["frame_ticks"]
        self.assertEqual(ticks["observed_count"], 3)
        self.assertEqual(ticks["ranges"], [[3, 4], [7, 7]])
        self.assertEqual(ticks["missing_ranges"], [[5, 6]])
        self.assertEqual(ticks["missing_count"], 2)
        self.assertEqual(ticks["duplicate_count"], 0)
        self.assertEqual(ticks["out_of_order_count"], 0)
        self.assertEqual((ticks["min"], ticks["max"]), (3, 7))
        self.assertIn("missing_interior_frame_ticks", manifest["quality_flags"])
        for key, value in self.provenance_data.items():
            self.assertEqual(manifest["provenance"][key], value)
        for key in ("source_sha256", "immersive_aircraft_sha256", "warfare_wings_sha256", "model_sha256"):
            self.assertIsNone(manifest["provenance"][key])

    def test_contiguous_complete_provenance_is_still_not_comparable(self):
        self.rows = [self.frame(tick) for tick in (3, 4, 5)]
        proc, manifest = self.verify()
        self.assertEqual(proc.returncode, 0, manifest)
        self.assertEqual(manifest["integrity"], "VALID")
        self.assertEqual(manifest["frame_ticks"]["missing_count"], 0)
        self.assertEqual(manifest["frame_ticks"]["missing_ranges"], [])

    def test_frame_duplicates_and_reversal_are_invalid_but_counted(self):
        for ticks, key in (((3, 4, 4, 7), "duplicate_count"), ((3, 7, 4), "out_of_order_count")):
            with self.subTest(ticks=ticks):
                self.rows = [self.frame(tick) for tick in ticks]
                manifest = self.assert_invalid()
                self.assertEqual(manifest["frame_ticks"][key], 1)
                self.assertEqual(manifest["frame_ticks"]["observed_count"], len(ticks))

    def test_redacted_identity_distinguishes_run_and_aircraft_type(self):
        _, baseline = self.verify()
        for row in self.rows:
            row['run_id'] = 'different-private-run'
        _, different_run = self.verify()
        self.assertEqual(baseline['identity']['aircraft_uuid_sha256'],
                         different_run['identity']['aircraft_uuid_sha256'])
        self.assertNotEqual(baseline['identity']['run_id_sha256'],
                            different_run['identity']['run_id_sha256'])
        self.assertEqual(baseline['identity']['aircraft_type_sha256'],
                         different_run['identity']['aircraft_type_sha256'])
        for row in self.rows:
            row['aircraft_entity_id'] = 'warfare_wings:p47n'
        _, different_type = self.verify()
        self.assertNotEqual(different_run['identity']['aircraft_type_sha256'],
                            different_type['identity']['aircraft_type_sha256'])
        self.assertEqual(different_run['identity']['run_id_sha256'],
                         different_type['identity']['run_id_sha256'])

    def test_identity_hash_domains_are_distinct(self):
        for row in self.rows:
            row['run_id'] = 'shared-private-label'
            row['aircraft_entity_id'] = 'shared-private-label'
        proc, manifest = self.verify()
        self.assertNotIn('shared-private-label', proc.stdout + proc.stderr)
        self.assertNotEqual(manifest['identity']['run_id_sha256'],
                            manifest['identity']['aircraft_type_sha256'])

    def test_mixed_identity_or_missing_identity_is_invalid(self):
        changes = (("aircraft_uuid", OTHER), ("aircraft_entity_id", "warfare_wings:p47n"),
                   ("run_id", "different-private-run"), ("aircraft_uuid", "not-a-uuid"),
                   ("aircraft_uuid", None), ("aircraft_entity_id", None), ("run_id", None))
        for field, value in changes:
            with self.subTest(field=field, value=value):
                self.rows = [self.frame(tick) for tick in (3, 4, 7)]
                if value is None:
                    self.rows[1].pop(field)
                else:
                    self.rows[1][field] = value
                self.assert_invalid()

    def test_invalid_or_missing_ticks_and_event_are_invalid(self):
        for field, value in (("server_tick", None), ("server_tick", True), ("server_tick", -1),
                             ("server_tick", 4.0), ("server_tick", "4"), ("event", None)):
            with self.subTest(field=field, value=value):
                self.rows = [self.frame(tick) for tick in (3, 4, 7)]
                if value is None:
                    self.rows[1].pop(field)
                else:
                    self.rows[1][field] = value
                self.assert_invalid()

    def test_nonframe_events_are_not_reflected_in_public_output(self):
        row = self.frame(4)
        row["event"] = "private-arbitrary-event-" + PRIVATE
        self.rows.insert(2, row)
        proc, manifest = self.verify()
        self.assertEqual(proc.returncode, 0, manifest)
        self.assertEqual(manifest["integrity"], "VALID")
        self.assertNotIn("private-arbitrary-event", proc.stdout + proc.stderr)
        self.assertEqual(manifest["frame_ticks"]["observed_count"], 3)

    def test_missing_tick_in_nonframe_row_is_invalid(self):
        row = self.frame(4)
        row["event"] = "private-arbitrary-event-" + PRIVATE
        del row["server_tick"]
        self.rows.insert(2, row)
        self.assert_invalid()

    def test_nonframe_tick_reversal_is_invalid_without_corrupting_frame_counts(self):
        row = self.frame(2)
        row["event"] = "private-arbitrary-event-" + PRIVATE
        self.rows.insert(2, row)
        manifest = self.assert_invalid()
        self.assertEqual(manifest["frame_ticks"]["observed_count"], 3)
        self.assertEqual(manifest["frame_ticks"]["out_of_order_count"], 0)
        self.assertGreater(manifest["row_tick_order_decreases"], 0)

    def test_missing_frame_fields_are_counted_without_implying_values(self):
        self.rows[1].pop("position")
        self.rows[2].pop("engine_target_command")
        proc, manifest = self.verify()
        self.assertEqual(proc.returncode, 0, manifest)
        self.assertEqual(manifest["integrity"], "VALID")
        fields = manifest["available_frame_fields"]
        self.assertEqual(fields["position"], {"present": 2, "usable": 2})
        self.assertEqual(fields["engine_target_command"], {"present": 2, "usable": 2})

    def test_invalid_present_frame_fields_fail_closed(self):
        for field, value in (("position", None), ("position", {"x": 1, "y": 2}),
                             ("position", {"x": "NaN", "y": 2, "z": 3}),
                             ("velocity_bpt", [0, 0, 0]), ("control_x", "0.5"),
                             ("control_y", True), ("engine_target_command", None),
                             ("on_ground", "false")):
            with self.subTest(field=field, value=value):
                self.rows = [self.frame(tick) for tick in (3, 4, 7)]
                self.rows[1][field] = value
                self.assert_invalid()

    def test_finite_json_integer_outside_double_range_is_invalid(self):
        for field in ("position.x", "speed_bps"):
            with self.subTest(field=field):
                self.rows = [self.frame(tick) for tick in (3, 4, 7)]
                if field == "position.x":
                    self.rows[1]["position"]["x"] = 10**400
                else:
                    self.rows[1][field] = 10**400
                manifest = self.assert_invalid()
                self.assertEqual(manifest["available_frame_fields"][field.split(".")[0]]["usable"], 2)

    def test_unknown_field_and_event_are_neither_raw_nor_hashed(self):
        unknown_key = "private-field-SILVER"
        unknown_value = "private-value-TOPSECRET"
        unknown_event = "private-event-WHISTLE"
        self.rows[0][unknown_key] = unknown_value
        nonframe = self.frame(4)
        nonframe["event"] = unknown_event
        self.rows.insert(2, nonframe)
        proc, manifest = self.verify()
        self.assertEqual(proc.returncode, 0, manifest)
        self.assertEqual(manifest["integrity"], "VALID")
        public = proc.stdout + proc.stderr
        for text in (unknown_key, unknown_value, unknown_event):
            self.assertNotIn(text, public)
            self.assertNotIn(hashlib.sha256(text.encode()).hexdigest(), public)
            for domain in ("event", "field"):
                self.assertNotIn(hashlib.sha256((domain + "\0" + text).encode()).hexdigest(), public)

    def test_json_corruption_duplicates_and_nonfinite_numbers_are_invalid(self):
        line = json.dumps(self.frame(3))
        corruptions = ("{broken\n", "null\n", "\n", line[:-1] + ',"server_tick":3}\n',
                       line[:-1] + ',"private_nested":{"x":1,"x":2}}\n',
                       line[:-1] + ',"invalid":NaN}\n', line[:-1] + ',"invalid":Infinity}\n',
                       line[:-1] + ',"invalid":-Infinity}\n', line[:-1] + ',"invalid":1e9999}\n')
        for raw in corruptions:
            with self.subTest(corruption=raw[-45:]):
                self.assert_invalid(raw_telemetry=raw)

    def test_provenance_unknowns_and_strict_hashes(self):
        original = copy.deepcopy(self.provenance_data)
        for key in original:
            with self.subTest(unknown=key):
                self.provenance_data = dict(original, **{key: None})
                proc, manifest = self.verify()
                self.assertEqual(proc.returncode, 0, manifest)
                self.assertEqual(manifest["integrity"], "VALID")
                self.assertIsNone(manifest["provenance"][key])
        for key, bad in (("source_head", "a" * 39), ("source_head", "G" * 40),
                         ("mod_sha256", "b" * 63), ("config_sha256", "z" * 64),
                         ("profile_sha256", "D" * 64), ("profile_sha256", PRIVATE)):
            with self.subTest(key=key, bad=bad):
                self.provenance_data = dict(original, **{key: bad})
                self.assert_invalid()

    def test_provenance_invalid_json_or_duplicate_key_is_invalid(self):
        for raw in ('{"source_head":', '{"source_head":null,"source_head":null}',
                    '{"source_head":NaN}', '{"source_head":1e9999}', 'null'):
            with self.subTest(raw=raw):
                self.assert_invalid(raw_provenance=raw)

    def test_large_tick_gap_is_one_interval_not_enumerated(self):
        self.rows = [self.frame(1), self.frame(10**12)]
        proc, manifest = self.verify(timeout=3)
        self.assertEqual(proc.returncode, 0, manifest)
        ticks = manifest["frame_ticks"]
        self.assertEqual(ticks["ranges"], [[1, 1], [10**12, 10**12]])
        self.assertEqual(ticks["missing_ranges"], [[2, 10**12 - 1]])
        self.assertEqual(ticks["missing_count"], 10**12 - 2)
        self.assertLess(len(proc.stdout), 10000)


if __name__ == "__main__":
    unittest.main()
