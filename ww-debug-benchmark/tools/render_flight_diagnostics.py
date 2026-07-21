#!/usr/bin/env python3
"""Render dependency-free HTML/SVG diagnostics from autonomous-flight JSONL telemetry."""

from __future__ import annotations

import argparse
import html
import json
import math
from pathlib import Path
from typing import Any, Iterable


def finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def latest(paths: Iterable[Path]) -> Path | None:
    candidates = [path for path in paths if path.is_file()]
    return max(candidates, key=lambda path: path.stat().st_mtime) if candidates else None


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                rows.append(value)
    return rows


def sample(rows: list[dict[str, Any]], maximum: int = 1800) -> list[dict[str, Any]]:
    if len(rows) <= maximum:
        return rows
    step = max(1, math.ceil(len(rows) / maximum))
    sampled = rows[::step]
    if sampled[-1] is not rows[-1]:
        sampled.append(rows[-1])
    return sampled


def bounds(values: list[float], padding: float = 0.08) -> tuple[float, float]:
    if not values:
        return 0.0, 1.0
    low = min(values)
    high = max(values)
    if abs(high - low) < 1.0e-9:
        return low - 0.5, high + 0.5
    margin = (high - low) * padding
    return low - margin, high + margin


def scale(value: float, low: float, high: float, target_low: float, target_high: float) -> float:
    if abs(high - low) < 1.0e-9:
        return (target_low + target_high) * 0.5
    ratio = (value - low) / (high - low)
    return target_low + ratio * (target_high - target_low)


def polyline(points: list[tuple[float, float]], css_class: str) -> str:
    encoded = " ".join(f"{x:.2f},{y:.2f}" for x, y in points)
    return f'<polyline class="{css_class}" points="{encoded}" />' if points else ""


def top_view(frames: list[dict[str, Any]]) -> str:
    positions = []
    for frame in sample(frames):
        position = frame.get("position") or {}
        x = finite(position.get("x"))
        z = finite(position.get("z"))
        if x is not None and z is not None:
            positions.append((x, z))
    xs = [x for x, _ in positions]
    zs = [z for _, z in positions]
    x0, x1 = bounds(xs)
    z0, z1 = bounds(zs)
    points = [
        (scale(x, x0, x1, 35, 865), scale(z, z0, z1, 465, 35))
        for x, z in positions
    ]
    start = points[0] if points else (0, 0)
    end = points[-1] if points else (0, 0)
    return f"""
    <svg viewBox="0 0 900 500" role="img" aria-label="Top-down flight path">
      <rect class="plot-bg" x="0" y="0" width="900" height="500" />
      <line class="axis" x1="35" y1="465" x2="865" y2="465" />
      <line class="axis" x1="35" y1="35" x2="35" y2="465" />
      {polyline(points, 'path-line')}
      <circle class="start" cx="{start[0]:.2f}" cy="{start[1]:.2f}" r="6" />
      <circle class="finish" cx="{end[0]:.2f}" cy="{end[1]:.2f}" r="6" />
      <text x="45" y="55">X {x0:.1f} … {x1:.1f}</text>
      <text x="45" y="78">Z {z0:.1f} … {z1:.1f}</text>
    </svg>
    """


def side_view(frames: list[dict[str, Any]]) -> str:
    points_raw: list[tuple[float, float]] = []
    for frame in sample(frames):
        position = frame.get("position") or {}
        home = frame.get("home_position") or {}
        runway = frame.get("runway_forward") or {}
        px, py, pz = finite(position.get("x")), finite(position.get("y")), finite(position.get("z"))
        hx, hz = finite(home.get("x")), finite(home.get("z"))
        fx, fz = finite(runway.get("x")), finite(runway.get("z"))
        if None not in (px, py, pz, hx, hz, fx, fz):
            longitudinal = (px - hx) * fx + (pz - hz) * fz
            points_raw.append((longitudinal, py))
    xs = [x for x, _ in points_raw]
    ys = [y for _, y in points_raw]
    x0, x1 = bounds(xs)
    y0, y1 = bounds(ys)
    points = [
        (scale(x, x0, x1, 35, 865), scale(y, y0, y1, 465, 35))
        for x, y in points_raw
    ]
    return f"""
    <svg viewBox="0 0 900 500" role="img" aria-label="Side flight profile">
      <rect class="plot-bg" x="0" y="0" width="900" height="500" />
      <line class="axis" x1="35" y1="465" x2="865" y2="465" />
      <line class="axis" x1="35" y1="35" x2="35" y2="465" />
      {polyline(points, 'altitude-line')}
      <text x="45" y="55">Runway axis {x0:.1f} … {x1:.1f} blocks</text>
      <text x="45" y="78">Y {y0:.1f} … {y1:.1f}</text>
    </svg>
    """


def attitude_view(frames: list[dict[str, Any]]) -> tuple[str, bool]:
    selected = sample(frames)
    series: dict[str, list[tuple[float, float]]] = {"yaw": [], "pitch": [], "roll": []}
    ticks: list[float] = []
    for frame in selected:
        tick = finite(frame.get("mission_ticks"))
        if tick is None:
            continue
        ticks.append(tick)
        for name, key in (("yaw", "yaw_deg"), ("pitch", "pitch_deg"), ("roll", "roll_deg")):
            value = finite(frame.get(key))
            if value is not None:
                series[name].append((tick, value))
    tick0, tick1 = bounds(ticks, 0.0)
    angle_values = [value for values in series.values() for _, value in values]
    angle0, angle1 = bounds(angle_values)

    def converted(name: str) -> list[tuple[float, float]]:
        return [
            (scale(tick, tick0, tick1, 35, 865), scale(value, angle0, angle1, 465, 35))
            for tick, value in series[name]
        ]

    roll_available = bool(series["roll"])
    svg = f"""
    <svg viewBox="0 0 900 500" role="img" aria-label="Aircraft attitude">
      <rect class="plot-bg" x="0" y="0" width="900" height="500" />
      <line class="axis" x1="35" y1="465" x2="865" y2="465" />
      <line class="axis" x1="35" y1="35" x2="35" y2="465" />
      {polyline(converted('yaw'), 'yaw-line')}
      {polyline(converted('pitch'), 'pitch-line')}
      {polyline(converted('roll'), 'roll-line')}
      <text x="45" y="55">Angles {angle0:.1f}° … {angle1:.1f}°</text>
      <text x="45" y="78">Mission ticks {tick0:.0f} … {tick1:.0f}</text>
      <text class="legend yaw-text" x="650" y="55">Yaw</text>
      <text class="legend pitch-text" x="715" y="55">Pitch</text>
      <text class="legend roll-text" x="785" y="55">Roll</text>
    </svg>
    """
    return svg, roll_available


def metric(frames: list[dict[str, Any]], key: str, function, default: str = "n/a") -> str:
    values = [value for frame in frames if (value := finite(frame.get(key))) is not None]
    return f"{function(values):.3f}" if values else default


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scenario", default="unknown")
    args = parser.parse_args()

    log_path = latest(args.root.rglob("aircraft/*.jsonl"))
    summary_path = latest(args.root.rglob("validation-summary-*.json"))
    rows = read_jsonl(log_path) if log_path else []
    frames = [row for row in rows if row.get("event") == "frame"]
    transitions = [row for row in rows if row.get("event") == "phase_transition"]
    summary: dict[str, Any] = {}
    if summary_path:
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            summary = {}

    attitude_svg, roll_available = attitude_view(frames)
    transition_rows = "".join(
        "<tr><td>{}</td><td>{}</td><td>{}</td></tr>".format(
            html.escape(str(row.get("server_tick", ""))),
            html.escape(str(row.get("phase", ""))),
            html.escape(str(row.get("reason", ""))),
        )
        for row in transitions
    ) or '<tr><td colspan="3">No phase transitions recorded.</td></tr>'

    result_rows = summary.get("results") or []
    result_text = html.escape(json.dumps(result_rows, ensure_ascii=False, indent=2))
    aircraft_name = frames[0].get("aircraft_name", "unknown") if frames else "unknown"
    phase = frames[-1].get("phase", "unknown") if frames else "unknown"
    roll_note = "Roll telemetry available" if roll_available else "Roll telemetry unavailable in this run"

    document = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Warfare Wings flight diagnostics</title>
<style>
:root {{ color-scheme: light dark; font-family: system-ui, sans-serif; }}
body {{ margin: 0 auto; max-width: 1200px; padding: 24px; line-height: 1.45; }}
h1, h2 {{ margin-bottom: .4rem; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 12px; }}
.card, .chart {{ border: 1px solid #7776; border-radius: 10px; padding: 14px; margin: 12px 0; }}
.card strong {{ display: block; font-size: 1.25rem; }}
svg {{ width: 100%; height: auto; }}
.plot-bg {{ fill: transparent; }}
.axis {{ stroke: currentColor; stroke-width: 1; opacity: .35; }}
.path-line, .altitude-line, .yaw-line, .pitch-line, .roll-line {{ fill: none; stroke-width: 2.2; }}
.path-line {{ stroke: #2c7; }} .altitude-line {{ stroke: #48e; }}
.yaw-line {{ stroke: #e55; }} .pitch-line {{ stroke: #4a8; }} .roll-line {{ stroke: #85e; }}
.start {{ fill: #2c7; }} .finish {{ fill: #e55; }}
.legend {{ font-weight: 700; }} .yaw-text {{ fill: #e55; }} .pitch-text {{ fill: #4a8; }} .roll-text {{ fill: #85e; }}
table {{ width: 100%; border-collapse: collapse; }} th, td {{ border-bottom: 1px solid #7775; padding: 7px; text-align: left; }}
pre {{ overflow: auto; padding: 12px; border-radius: 8px; background: #7772; }}
</style>
</head>
<body>
<h1>Warfare Wings headless flight diagnostics</h1>
<p>Scenario: <strong>{html.escape(args.scenario)}</strong> · Aircraft: <strong>{html.escape(str(aircraft_name))}</strong></p>
<div class="grid">
  <div class="card">Final phase<strong>{html.escape(str(phase))}</strong></div>
  <div class="card">Frames<strong>{len(frames)}</strong></div>
  <div class="card">Maximum speed<strong>{metric(frames, 'speed_bps', max)} bps</strong></div>
  <div class="card">Minimum AGL<strong>{metric(frames, 'altitude_above_ground', min)} blocks</strong></div>
  <div class="card">Maximum |roll|<strong>{metric(frames, 'roll_deg', lambda values: max(abs(v) for v in values))}°</strong></div>
  <div class="card">Attitude status<strong>{html.escape(roll_note)}</strong></div>
</div>
<section class="chart"><h2>Top-down path</h2>{top_view(frames)}</section>
<section class="chart"><h2>Side profile</h2>{side_view(frames)}</section>
<section class="chart"><h2>Yaw, pitch and roll</h2>{attitude_svg}</section>
<section class="card">
<h2>Phase transitions</h2>
<table><thead><tr><th>Server tick</th><th>Phase</th><th>Reason</th></tr></thead><tbody>{transition_rows}</tbody></table>
</section>
<section class="card"><h2>Validation summary</h2><pre>{result_text}</pre></section>
<p>Source log: {html.escape(str(log_path) if log_path else 'none')}</p>
</body></html>"""

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(document, encoding="utf-8")
    print(f"wrote visual flight diagnostics to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
