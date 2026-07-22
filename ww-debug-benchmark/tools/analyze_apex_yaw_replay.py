#!/usr/bin/env python3
"""Replay preserved mutual-dogfight telemetry through Immersive Aircraft input smoothing.

This tool does not replace the real Forge GameTest. It cheaply rejects angular-control
candidates that cannot rotate the P-47N into a firing sector even when the preserved
P-47N/A6M positions are reused.

The orientation model follows Immersive Aircraft 1.20.1:
  smooth = 0.9 * smooth + 0.1 * command
  yaw += yaw_speed * logical_x_smooth
  pitch += pitch_speed * z_smooth

The benchmark adapter inverts logical X before calling the native API, while the
aircraft subtracts native X from yaw. The two inversions therefore produce the
logical yaw update shown above.
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Vec:
    x: float
    y: float
    z: float

    def __add__(self, other: "Vec") -> "Vec":
        return Vec(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: "Vec") -> "Vec":
        return Vec(self.x - other.x, self.y - other.y, self.z - other.z)

    def scale(self, value: float) -> "Vec":
        return Vec(self.x * value, self.y * value, self.z * value)

    def dot(self, other: "Vec") -> float:
        return self.x * other.x + self.y * other.y + self.z * other.z

    def length(self) -> float:
        return math.sqrt(self.dot(self))

    def normalized(self, fallback: "Vec" | None = None) -> "Vec":
        length = self.length()
        if length > 1.0e-9:
            return self.scale(1.0 / length)
        return fallback or Vec(0.0, 0.0, 1.0)

    def horizontal(self) -> "Vec":
        return Vec(self.x, 0.0, self.z).normalized()


@dataclass(frozen=True)
class Frame:
    tick: int
    position: Vec
    velocity: Vec
    yaw: float
    pitch: float
    speed_bps: float
    agl: float


@dataclass(frozen=True)
class Candidate:
    climb_pitch: float
    yaw_trigger_pitch: float
    pivot_complete_heading: float
    pivot_divisor: float
    capture_pitch_divisor: float
    capture_pitch_damping: float
    yaw_damping: float


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def wrap_degrees(value: float) -> float:
    return (value + 180.0) % 360.0 - 180.0


def vector(data: dict[str, float]) -> Vec:
    return Vec(float(data["x"]), float(data["y"]), float(data["z"]))


def forward(yaw_deg: float, pitch_deg: float) -> Vec:
    yaw = math.radians(yaw_deg)
    pitch = math.radians(pitch_deg)
    return Vec(
        -math.sin(yaw) * math.cos(pitch),
        -math.sin(pitch),
        math.cos(yaw) * math.cos(pitch),
    )


def angle_degrees(first: Vec, second: Vec) -> float:
    a = first.normalized()
    b = second.normalized()
    return math.degrees(math.acos(clamp(a.dot(b), -1.0, 1.0)))


def signed_horizontal_angle(current: Vec, desired: Vec) -> float:
    first = current.horizontal()
    second = desired.horizontal()
    dot = clamp(first.dot(second), -1.0, 1.0)
    cross = first.x * second.z - first.z * second.x
    return math.degrees(math.atan2(cross, dot))


def desired_pitch(direction: Vec) -> float:
    normalized = direction.normalized()
    return -math.degrees(math.asin(clamp(normalized.y, -1.0, 1.0)))


def load_frames(path: Path) -> dict[int, Frame]:
    frames: dict[int, Frame] = {}
    with path.open(encoding="utf-8") as handle:
        for raw in handle:
            try:
                row = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if row.get("event") != "frame":
                continue
            tick = int(row["server_tick"])
            frames[tick] = Frame(
                tick=tick,
                position=vector(row["position"]),
                velocity=vector(row["velocity_bpt"]),
                yaw=float(row["yaw_deg"]),
                pitch=float(row["pitch_deg"]),
                speed_bps=float(row["speed_bps"]),
                agl=float(row["altitude_above_ground"]),
            )
    if not frames:
        raise ValueError(f"no frame rows found in {path}")
    return frames


def simulate(
    p47_frames: dict[int, Frame],
    target_frames: dict[int, Frame],
    start_tick: int,
    candidate: Candidate,
    *,
    lead_ticks: float,
    max_ticks: int,
    yaw_speed: float,
    pitch_speed: float,
) -> dict:
    initial = p47_frames[start_tick]
    yaw = initial.yaw
    pitch = initial.pitch
    smoothed_x = 0.0
    smoothed_z = 0.0
    previous_yaw = yaw
    previous_pitch = pitch
    stage = "CLIMB"
    stage_ticks = 0
    rows: list[dict] = []

    for tick in range(start_tick, start_tick + max_ticks):
        p47 = p47_frames.get(tick)
        target = target_frames.get(tick)
        if p47 is None or target is None:
            break

        lead_point = target.position + target.velocity.scale(lead_ticks)
        lead_direction = (lead_point - p47.position).normalized()
        raw_direction = (target.position - p47.position).normalized()
        aircraft_forward = forward(yaw, pitch)
        horizontal_error = signed_horizontal_angle(aircraft_forward, lead_direction)
        raw_angle = angle_degrees(aircraft_forward, raw_direction)
        lead_angle = angle_degrees(aircraft_forward, lead_direction)
        pitch_rate = pitch - previous_pitch
        yaw_rate = wrap_degrees(yaw - previous_yaw)
        previous_pitch = pitch
        previous_yaw = yaw

        if stage == "CLIMB":
            x_command = 0.0
            z_command = clamp(
                (candidate.climb_pitch - pitch) / 12.0 - 0.25 * pitch_rate,
                -0.95,
                0.35,
            )
            if pitch <= candidate.yaw_trigger_pitch:
                stage = "PIVOT"
                stage_ticks = 0
        elif stage == "PIVOT":
            x_command = clamp(
                horizontal_error / candidate.pivot_divisor
                - candidate.yaw_damping * yaw_rate,
                -0.96,
                0.96,
            )
            z_command = clamp(
                (candidate.climb_pitch - pitch) / 12.0 - 0.30 * pitch_rate,
                -0.65,
                0.65,
            )
            if stage_ticks >= 8 and abs(horizontal_error) <= candidate.pivot_complete_heading:
                stage = "CAPTURE"
                stage_ticks = 0
        else:
            target_pitch = desired_pitch(lead_direction)
            x_command = clamp(
                horizontal_error / 18.0 - candidate.yaw_damping * yaw_rate,
                -0.94,
                0.94,
            )
            z_command = clamp(
                (target_pitch - pitch) / candidate.capture_pitch_divisor
                - candidate.capture_pitch_damping * pitch_rate,
                -0.88,
                0.88,
            )

        # VehicleEntity updates orientation with the previous smoothed input,
        # then updates the 10-tick interpolator at the end of the tick.
        yaw += yaw_speed * smoothed_x
        pitch += pitch_speed * smoothed_z
        smoothed_x = 0.9 * smoothed_x + 0.1 * x_command
        smoothed_z = 0.9 * smoothed_z + 0.1 * z_command

        rows.append(
            {
                "tick": tick,
                "stage": stage,
                "yaw": yaw,
                "pitch": pitch,
                "horizontal_lead_error": horizontal_error,
                "raw_angle": raw_angle,
                "lead_angle": lead_angle,
                "x_command": x_command,
                "z_command": z_command,
                "smoothed_x": smoothed_x,
                "smoothed_z": smoothed_z,
                "recorded_speed_bps": p47.speed_bps,
                "recorded_agl": p47.agl,
            }
        )
        stage_ticks += 1

    attack_rows = [
        row for row in rows
        if row["raw_angle"] <= 45.0 and row["lead_angle"] <= 12.0
    ]
    return {
        "candidate": candidate.__dict__,
        "start_tick": start_tick,
        "samples": len(rows),
        "first_capture_tick": next(
            (row["tick"] for row in rows if row["stage"] == "CAPTURE"), None
        ),
        "first_modeled_attack_tick": attack_rows[0]["tick"] if attack_rows else None,
        "minimum_raw_angle": min((row["raw_angle"] for row in rows), default=None),
        "minimum_lead_angle": min((row["lead_angle"] for row in rows), default=None),
        "minimum_pitch": min((row["pitch"] for row in rows), default=None),
        "maximum_pitch": max((row["pitch"] for row in rows), default=None),
        "rows": rows,
    }


def candidate_from_args(args: argparse.Namespace) -> Candidate:
    return Candidate(
        climb_pitch=args.climb_pitch,
        yaw_trigger_pitch=args.yaw_trigger_pitch,
        pivot_complete_heading=args.pivot_complete_heading,
        pivot_divisor=args.pivot_divisor,
        capture_pitch_divisor=args.capture_pitch_divisor,
        capture_pitch_damping=args.capture_pitch_damping,
        yaw_damping=args.yaw_damping,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--p47", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--start-tick", type=int, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--lead-ticks", type=float, default=8.0)
    parser.add_argument("--max-ticks", type=int, default=220)
    parser.add_argument("--yaw-speed", type=float, default=2.5)
    parser.add_argument("--pitch-speed", type=float, default=2.4)
    parser.add_argument("--climb-pitch", type=float, default=-34.0)
    parser.add_argument("--yaw-trigger-pitch", type=float, default=-20.0)
    parser.add_argument("--pivot-complete-heading", type=float, default=28.0)
    parser.add_argument("--pivot-divisor", type=float, default=26.0)
    parser.add_argument("--capture-pitch-divisor", type=float, default=11.0)
    parser.add_argument("--capture-pitch-damping", type=float, default=0.20)
    parser.add_argument("--yaw-damping", type=float, default=0.16)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    p47_frames = load_frames(args.p47)
    target_frames = load_frames(args.target)
    if args.start_tick not in p47_frames or args.start_tick not in target_frames:
        raise ValueError(f"start tick {args.start_tick} is missing from one telemetry file")
    result = simulate(
        p47_frames,
        target_frames,
        args.start_tick,
        candidate_from_args(args),
        lead_ticks=args.lead_ticks,
        max_ticks=args.max_ticks,
        yaw_speed=args.yaw_speed,
        pitch_speed=args.pitch_speed,
    )
    summary = {key: value for key, value in result.items() if key != "rows"}
    print(json.dumps(summary, indent=2, sort_keys=True))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
