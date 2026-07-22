#!/usr/bin/env python3
"""Regression tests for the P-47N real-physics trajectory model."""
from __future__ import annotations

import unittest
from pathlib import Path

import analyze_apex_yaw_replay as angular
import batch_coupled_climb_trajectory as batch
from analyze_coupled_climb_trajectory import (
    AircraftState,
    physics_tick,
    qualifies_for_headless,
    selected_candidate_defaults,
)


class CoupledClimbTrajectoryCalibrationTest(unittest.TestCase):
    def test_unsafe_attack_sector_does_not_qualify_for_headless(self) -> None:
        safe = dict(
            first_attack={"tick": 100},
            minimum_speed_bps=16.0,
            minimum_distance=53.0,
            minimum_estimated_agl=98.0,
            minimum_pull_out_margin=8.0,
            stall_guard_speed=10.0,
            minimum_separation=8.0,
        )
        self.assertTrue(qualifies_for_headless(**safe))

        for field, unsafe_value in (
            ("minimum_speed_bps", 9.9),
            ("minimum_distance", 7.9),
            ("minimum_estimated_agl", 0.0),
            ("minimum_pull_out_margin", -0.1),
        ):
            unsafe = safe | {field: unsafe_value}
            self.assertFalse(qualifies_for_headless(**unsafe), field)

    def test_batch_reuses_selected_candidate_parser(self) -> None:
        selected = selected_candidate_defaults()
        args = batch.simulation_args(Path("p47.jsonl"), Path("a6m.jsonl"), 5351)

        self.assertTrue(args.crossing_lag)
        self.assertFalse(args.p47_legacy_heading_capture_enabled)
        self.assertEqual(args.rotation_decay, 0.97)
        mapping = {
            "crossing_entry_min_raw_angle": "crossing_entry_min_raw_angle",
            "crossing_entry_max_raw_angle": "crossing_entry_raw_angle",
            "crossing_entry_min_closure": "crossing_entry_min_closure",
            "crossing_improvement_epsilon": "crossing_improvement_epsilon",
            "crossing_stall_ticks": "crossing_stall_ticks",
            "p47_legacy_heading_capture_enabled": "p47_legacy_heading_capture_enabled",
            "lag_ticks": "lag_ticks",
            "lag_yaw_fraction": "lag_yaw_fraction",
            "lag_target_pitch": "lag_climb_pitch",
            "approach_lead_ticks": "approach_lead_ticks",
            "reentry_speed_floor": "lag_speed_floor",
            "reentry_target_speed_offset": "lag_target_speed_offset",
            "reentry_min_agl": "reentry_min_agl",
            "reentry_pull_out_seconds": "reentry_pull_out_seconds",
        }
        for selected_name, argument_name in mapping.items():
            self.assertEqual(getattr(args, argument_name), selected[selected_name])

    def test_pr9_tick_1245_matches_tick_1246(self) -> None:
        # Preserved PR #9 dogfight_mutual telemetry. The initial smoothed inputs are
        # inferred from the recorded orientation delta, exactly as the replay CLI does.
        position = angular.Vec(-91.82928447092853, 35.863471054084954, 916.9324635422247)
        velocity = angular.Vec(2.050755314740897, 0.06426449244990683, -0.19660476930070614)
        yaw = -102.28647
        pitch = -1.7688175
        next_yaw = -103.745026
        next_pitch = -1.7674143
        control_decay = (1.0 - 0.013) * 0.97
        smoothed_x = angular.wrap_degrees(next_yaw - yaw) / (2.5 * control_decay)
        smoothed_z = (next_pitch - pitch) / (2.4 * control_decay)

        state = AircraftState(
            position=position,
            velocity=velocity,
            yaw=yaw,
            pitch=pitch,
            engine_power=0.9848687648773193,
            smoothed_x=smoothed_x,
            smoothed_z=smoothed_z,
        )
        predicted = physics_tick(
            state,
            command_x=-0.7463100552558899,
            command_z=-0.29062125,
            engine_target=0.2,
            engine_speed=0.102,
            lift=0.165,
            friction=0.013,
            glide_factor=0.055,
            horizontal_decay=0.97,
            vertical_decay=0.97,
            rotation_decay=0.97,
            yaw_speed=2.5,
            pitch_speed=2.4,
            engine_reaction_steps=100.0,
        )

        actual_position = angular.Vec(-89.78330593410566, 35.92771521458437, 916.6835887182727)
        actual_velocity = angular.Vec(2.045978536822875, 0.06424416049941548, -0.2488748239519536)

        self.assertAlmostEqual(predicted.yaw, next_yaw, places=5)
        self.assertAlmostEqual(predicted.pitch, next_pitch, places=5)
        self.assertAlmostEqual(predicted.engine_power, 0.9770200848579407, places=6)
        self.assertLess((predicted.position - actual_position).length(), 0.005)
        self.assertLess((predicted.velocity - actual_velocity).length(), 0.005)

    def test_rotation_decay_precedes_control_and_interpolation(self) -> None:
        state = AircraftState(
            position=angular.Vec(0.0, 100.0, 0.0),
            velocity=angular.Vec(0.0, 0.0, 0.0),
            yaw=0.0,
            pitch=0.0,
            engine_power=0.0,
            smoothed_x=1.0,
            smoothed_z=-1.0,
        )
        predicted = physics_tick(
            state,
            command_x=0.0,
            command_z=0.0,
            engine_target=0.0,
            engine_speed=0.102,
            lift=0.165,
            friction=0.013,
            glide_factor=0.055,
            horizontal_decay=0.97,
            vertical_decay=0.97,
            rotation_decay=0.97,
            yaw_speed=2.5,
            pitch_speed=2.4,
            engine_reaction_steps=100.0,
        )

        control_decay = (1.0 - 0.013) * 0.97
        self.assertAlmostEqual(predicted.yaw, 2.5 * control_decay)
        self.assertAlmostEqual(predicted.pitch, -2.4 * control_decay)
        self.assertAlmostEqual(predicted.smoothed_x, 0.9 * control_decay)
        self.assertAlmostEqual(predicted.smoothed_z, -0.9 * control_decay)

    def test_local_pivot_orientation_matches_94_tick_real_physics_trace(self) -> None:
        control_decay = (1.0 - 0.013) * 0.97
        state = AircraftState(
            position=angular.Vec(0.0, 100.0, 0.0),
            velocity=angular.Vec(0.0, 0.0, 0.0),
            yaw=-93.92355,
            pitch=-8.606654,
            engine_power=0.0,
            smoothed_x=angular.wrap_degrees(-94.689575 - -93.92355)
            / (2.5 * control_decay),
            smoothed_z=(-9.702209 - -8.606654) / (2.4 * control_decay),
        )
        expected = {
            5371: (-105.54343, -18.393744),
            5381: (-121.01257, -22.208162),
            5391: (-137.31653, -22.512064),
            5401: (-153.79218, -22.225204),
            5411: (-170.29492, -22.091967),
            5421: (173.20544, -22.070692),
            5431: (156.71423, -22.072842),
            5441: (140.23175, -22.072727),
            5451: (123.75665, -22.070492),
            5455: (117.168335, -22.069643),
        }
        previous_pitch = -7.509071
        maximum_yaw_error = 0.0
        maximum_pitch_error = 0.0

        for tick in range(5361, 5455):
            pitch_rate = state.pitch - previous_pitch
            previous_pitch = state.pitch
            command_z = angular.clamp(
                (-22.0 - state.pitch) / 12.0 - 0.30 * pitch_rate,
                -0.65,
                0.65,
            )
            state = physics_tick(
                state,
                command_x=-0.96,
                command_z=command_z,
                engine_target=0.0,
                engine_speed=0.0,
                lift=0.0,
                friction=0.013,
                glide_factor=0.0,
                horizontal_decay=0.97,
                vertical_decay=0.97,
                rotation_decay=0.97,
                yaw_speed=2.5,
                pitch_speed=2.4,
                engine_reaction_steps=100.0,
            )
            expected_orientation = expected.get(tick + 1)
            if expected_orientation is not None:
                expected_yaw, expected_pitch = expected_orientation
                maximum_yaw_error = max(
                    maximum_yaw_error,
                    abs(angular.wrap_degrees(state.yaw - expected_yaw)),
                )
                maximum_pitch_error = max(
                    maximum_pitch_error,
                    abs(state.pitch - expected_pitch),
                )

        self.assertLess(maximum_yaw_error, 1.0)
        self.assertLess(maximum_pitch_error, 0.2)


if __name__ == "__main__":
    unittest.main()
