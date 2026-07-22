#!/usr/bin/env python3
"""Replay a P-47N coupled-climb candidate with Immersive Aircraft physics.

Unlike ``analyze_apex_yaw_replay.py``, this tool advances the modeled P-47N position
and velocity. The target keeps its recorded real-physics trajectory, so the result is
still a pre-flight diagnostic rather than a replacement for Forge GameTest.

The default P-47N constants come from Warfare Wings 1.1.4 and Immersive Aircraft
1.3.3 for Minecraft 1.20.1. The update order mirrors the upstream implementation:

1. glide contribution and velocity-to-nose conversion;
2. drag, horizontal/vertical decay, and speed-dependent airplane gravity;
3. friction/rotation decay of the smoothed X/Z input, then yaw/pitch update;
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


def qualifies_for_headless(
    first_attack: dict | None,
    minimum_speed_bps: float | None,
    minimum_distance: float | None,
    minimum_estimated_agl: float | None,
    minimum_pull_out_margin: float | None,
    stall_guard_speed: float,
    minimum_separation: float,
) -> bool:
    return (
        first_attack is not None
        and minimum_speed_bps is not None
        and minimum_speed_bps >= stall_guard_speed
        and minimum_distance is not None
        and minimum_distance >= minimum_separation
        and minimum_estimated_agl is not None
        and minimum_estimated_agl > 0.0
        and minimum_pull_out_margin is not None
        and minimum_pull_out_margin >= 0.0
    )


def infer_initial_smoothing(first: angular.Frame, second: angular.Frame,
                            yaw_speed: float, pitch_speed: float,
                            friction: float,
                            rotation_decay: float) -> tuple[float, float]:
    decay = (1.0 - friction) * rotation_decay
    if abs(decay) <= 1.0e-12:
        raise ValueError("control decay must be non-zero")
    smoothed_x = angular.wrap_degrees(second.yaw - first.yaw) / (yaw_speed * decay)
    smoothed_z = (second.pitch - first.pitch) / (pitch_speed * decay)
    return smoothed_x, smoothed_z


def read_frame_engine_power(path: Path, tick: int) -> float | None:
    """Read the real engine-power interpolator value from the selected JSONL frame."""
    with path.open(encoding="utf-8") as handle:
        for raw in handle:
            try:
                row = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if row.get("event") != "frame" or int(row.get("server_tick", -1)) != tick:
                continue
            value = row.get("engine_power")
            if value is None:
                return None
            value = float(value)
            return value if math.isfinite(value) else None
    return None


def selected_candidate_defaults() -> dict[str, float | int | bool]:
    """Load the branch's machine-readable candidate, with safe fallback values."""
    defaults: dict[str, float | int | bool] = {
        "climb_pitch": -22.0,
        "yaw_trigger_pitch": -2.0,
        "pivot_complete_heading": 65.0,
        "pivot_divisor": 22.0,
        "capture_pitch_divisor": 10.0,
        "capture_pitch_damping": 0.10,
        "yaw_damping": 0.05,
        "lead_ticks": 8.0,
        "crossing_lag_enabled": True,
        "crossing_entry_min_raw_angle": 83.0,
        "crossing_entry_max_raw_angle": 92.0,
        "crossing_entry_min_closure": 0.0,
        "crossing_improvement_epsilon": 0.10,
        "crossing_stall_ticks": 2,
        "p47_legacy_heading_capture_enabled": False,
        "lag_ticks": 30,
        "lag_yaw_fraction": 0.25,
        "lag_target_pitch": -32.0,
        "approach_lead_ticks": 25.0,
        "reentry_speed_floor": 15.0,
        "reentry_target_speed_offset": -6.0,
        "reentry_min_agl": 90.0,
        "reentry_pull_out_seconds": 4.2,
    }
    path = Path(__file__).with_name("p47_coupled_climb_candidate.json")
    if not path.is_file():
        return defaults
    try:
        root = json.loads(path.read_text(encoding="utf-8"))
        parameters = root.get("parameters", {})
        for key in tuple(defaults):
            if key in parameters:
                fallback = defaults[key]
                raw_value = parameters[key]
                if isinstance(fallback, bool):
                    if isinstance(raw_value, bool):
                        defaults[key] = raw_value
                    continue
                value = float(raw_value)
                if math.isfinite(value):
                    defaults[key] = int(value) if isinstance(fallback, int) else value
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass
    return defaults


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
    rotation_decay: float,
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

    # InventoryVehicleEntity.applyFriction decays the interpolated controls before
    # AircraftEntity.updateController consumes them in the same tick.
    control_decay = decay * rotation_decay
    decayed_smoothed_x = state.smoothed_x * control_decay
    decayed_smoothed_z = state.smoothed_z * control_decay
    yaw = angular.wrap_degrees(state.yaw + yaw_speed * decayed_smoothed_x)
    pitch = state.pitch + pitch_speed * decayed_smoothed_z

    # AirplaneEntity.updateController adds thrust after the orientation update.
    thrust_direction = angular.forward(yaw, pitch)
    thrust = state.engine_power * state.engine_power * engine_speed
    velocity = velocity + thrust_direction.scale(thrust)
    position = state.position + velocity

    # VehicleEntity and EngineVehicle update their interpolators at the end of tick.
    smoothed_x = 0.9 * decayed_smoothed_x + 0.1 * command_x
    smoothed_z = 0.9 * decayed_smoothed_z + 0.1 * command_z
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
        initial, following, args.yaw_speed, args.pitch_speed,
        args.friction, args.rotation_decay
    )
    measured_engine_power = read_frame_engine_power(args.p47, args.start_tick)
    initial_engine_power = args.initial_engine_power
    if initial_engine_power is None:
        initial_engine_power = measured_engine_power
    if initial_engine_power is None:
        initial_engine_power = args.recorded_engine_power

    state = AircraftState(
        position=initial.position,
        velocity=initial.velocity,
        yaw=initial.yaw,
        pitch=initial.pitch,
        engine_power=initial_engine_power,
        smoothed_x=smoothed_x,
        smoothed_z=smoothed_z,
    )
    estimated_ground_y = initial.position.y - initial.agl
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
    previous_raw_angle = None
    crossing_stall_ticks = 0
    rows: list[dict] = []
    first_attack = None
    termination_reason = "max_ticks"

    for tick in range(args.start_tick, args.start_tick + args.max_ticks):
        target = target_frames.get(tick)
        if target is None:
            termination_reason = "target_missing"
            break
        lead_point = target.position + target.velocity.scale(args.lead_ticks)
        lead_direction = (lead_point - state.position).normalized()
        approach_lead_point = target.position + target.velocity.scale(
            args.approach_lead_ticks
        )
        approach_lead_direction = (approach_lead_point - state.position).normalized()
        raw_direction = (target.position - state.position).normalized()
        aircraft_forward = angular.forward(state.yaw, state.pitch)
        horizontal_error = angular.signed_horizontal_angle(
            aircraft_forward, lead_direction
        )
        raw_angle = angular.angle_degrees(aircraft_forward, raw_direction)
        raw_angle_improvement = (
            None
            if previous_raw_angle is None
            else previous_raw_angle - raw_angle
        )
        previous_raw_angle = raw_angle
        lead_angle = angular.angle_degrees(aircraft_forward, lead_direction)
        distance = (target.position - state.position).length()
        closure = closure_bps(
            state.position, state.velocity, target.position, target.velocity
        )
        speed_bps = state.velocity.length() * 20.0
        vertical_speed_bps = state.velocity.y * 20.0
        estimated_agl = state.position.y - estimated_ground_y
        required_pull_out_agl = max(
            args.reentry_min_agl,
            max(0.0, -vertical_speed_bps) * args.reentry_pull_out_seconds,
        )
        pitch_rate = state.pitch - previous_pitch
        yaw_rate = angular.wrap_degrees(state.yaw - previous_yaw)
        previous_pitch = state.pitch
        previous_yaw = state.yaw

        if (
            stage == "PIVOT"
            and args.crossing_entry_min_raw_angle
            <= raw_angle
            <= args.crossing_entry_raw_angle
            and raw_angle_improvement is not None
            and abs(raw_angle_improvement) <= args.crossing_improvement_epsilon
        ):
            crossing_stall_ticks += 1
        else:
            crossing_stall_ticks = 0

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
            "vertical_speed_bps": vertical_speed_bps,
            "distance": distance,
            "closure_bps": closure,
            "raw_angle": raw_angle,
            "raw_angle_improvement": raw_angle_improvement,
            "crossing_stall_ticks": crossing_stall_ticks,
            "lead_angle": lead_angle,
            "horizontal_lead_error": horizontal_error,
            "engine_power": state.engine_power,
            "estimated_agl": estimated_agl,
            "required_pull_out_agl": required_pull_out_agl,
            "pull_out_margin": estimated_agl - required_pull_out_agl,
            "attack_sector": attack_sector,
        }
        rows.append(row)

        if stage == "CLIMB":
            if stage_ticks >= 8 and (
                state.pitch <= candidate.yaw_trigger_pitch
                or speed_bps <= args.stall_guard_speed * 1.60
            ):
                stage = "PIVOT"
                stage_ticks = 0
            elif stage_ticks >= 54:
                termination_reason = "climb_timeout"
                break

        if stage == "PIVOT":
            energy_guard = (
                stage_ticks >= 8
                and speed_bps <= args.stall_guard_speed * 1.45
            )
            lag_handoff = (
                args.crossing_lag
                and stage_ticks >= 8
                and crossing_stall_ticks >= args.crossing_stall_ticks
                and raw_angle <= args.crossing_entry_raw_angle
                and closure >= args.crossing_entry_min_closure
            )
            if energy_guard:
                stage = "CAPTURE"
                stage_ticks = 0
            elif lag_handoff:
                stage = "LAG"
                stage_ticks = 0
            elif (
                args.p47_legacy_heading_capture_enabled
                and stage_ticks >= 8
                and abs(horizontal_error) <= candidate.pivot_complete_heading
            ):
                stage = "CAPTURE"
                stage_ticks = 0
            elif stage_ticks >= 96:
                termination_reason = "pivot_timeout"
                break

        if stage == "LAG" and stage_ticks >= args.lag_ticks:
            stage = "APPROACH"
            stage_ticks = 0

        if (stage in {"LAG", "APPROACH"}
                and speed_bps <= args.stall_guard_speed * 1.45):
            termination_reason = "reentry_energy_guard"
            break

        if stage in {"LAG", "APPROACH"} and row["pull_out_margin"] < 0.0:
            termination_reason = "reentry_pull_out_guard"
            break

        if stage in {"CAPTURE", "APPROACH"} and attack_sector:
            first_attack = row
            termination_reason = "attack_sector_reached"
            break

        if stage in {"CAPTURE", "APPROACH"} and (
            stage_ticks >= 190 or distance > 190.0
        ):
            termination_reason = "capture_timeout"
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
        elif stage == "LAG":
            raw_horizontal_error = angular.signed_horizontal_angle(
                aircraft_forward, raw_direction
            )
            full_yaw_command = angular.clamp(
                raw_horizontal_error / candidate.pivot_divisor
                - candidate.yaw_damping * yaw_rate,
                -0.96,
                0.96,
            )
            command_x = full_yaw_command * args.lag_yaw_fraction
            command_z = angular.clamp(
                (args.lag_climb_pitch - state.pitch) / 12.0 - 0.30 * pitch_rate,
                -0.95,
                0.65,
            )
            target_speed = max(
                args.lag_speed_floor,
                horizontal_speed(target.velocity) * 20.0
                + args.lag_target_speed_offset,
            )
            if speed_bps < target_speed - 1.0:
                engine_target = 1.0
            elif speed_bps > target_speed + 3.0:
                engine_target = 0.10
            else:
                engine_target = 0.35
        else:
            control_lead_direction = (
                approach_lead_direction if stage == "APPROACH" else lead_direction
            )
            control_horizontal_error = angular.signed_horizontal_angle(
                aircraft_forward, control_lead_direction
            )
            target_pitch = angular.desired_pitch(control_lead_direction)
            command_x = angular.clamp(
                control_horizontal_error / 18.0
                - candidate.yaw_damping * yaw_rate,
                -0.94, 0.94,
            )
            command_z = angular.clamp(
                (target_pitch - state.pitch) / candidate.capture_pitch_divisor
                - candidate.capture_pitch_damping * pitch_rate,
                -0.88, 0.88,
            )
            if stage == "APPROACH":
                target_speed = max(
                    args.lag_speed_floor,
                    horizontal_speed(target.velocity) * 20.0
                    + args.lag_target_speed_offset,
                )
            else:
                target_speed = max(
                    args.cruise_speed,
                    horizontal_speed(target.velocity) * 20.0 + 3.0,
                )
            if speed_bps < target_speed - 1.0:
                engine_target = 1.0
            elif speed_bps > target_speed + 3.0:
                engine_target = 0.10 if stage == "APPROACH" else 0.30
            else:
                engine_target = 0.35 if stage == "APPROACH" else 0.65

        row["command_x"] = command_x
        row["command_z"] = command_z
        row["engine_target"] = engine_target

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
            rotation_decay=args.rotation_decay,
            yaw_speed=args.yaw_speed,
            pitch_speed=args.pitch_speed,
            engine_reaction_steps=args.engine_reaction_steps,
        )
        stage_ticks += 1

    minimum_speed_bps = min((row["speed_bps"] for row in rows), default=None)
    minimum_distance = min((row["distance"] for row in rows), default=None)
    minimum_estimated_agl = min(
        (row["estimated_agl"] for row in rows), default=None
    )
    minimum_pull_out_margin = min(
        (row["pull_out_margin"] for row in rows), default=None
    )
    qualified = qualifies_for_headless(
        first_attack,
        minimum_speed_bps,
        minimum_distance,
        minimum_estimated_agl,
        minimum_pull_out_margin,
        args.stall_guard_speed,
        args.minimum_separation,
    )

    return {
        "candidate": asdict(candidate),
        "start_tick": args.start_tick,
        "initial_engine_power": initial_engine_power,
        "initial_engine_power_source": (
            "override" if args.initial_engine_power is not None
            else "telemetry" if measured_engine_power is not None
            else "fallback"
        ),
        "samples": len(rows),
        "modeled_attack": first_attack is not None,
        "qualified_for_headless": qualified,
        "termination_reason": termination_reason,
        "first_attack": first_attack,
        "minimum_speed_bps": minimum_speed_bps,
        "minimum_distance": minimum_distance,
        "maximum_distance": max((row["distance"] for row in rows), default=None),
        "minimum_pitch": min((row["pitch"] for row in rows), default=None),
        "maximum_pitch": max((row["pitch"] for row in rows), default=None),
        "minimum_estimated_agl": minimum_estimated_agl,
        "minimum_pull_out_margin": minimum_pull_out_margin,
        "qualification_gates": {
            "minimum_separation_blocks": args.minimum_separation,
            "minimum_speed_bps": args.stall_guard_speed,
            "minimum_estimated_agl_exclusive": 0.0,
            "minimum_pull_out_margin": 0.0,
        },
        "control_decay_per_tick": (1.0 - args.friction) * args.rotation_decay,
        "crossing_lag": {
            "enabled": args.crossing_lag,
            "entry_raw_angle": args.crossing_entry_raw_angle,
            "entry_min_raw_angle": args.crossing_entry_min_raw_angle,
            "entry_min_closure": args.crossing_entry_min_closure,
            "improvement_epsilon_deg_per_tick": args.crossing_improvement_epsilon,
            "stall_ticks": args.crossing_stall_ticks,
            "lag_ticks": args.lag_ticks,
            "yaw_fraction": args.lag_yaw_fraction,
            "climb_pitch": args.lag_climb_pitch,
            "approach_lead_ticks": args.approach_lead_ticks,
            "speed_floor_bps": args.lag_speed_floor,
            "target_speed_offset_bps": args.lag_target_speed_offset,
            "minimum_agl": args.reentry_min_agl,
            "pull_out_seconds": args.reentry_pull_out_seconds,
        },
        "warning": "Target response, LOS, terrain, collision, and threat arbitration are not resimulated.",
        "rows": rows,
    }


def build_parser() -> argparse.ArgumentParser:
    selected = selected_candidate_defaults()
    parser = argparse.ArgumentParser()
    parser.add_argument("--p47", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--start-tick", type=int, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--max-ticks", type=int, default=390)
    parser.add_argument("--lead-ticks", type=float, default=selected["lead_ticks"])

    parser.add_argument("--climb-pitch", type=float, default=selected["climb_pitch"])
    parser.add_argument("--yaw-trigger-pitch", type=float,
                        default=selected["yaw_trigger_pitch"])
    parser.add_argument("--pivot-complete-heading", type=float,
                        default=selected["pivot_complete_heading"])
    parser.add_argument("--pivot-divisor", type=float,
                        default=selected["pivot_divisor"])
    parser.add_argument("--capture-pitch-divisor", type=float,
                        default=selected["capture_pitch_divisor"])
    parser.add_argument("--capture-pitch-damping", type=float,
                        default=selected["capture_pitch_damping"])
    parser.add_argument("--yaw-damping", type=float,
                        default=selected["yaw_damping"])

    parser.add_argument("--engine-speed", type=float, default=0.102)
    parser.add_argument("--lift", type=float, default=0.165)
    parser.add_argument("--friction", type=float, default=0.013)
    parser.add_argument("--glide-factor", type=float, default=0.055)
    parser.add_argument("--horizontal-decay", type=float, default=0.97)
    parser.add_argument("--vertical-decay", type=float, default=0.97)
    parser.add_argument("--rotation-decay", type=float, default=0.97)
    parser.add_argument("--yaw-speed", type=float, default=2.5)
    parser.add_argument("--pitch-speed", type=float, default=2.4)
    parser.add_argument("--engine-reaction-steps", type=float, default=100.0)
    parser.add_argument("--cruise-speed", type=float, default=33.6741875662)
    parser.add_argument("--stall-guard-speed", type=float, default=10.1662137203)
    parser.add_argument("--minimum-separation", type=float, default=8.0)
    parser.add_argument(
        "--crossing-lag",
        action=argparse.BooleanOptionalAction,
        default=selected["crossing_lag_enabled"],
    )
    parser.add_argument(
        "--crossing-entry-raw-angle",
        type=float,
        default=selected["crossing_entry_max_raw_angle"],
    )
    parser.add_argument(
        "--crossing-entry-min-raw-angle",
        type=float,
        default=selected["crossing_entry_min_raw_angle"],
    )
    parser.add_argument(
        "--crossing-entry-min-closure",
        type=float,
        default=selected["crossing_entry_min_closure"],
    )
    parser.add_argument(
        "--crossing-improvement-epsilon",
        type=float,
        default=selected["crossing_improvement_epsilon"],
    )
    parser.add_argument(
        "--crossing-stall-ticks",
        type=int,
        default=selected["crossing_stall_ticks"],
    )
    parser.add_argument(
        "--p47-legacy-heading-capture",
        dest="p47_legacy_heading_capture_enabled",
        action=argparse.BooleanOptionalAction,
        default=selected["p47_legacy_heading_capture_enabled"],
    )
    parser.add_argument("--lag-ticks", type=int, default=selected["lag_ticks"])
    parser.add_argument(
        "--lag-yaw-fraction", type=float, default=selected["lag_yaw_fraction"]
    )
    parser.add_argument(
        "--lag-climb-pitch", type=float, default=selected["lag_target_pitch"]
    )
    parser.add_argument(
        "--approach-lead-ticks", type=float, default=selected["approach_lead_ticks"]
    )
    parser.add_argument(
        "--lag-speed-floor", type=float, default=selected["reentry_speed_floor"]
    )
    parser.add_argument(
        "--lag-target-speed-offset",
        type=float,
        default=selected["reentry_target_speed_offset"],
    )
    parser.add_argument(
        "--reentry-min-agl", type=float, default=selected["reentry_min_agl"]
    )
    parser.add_argument(
        "--reentry-pull-out-seconds",
        type=float,
        default=selected["reentry_pull_out_seconds"],
    )
    parser.add_argument("--recorded-engine-power", type=float, default=1.0,
                        help="Fallback only when the selected JSONL frame lacks engine_power")
    parser.add_argument("--initial-engine-power", type=float,
                        help="Optional explicit override of the telemetry engine power")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = simulate(args)
    summary = {key: value for key, value in result.items() if key != "rows"}
    print(json.dumps(summary, indent=2, sort_keys=True))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return 0 if result["qualified_for_headless"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
