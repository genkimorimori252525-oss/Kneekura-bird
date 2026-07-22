#!/usr/bin/env python3
"""Regression test for one exact P-47N real-physics telemetry step."""
from __future__ import annotations

import unittest

import analyze_apex_yaw_replay as angular
from analyze_coupled_climb_trajectory import AircraftState, physics_tick


class CoupledClimbTrajectoryCalibrationTest(unittest.TestCase):
    def test_pr9_tick_1245_matches_tick_1246(self) -> None:
        # Preserved PR #9 dogfight_mutual telemetry. The initial smoothed inputs are
        # inferred from the recorded orientation delta, exactly as the replay CLI does.
        position = angular.Vec(-91.82928447092853, 35.863471054084954, 916.9324635422247)
        velocity = angular.Vec(2.050755314740897, 0.06426449244990683, -0.19660476930070614)
        yaw = -102.28647
        pitch = -1.7688175
        next_yaw = -103.745026
        next_pitch = -1.7674143
        smoothed_x = angular.wrap_degrees(next_yaw - yaw) / 2.5
        smoothed_z = (next_pitch - pitch) / 2.4

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


if __name__ == "__main__":
    unittest.main()
