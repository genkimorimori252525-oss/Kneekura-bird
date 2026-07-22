#!/usr/bin/env python3
"""Replay a P-47N coupled-climb candidate with Immersive Aircraft physics.

Unlike ``analyze_apex_yaw_replay.py``, this tool advances the modeled P-47N position
and velocity. The target keeps its recorded real-physics trajectory, so the result is
still a pre-flight diagnostic rather than a replacement for Forge GameTest.

The default P-47N constants come from Warfare Wings 1.1.4 and Immersive Aircraft
1.3.3 for Minecraft 1.20.1. The update order mirrors the upstream implementation:

1. glide contribution and velocity-to-nose conversion;
2. drag, horizontal/vertical decay, and speed-dependent airplane gravity;
3. yaw/pitch update from the previous smoothed X/Z input;
4. thrust along the updated aircraft forward vector;
5. movement;
6. input and engine-power interpolation for the next tick.
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path

import analyze_apex_yaw_replay as angular


@dataclass
class AircraftState:
    position: angular.Vec
    velocity: angular.Vec
    yaw: float
    pitch: float
    engine_power: float
    smoothed_x: float
    smoothed_z: float


def lerp(first: angular.Vec, second: angular.Vec, weight: float) -> angular.Vec:
    return angular.Vec(
        first.x + (second.x - first.x) * weight,
        first.y + (second.y - first.y) * weight,
        first.z + (second.z - first.z) * weight,
    )


def horizontal_speed(vector: angular.Vec) -> float:
    return math.hypot(vector.x, vector.z)


def closure_bps(defender: angular.Vec, defender_velocity: angular.Vec,
                attacker: angular.Vec, attacker_velocity: angular.Vec) -> float:
    line = attacker - defender
    if line.length() <= 1.0e-9:
        return 0.0
    relative = attacker_velocity - defender_velocity
    return -relative.scale(20.0).dot(line.normalized())


def infer_initial_smoothing(first: angular.Frame, second: angular.Frame,
                            yaw_speed: float, pitch_speed: float) -> tuple[float, float]:
    smoothed_x = angular.wrap_degrees(second.yaw - first.yaw) / yaw_speed
    smoothed_z = (second.pitch - first.pitch) / pitch_speed
    return smoothed_x, smoothed_z


def physics_tick(
    state: AircraftState,
    *,
    command_x: float,
    command_z: float,
    engine_target: float,
    engine_speed: float,
    lift: float,
    friction: float,
    glide_factor: float,
    horizontal_decay: float,
    vertical_decay: float,
    yaw_speed: float,
    pitch_speed: float,
    engine_reaction_steps: float,
) -> AircraftState:
    direction = angular.forward(state.yaw, state.pitch)
    velocity = state.velocity

    # AircraftEntity.updateVelocity: convert descent into forward glide first.
    altitude_difference = -velocity.y
    if abs(altitude_difference) > 1.0e-12 and glide_factor > 0.0:
        velocity = velocity + direction.scale(
            altitude_difference * glide_factor * (1.0 - abs(direction.y))
        )

    # AircraftEntity.convertPower: gradually align velocity with the nose and lose
    # energy according to angular misalignment and VehicleStat.FRICTION.
    speed = velocity.length()
    if speed > 1.0e-12:
        normalized_velocity = velocity.scale(1.0 / speed)
        alignment = abs(direction.dot(normalized_velocity))
        converted = lerp(normalized_velocity, direction, lift)
        velocity = converted.scale(
            speed * (alignment * friction + (1.0 - friction))
        )

    # InventoryVehicleEntity.applyFriction and AirplaneEntity.getGravity.
    effective_horizontal_speed = velocity.length() * (1.0 - abs(direction.y))
    gravity = max(0.0, 1.0 - effective_horizontal_speed * 1.5) * -0.04
    decay = 1.0 - friction
    velocity = angular.Vec(
        velocity.x * decay * horizontal_decay,
        velocity.y * decay * vertical_decay + gravity,
        velocity.z * decay * horizontal_decay,
    )

    # AircraftEntity.updateController uses the smoothed input from the previous tick.
    yaw = angular.wrap_degrees(state.yaw + yaw_speed * state.smoothed_x)
    pitch = state.pitch + pitch_speed * state.smoothed_z

    # AirplaneEntity.updateController adds thrust after the orientation update.
    thrust_direction = angular.forward(yaw, pitch)
    thrust = state.engine_power * state.engine_power * engine_speed
    velocity = velocity + thrust_direction.scale(thrust)
    position = state.position + velocity

    # VehicleEntity and EngineVehicle update their interpolators at the end of tick.
    smoothed_x = 0.9 * state.smoothed_x + 0.1 * command_x
    smoothed_z = 0.9 * state.smoothed_z + 0.1 * command_z
    engine_power = state.engine_power + (
        engine_target - state.engine_power
    ) / engine_reaction_steps

    return AircraftState(
        position=position,
        velocity=velocity,
        yaw=yaw,
        pitch=pitch,
        engine_power=engine_power,
        smoothed_x=smoothed_x,
        smoothed_z=smoothed_z,
    )


def simulate(args: argparse.Namespace) -> dict:
    p47_frames = angular.load_frames(args.p47)
    target_frames = angular.load_frames(args.target)
    if args.start_tick not in p47_frames or args.start_tick + 1 not in p47_frames:
        raise ValueError("start tick and following P-47N frame are required")
    if args.start_tick not in target_frames:
        raise ValueError("start tick is missing from target telemetry")

    initial = p47_frames[args.start_tick]
    following = p47_frames[args.start_tick + 1]
    smoothed_x, smoothed_z = infer_initial_smoothing(
        initial, following, args.yaw_speed, args.pitch_speed
    )
    state = AircraftState(
        position=initial.position,
        velocity=initial.velocity,
        yaw=initial.yaw,
        pitch=initial.pitch,
        engine_power=args.initial_engine_power
        if args.initial_engine_power is not None else args.recorded_engine_power,
        smoothed_x=smoothed_x,
        smoothed_z=smoothed_z,
    )
    candidate = angular.Candidate(
        climb_pitch=args.climb_pitch,
        yaw_trigger_pitch=args.yaw_trigger_pitch,
        pivot_complete_heading=args.pivot_complete_heading,
        pivot_divisor=args.pivot_divisor,
        capture_pitch_divisor=args.capture_pitch_divisor,
        capture_pitch_damping=args.capture_pitch_damping,
        yaw_damping=args.yaw_damping,
    )

    stage = "CLIMB"
    stage_ticks = 0
    previous_yaw = state.yaw
    previous_pitch = state.pitch
    rows: list[dict] = []
    first_attack = None

    for tick in range(args.start_tick, args.start_tick + args.max_ticks):
        target = target_frames.get(tick)
        if target is None:
            break
        lead_point = target.position + target.velocity.scale(args.lead_ticks)
        lead_direction = (lead_point - state.position).normalized()
        raw_direction = (target.position - state.position).normalized()
        aircraft_forward = angular.forward(state.yaw, state.pitch)
        horizontal_error = angular.signed_horizontal_angle(
            aircraft_forward, lead_direction
        )
        raw_angle = angular.angle_degrees(aircraft_forward, raw_direction)
        lead_angle = angular.angle_degrees(aircraft_forward, lead_direction)
        distance = (target.position - state.position).length()
        closure = closure_bps(
            state.position, state.velocity, target.position, target.velocity
        )
        speed_bps = state.velocity.length() * 20.0
        pitch_rate = state.pitch - previous_pitch
        yaw_rate = angular.wrap_degrees(state.yaw - previous_yaw)
        previous_pitch = state.pitch
        previous_yaw = state.yaw

        attack_sector = (
            raw_angle <= 45.0
            and lead_angle <= 12.0
            and 24.0 <= distance <= 125.0
            and -6.0 <= closure <= 28.0
        )
        row = {
            "tick": tick,
            "stage": stage,
            "position": asdict(state.position),
            "velocity_bpt": asdict(state.velocity),
            "yaw": state.yaw,
            "pitch": state.pitch,
            "speed_bps": speed_bps,
            "distance": distance,
            "closure_bps": closure,
            "raw_angle": raw_angle,
            "lead_angle": lead_angle,
            "horizontal_lead_error": horizontal_error,
            "engine_power": state.engine_power,
            "attack_sector": attack_sector,
        }
        rows.append(row)
        if attack_sector:
            first_attack = row
            break

        if stage == "CLIMB":
            if stage_ticks >= 8 and (
                state.pitch <= candidate.yaw_trigger_pitch
                or speed_bps <= args.stall_guard_speed * 1.60
            ):
                stage = "PIVOT"
                stage_ticks = 0
            elif stage_ticks >= 54:
                break

        if stage == "PIVOT":
            if stage_ticks >= 8 and (
                abs(horizontal_error) <= candidate.pivot_complete_heading
                or speed_bps <= args.stall_guard_speed * 1.45
            ):
                stage = "CAPTURE"
                stage_ticks = 0
            elif stage_ticks >= 96:
                break

        if stage == "CAPTURE" and (stage_ticks >= 190 or distance > 190.0):
            break

        if stage == "CLIMB":
            command_x = 0.0
            command_z = angular.clamp(
                (candidate.climb_pitch - state.pitch) / 12.0 - 0.25 * pitch_rate,
                -0.95, 0.35,
            )
            engine_target = 1.0
        elif stage == "PIVOT":
            command_x = angular.clamp(
                horizontal_error / candidate.pivot_divisor
                - candidate.yaw_damping * yaw_rate,
                -0.96, 0.96,
            )
            command_z = angular.clamp(
                (candidate.climb_pitch - state.pitch) / 12.0 - 0.30 * pitch_rate,
                -0.65, 0.65,
            )
            engine_target = 1.0
        else:
            target_pitch = angular.desired_pitch(lead_direction)
            command_x = angular.clamp(
                horizontal_error / 18.0 - candidate.yaw_damping * yaw_rate,
                -0.94, 0.94,
            )
            command_z = angular.clamp(
                (target_pitch - state.pitch) / candidate.capture_pitch_divisor
                - candidate.capture_pitch_damping * pitch_rate,
                -0.88, 0.88,
            )
            target_speed = max(
                args.cruise_speed,
                horizontal_speed(target.velocity) * 20.0 + 3.0,
            )
            if speed_bps < target_speed - 1.0:
                engine_target = 1.0
            elif speed_bps > target_speed + 3.0:
                engine_target = 0.30
            else:
                engine_target = 0.65

        state = physics_tick(
            state,
            command_x=command_x,
            command_z=command_z,
            engine_target=engine_target,
            engine_speed=args.engine_speed,
            lift=args.lift,
            friction=args.friction,
            glide_factor=args.glide_factor,
            horizontal_decay=args.horizontal_decay,
            vertical_decay=args.vertical_decay,
            yaw_speed=args.yaw_speed,
            pitch_speed=args.pitch_speed,
            engine_reaction_steps=args.engine_reaction_steps,
        )
        stage_ticks += 1

    return {
        "candidate": asdict(candidate),
        "start_tick": args.start_tick,
        "samples": len(rows),
        "modeled_attack": first_attack is not None,
        "first_attack": first_attack,
        "minimum_speed_bps": min((row["speed_bps"] for row in rows), default=None),
        "minimum_distance": min((row["distance"] for row in rows), default=None),
        "maximum_distance": max((row["distance"] for row in rows), default=None),
        "minimum_pitch": min((row["pitch"] for row in rows), default=None),
        "maximum_pitch": max((row["pitch"] for row in rows), default=None),
        "warning": "Target response, LOS, terrain, collision, and threat arbitration are not resimulated.",
        "rows": rows,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--p47", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--start-tick", type=int, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--max-ticks", type=int, default=390)
    parser.add_argument("--lead-ticks", type=float, default=8.0)

    parser.add_argument("--climb-pitch", type=float, default=-22.0)
    parser.add_argument("--yaw-trigger-pitch", type=float, default=0.0)
    parser.add_argument("--pivot-complete-heading", type=float, default=65.0)
    parser.add_argument("--pivot-divisor", type=float, default=38.0)
    parser.add_argument("--capture-pitch-divisor", type=float, default=12.0)
    parser.add_argument("--capture-pitch-damping", type=float, default=0.10)
    parser.add_argument("--yaw-damping", type=float, default=0.0)

    parser.add_argument("--engine-speed", type=float, default=0.102)
    parser.add_argument("--lift", type=float, default=0.165)
    parser.add_argument("--friction", type=float, default=0.013)
    parser.add_argument("--glide-factor", type=float, default=0.055)
    parser.add_argument("--horizontal-decay", type=float, default=0.97)
    parser.add_argument("--vertical-decay", type=float, default=0.97)
    parser.add_argument("--yaw-speed", type=float, default=2.5)
    parser.add_argument("--pitch-speed", type=float, default=2.4)
    parser.add_argument("--engine-reaction-steps", type=float, default=100.0)
    parser.add_argument("--cruise-speed", type=float, default=33.6741875662)
    parser.add_argument("--stall-guard-speed", type=float, default=10.1662137203)
    parser.add_argument("--recorded-engine-power", type=float, default=1.0)
    parser.add_argument("--initial-engine-power", type=float)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = simulate(args)
    summary = {key: value for key, value in result.items() if key != "rows"}
    print(json.dumps(summary, indent=2, sort_keys=True))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return 0 if result["modeled_attack"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
