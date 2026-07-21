#!/usr/bin/env python3
"""Rank oblique lag-yoyo candidates from WW Debug JSONL telemetry.

The target follows its recorded path. The candidate aircraft is a capped-rate point mass that
uses its measured speed and measured yaw/pitch response. This is intentionally not a replacement
for Immersive Aircraft physics; it is a deterministic filter for choosing one control hypothesis
before spending a remote Forge GameTest run.
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Sequence

EPSILON = 1.0e-9
TICKS_PER_SECOND = 20.0


@dataclass(frozen=True)
class Vec3:
    x: float
    y: float
    z: float

    def __add__(self, other: "Vec3") -> "Vec3":
        return Vec3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: "Vec3") -> "Vec3":
        return Vec3(self.x - other.x, self.y - other.y, self.z - other.z)

    def __mul__(self, scalar: float) -> "Vec3":
        return Vec3(self.x * scalar, self.y * scalar, self.z * scalar)

    __rmul__ = __mul__

    def dot(self, other: "Vec3") -> float:
        return self.x * other.x + self.y * other.y + self.z * other.z

    def length(self) -> float:
        return math.sqrt(self.dot(self))

    def normalized(self, fallback: "Vec3" | None = None) -> "Vec3":
        length = self.length()
        if length > EPSILON:
            return self * (1.0 / length)
        return fallback if fallback is not None else Vec3(0.0, 0.0, 1.0)

    def horizontal(self) -> "Vec3":
        return Vec3(self.x, 0.0, self.z)


@dataclass(frozen=True)
class Frame:
    tick: int
    position: Vec3
    velocity_bps: Vec3
    forward: Vec3
    speed_bps: float
    yaw_rate_deg_s: float
    pitch_rate_deg_s: float


@dataclass(frozen=True)
class Telemetry:
    frames: dict[int, Frame]
    handoff_ticks: tuple[int, ...]


@dataclass(frozen=True)
class Candidate:
    lag_ticks: int
    lag_yaw_fraction: float
    climb_angle_deg: float
    lead_seconds: float
    speed_floor_bps: float
    target_speed_offset_bps: float


@dataclass(frozen=True)
class Result:
    candidate: Candidate
    score: float
    first_attack_tick: int | None
    first_narrow_tick: int | None
    attack_sector_ticks: int
    narrow_sector_ticks: int
    min_separation: float
    min_raw_angle_deg: float
    final_separation: float
    final_raw_angle_deg: float
    final_closure_bps: float
    final_altitude_advantage: float


def parse_vec(value: dict[str, float]) -> Vec3:
    return Vec3(float(value["x"]), float(value["y"]), float(value["z"]))


def read_telemetry(path: Path) -> Telemetry:
    frames: dict[int, Frame] = {}
    handoffs: list[int] = []
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_number, raw in enumerate(handle, 1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                event = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
            if event.get("event") == "energy_crossing_reentry_transition":
                reason = str(event.get("reason", ""))
                if ("best_crossing_geometry_stalled" in reason
                        or "vertical_zoom_at_crossing_minimum" in reason):
                    handoffs.append(int(event["server_tick"]))
            if event.get("event") != "frame":
                continue
            try:
                tick = int(event["server_tick"])
                velocity_bpt = parse_vec(event["velocity_bpt"])
                frames[tick] = Frame(
                    tick=tick,
                    position=parse_vec(event["position"]),
                    velocity_bps=velocity_bpt * TICKS_PER_SECOND,
                    forward=parse_vec(event["aircraft_forward"]).normalized(),
                    speed_bps=float(event["speed_bps"]),
                    yaw_rate_deg_s=float(event.get("yaw_rate_deg_s", 0.0)),
                    pitch_rate_deg_s=float(event.get("pitch_rate_deg_s", 0.0)),
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"{path}:{line_number}: incomplete frame: {exc}") from exc
    if not frames:
        raise ValueError(f"{path}: no frame events found")
    return Telemetry(frames, tuple(handoffs))


def angle_deg(first: Vec3, second: Vec3) -> float:
    cosine = first.normalized().dot(second.normalized())
    return math.degrees(math.acos(max(-1.0, min(1.0, cosine))))


def rotate_toward(current: Vec3, desired: Vec3, max_angle_rad: float) -> Vec3:
    current = current.normalized()
    desired = desired.normalized(current)
    angle = math.acos(max(-1.0, min(1.0, current.dot(desired))))
    if angle <= max_angle_rad or angle < EPSILON:
        return desired
    fraction = max_angle_rad / angle
    return (current * (1.0 - fraction) + desired * fraction).normalized(current)


def constrained_direction(current: Vec3, desired: Vec3,
                          max_yaw_rad: float, max_pitch_rad: float) -> Vec3:
    current_h = current.horizontal().normalized(Vec3(0.0, 0.0, 1.0))
    desired_h = desired.horizontal().normalized(current_h)
    horizontal = rotate_toward(current_h, desired_h, max_yaw_rad)
    current_pitch = math.asin(max(-1.0, min(1.0, current.normalized().y)))
    desired_pitch = math.asin(max(-1.0, min(1.0, desired.normalized().y)))
    pitch_delta = max(-max_pitch_rad, min(max_pitch_rad, desired_pitch - current_pitch))
    pitch = current_pitch + pitch_delta
    horizontal_scale = math.cos(pitch)
    return Vec3(horizontal.x * horizontal_scale, math.sin(pitch),
                horizontal.z * horizontal_scale).normalized(current)


def closure_bps(own_position: Vec3, own_velocity: Vec3,
                target_position: Vec3, target_velocity: Vec3) -> float:
    line = target_position - own_position
    if line.length() < EPSILON:
        return 0.0
    return -(target_velocity - own_velocity).dot(line.normalized())


def percentile(values: Sequence[float], fraction: float) -> float:
    ordered = sorted(abs(value) for value in values if math.isfinite(value))
    if not ordered:
        return 0.0
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return ordered[index]


def estimate_rate_caps(frames: dict[int, Frame], start_tick: int,
                       lookback_ticks: int) -> tuple[float, float]:
    relevant = [frame for tick, frame in frames.items()
                if start_tick - lookback_ticks <= tick <= start_tick]
    yaw = percentile([frame.yaw_rate_deg_s for frame in relevant], 0.85)
    pitch = percentile([frame.pitch_rate_deg_s for frame in relevant], 0.85)
    return max(18.0, min(65.0, yaw)), max(8.0, min(30.0, pitch))


def frame_at(frames: dict[int, Frame], tick: int) -> Frame:
    direct = frames.get(tick)
    if direct is not None:
        return direct
    earlier = [known for known in frames if known < tick]
    later = [known for known in frames if known > tick]
    if not earlier or not later:
        raise KeyError(f"telemetry does not cover tick {tick}")
    low_tick = max(earlier)
    high_tick = min(later)
    low = frames[low_tick]
    high = frames[high_tick]
    alpha = (tick - low_tick) / (high_tick - low_tick)

    def lerp(first: float, second: float) -> float:
        return first + (second - first) * alpha

    return Frame(
        tick=tick,
        position=Vec3(lerp(low.position.x, high.position.x),
                      lerp(low.position.y, high.position.y),
                      lerp(low.position.z, high.position.z)),
        velocity_bps=Vec3(lerp(low.velocity_bps.x, high.velocity_bps.x),
                          lerp(low.velocity_bps.y, high.velocity_bps.y),
                          lerp(low.velocity_bps.z, high.velocity_bps.z)),
        forward=(low.forward * (1.0 - alpha) + high.forward * alpha).normalized(low.forward),
        speed_bps=lerp(low.speed_bps, high.speed_bps),
        yaw_rate_deg_s=lerp(low.yaw_rate_deg_s, high.yaw_rate_deg_s),
        pitch_rate_deg_s=lerp(low.pitch_rate_deg_s, high.pitch_rate_deg_s),
    )


def choose_start_tick(own: Telemetry, target: Telemetry, explicit: int | None) -> int:
    common = sorted(set(own.frames) & set(target.frames))
    if explicit is not None:
        if explicit not in own.frames:
            raise ValueError(f"own log has no frame at start tick {explicit}")
        return explicit
    candidates = [tick for tick in own.handoff_ticks if common[0] <= tick <= common[-1]]
    if candidates:
        return candidates[-1]
    scored: list[tuple[float, int]] = []
    for tick in common:
        own_frame = own.frames[tick]
        target_frame = target.frames[tick]
        relative = target_frame.position - own_frame.position
        raw_angle = angle_deg(own_frame.forward, relative)
        closure = closure_bps(own_frame.position, own_frame.velocity_bps,
                              target_frame.position, target_frame.velocity_bps)
        if 79.0 <= raw_angle <= 90.0 and closure > 0.0:
            scored.append((abs(raw_angle - 86.0), tick))
    if not scored:
        raise ValueError("no crossing-minimum handoff found; pass --start-tick")
    return min(scored)[1]


def candidate_grid() -> Iterator[Candidate]:
    for lag_ticks in (20, 30, 40, 60, 80):
        for yaw_fraction in (0.25, 0.5, 0.75, 1.0):
            for climb_angle in (8.0, 16.0, 24.0, 32.0):
                for lead_seconds in (0.5, 0.75, 1.0, 1.25):
                    for speed_floor in (15.0, 18.0, 20.0):
                        for speed_offset in (-6.0, -3.0, 0.0):
                            yield Candidate(lag_ticks, yaw_fraction, climb_angle,
                                            lead_seconds, speed_floor, speed_offset)


def simulate(start: Frame, target_frames: dict[int, Frame], candidate: Candidate,
             duration_ticks: int, yaw_cap_deg_s: float, pitch_cap_deg_s: float,
             min_safe_separation: float) -> Result:
    position = start.position
    direction = start.forward
    speed = start.speed_bps
    min_separation = math.inf
    min_raw_angle = 180.0
    first_attack: int | None = None
    first_narrow: int | None = None
    attack_ticks = 0
    narrow_ticks = 0
    final_separation = math.inf
    final_angle = 180.0
    final_closure = 0.0
    final_altitude_advantage = 0.0
    max_yaw = math.radians(yaw_cap_deg_s / TICKS_PER_SECOND)
    max_pitch = math.radians(pitch_cap_deg_s / TICKS_PER_SECOND)
    speed_response_bps_per_tick = 2.0 / TICKS_PER_SECOND

    for offset in range(duration_ticks + 1):
        target = frame_at(target_frames, start.tick + offset)
        relative = target.position - position
        if offset < candidate.lag_ticks:
            line_horizontal = relative.horizontal().normalized(direction.horizontal().normalized())
            horizontal = rotate_toward(direction.horizontal(), line_horizontal,
                                       max_yaw * candidate.lag_yaw_fraction)
            climb = math.radians(candidate.climb_angle_deg)
            desired = Vec3(horizontal.x * math.cos(climb), math.sin(climb),
                           horizontal.z * math.cos(climb))
            direction = constrained_direction(direction, desired,
                                              max_yaw * candidate.lag_yaw_fraction, max_pitch)
        else:
            lead_point = target.position + target.velocity_bps * candidate.lead_seconds
            direction = constrained_direction(direction, lead_point - position,
                                              max_yaw, max_pitch)

        desired_speed = max(candidate.speed_floor_bps,
                            target.speed_bps + candidate.target_speed_offset_bps)
        speed_error = desired_speed - speed
        speed += max(-speed_response_bps_per_tick,
                     min(speed_response_bps_per_tick, speed_error))
        velocity = direction * speed
        separation = relative.length()
        raw_angle = angle_deg(direction, relative)
        closure = closure_bps(position, velocity, target.position, target.velocity_bps)
        attack_sector = raw_angle <= 45.0 and 24.0 <= separation <= 170.0
        narrow_sector = (raw_angle <= 12.0 and 24.0 <= separation <= 125.0
                         and -6.0 <= closure <= 28.0)
        if attack_sector and first_attack is None:
            first_attack = offset
        if narrow_sector and first_narrow is None:
            first_narrow = offset
        attack_ticks += int(attack_sector)
        narrow_ticks += int(narrow_sector)
        min_separation = min(min_separation, separation)
        min_raw_angle = min(min_raw_angle, raw_angle)
        final_separation = separation
        final_angle = raw_angle
        final_closure = closure
        final_altitude_advantage = position.y - target.position.y
        if offset < duration_ticks:
            position = position + velocity * (1.0 / TICKS_PER_SECOND)

    unsafe_penalty = max(0.0, min_safe_separation - min_separation) * 1000.0
    first_narrow_penalty = float(first_narrow if first_narrow is not None else duration_ticks * 3)
    score = (narrow_ticks * 100.0 + attack_ticks * 2.0
             - first_narrow_penalty * 0.2
             - unsafe_penalty
             - abs(final_closure) * 0.4
             - final_angle * 0.15)
    return Result(candidate, score, first_attack, first_narrow, attack_ticks, narrow_ticks,
                  min_separation, min_raw_angle, final_separation, final_angle,
                  final_closure, final_altitude_advantage)


def actual_baseline(own_frames: dict[int, Frame], target_frames: dict[int, Frame],
                    start_tick: int, duration_ticks: int) -> dict[str, object]:
    min_separation = math.inf
    min_angle = 180.0
    attack_ticks = 0
    narrow_ticks = 0
    final: tuple[float, float, float] | None = None
    for offset in range(duration_ticks + 1):
        tick = start_tick + offset
        own = frame_at(own_frames, tick)
        target = frame_at(target_frames, tick)
        relative = target.position - own.position
        separation = relative.length()
        raw_angle = angle_deg(own.forward, relative)
        closure = closure_bps(own.position, own.velocity_bps,
                              target.position, target.velocity_bps)
        min_separation = min(min_separation, separation)
        min_angle = min(min_angle, raw_angle)
        attack_ticks += int(raw_angle <= 45.0 and 24.0 <= separation <= 170.0)
        narrow_ticks += int(raw_angle <= 12.0 and 24.0 <= separation <= 125.0
                            and -6.0 <= closure <= 28.0)
        final = (separation, raw_angle, closure)
    assert final is not None
    return {
        "min_separation": round(min_separation, 3),
        "min_raw_angle_deg": round(min_angle, 3),
        "attack_sector_ticks": attack_ticks,
        "narrow_sector_ticks": narrow_ticks,
        "final_separation": round(final[0], 3),
        "final_raw_angle_deg": round(final[1], 3),
        "final_closure_bps": round(final[2], 3),
    }


def result_dict(result: Result) -> dict[str, object]:
    candidate = result.candidate
    return {
        "candidate": {
            "lag_ticks": candidate.lag_ticks,
            "lag_yaw_fraction": candidate.lag_yaw_fraction,
            "climb_angle_deg": candidate.climb_angle_deg,
            "lead_seconds": candidate.lead_seconds,
            "speed_floor_bps": candidate.speed_floor_bps,
            "target_speed_offset_bps": candidate.target_speed_offset_bps,
        },
        "score": round(result.score, 3),
        "first_attack_tick_offset": result.first_attack_tick,
        "first_narrow_tick_offset": result.first_narrow_tick,
        "attack_sector_ticks": result.attack_sector_ticks,
        "narrow_sector_ticks": result.narrow_sector_ticks,
        "min_separation": round(result.min_separation, 3),
        "min_raw_angle_deg": round(result.min_raw_angle_deg, 3),
        "final_separation": round(result.final_separation, 3),
        "final_raw_angle_deg": round(result.final_raw_angle_deg, 3),
        "final_closure_bps": round(result.final_closure_bps, 3),
        "final_altitude_advantage": round(result.final_altitude_advantage, 3),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--own-log", required=True, type=Path)
    parser.add_argument("--target-log", required=True, type=Path)
    parser.add_argument("--start-tick", type=int)
    parser.add_argument("--duration-ticks", type=int, default=320)
    parser.add_argument("--lookback-ticks", type=int, default=80)
    parser.add_argument("--min-safe-separation", type=float, default=8.0)
    parser.add_argument("--top", type=int, default=12)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.duration_ticks <= 0 or args.top <= 0:
        parser.error("--duration-ticks and --top must be positive")

    own = read_telemetry(args.own_log)
    target = read_telemetry(args.target_log)
    start_tick = choose_start_tick(own, target, args.start_tick)
    if start_tick + args.duration_ticks > min(max(own.frames), max(target.frames)):
        parser.error("both telemetry logs must cover the requested duration")
    start = own.frames[start_tick]
    target_start = frame_at(target.frames, start_tick)
    yaw_cap, pitch_cap = estimate_rate_caps(own.frames, start_tick, args.lookback_ticks)

    results = [simulate(start, target.frames, candidate, args.duration_ticks,
                        yaw_cap, pitch_cap, args.min_safe_separation)
               for candidate in candidate_grid()]
    results.sort(key=lambda item: item.score, reverse=True)
    initial_relative = target_start.position - start.position
    payload = {
        "model": "recorded-target capped-rate oblique-lag-yoyo v1",
        "limitations": [
            "Target behavior is replayed and does not react to the counterfactual path.",
            "Aircraft response is a capped-rate point mass, not Immersive Aircraft physics.",
            "A candidate must still pass the real weapon, collision, terrain, and GameTest gates.",
        ],
        "start_tick": start_tick,
        "duration_ticks": args.duration_ticks,
        "initial_geometry": {
            "distance": round(initial_relative.length(), 3),
            "raw_angle_deg": round(angle_deg(start.forward, initial_relative), 3),
            "closure_bps": round(closure_bps(start.position, start.velocity_bps,
                                              target_start.position,
                                              target_start.velocity_bps), 3),
            "own_speed_bps": round(start.speed_bps, 3),
            "target_speed_bps": round(target_start.speed_bps, 3),
        },
        "estimated_rate_caps": {
            "yaw_deg_s": round(yaw_cap, 3),
            "pitch_deg_s": round(pitch_cap, 3),
        },
        "actual_recorded_baseline": actual_baseline(
            own.frames, target.frames, start_tick, args.duration_ticks),
        "evaluated_candidates": len(results),
        "top_candidates": [result_dict(result) for result in results[:args.top]],
    }
    rendered = json.dumps(payload, indent=2)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
