"""
Warfare Wings 航空機データ解析 + 理論性能算出スクリプト

24機のベースJSONを解析し、以下を出力:
- aircraft_stats.csv: 全機体の静的スタッツ + 理論性能一覧
- aircraft_stats.json: AI用の構造化データ
"""

import json
import os
import csv
import math
import glob

# ============================================================
# 設定
# ============================================================

AIRCRAFT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "warfare_wings", "aircraft")
OUTPUT_DIR = os.path.dirname(__file__)

# Immersive Aircraft の物理定数（ソースコードから抽出）
GRAVITY = -0.04          # InventoryVehicleEntity: gravity per tick
HORIZONTAL_DECAY = 0.97  # InventoryVehicleEntity: horizontal velocity decay
VERTICAL_DECAY = 0.97    # InventoryVehicleEntity: vertical velocity decay
DEFAULT_FRICTION = 0.015 # VehicleStat.FRICTION default (driftDrag in JSON)
TICKS_PER_SECOND = 20

# scheme変種を除外するためのベース機体リスト
BASE_AIRCRAFT = [
    "a6m", "b17", "b29", "bf109", "d4y", "f4u", "f6f", "fw190",
    "g10n1", "g10n2", "g4m", "he111", "il2", "ju87", "ki61", "ki84",
    "mc202", "mig3", "p40e", "p47n", "p51d", "sbd", "spitfire", "yak3"
]

# 表示名マッピング
DISPLAY_NAMES = {
    "a6m": "A6M Zero", "b17": "B-17 Flying Fortress", "b29": "B-29 Superfortress",
    "bf109": "Bf 109", "d4y": "D4Y Suisei", "f4u": "F4U Corsair",
    "f6f": "F6F Hellcat", "fw190": "Fw 190", "g10n1": "G10N1 Fugaku",
    "g10n2": "G10N2 Fugaku", "g4m": "G4M Betty", "he111": "He 111",
    "il2": "IL-2 Sturmovik", "ju87": "Ju 87 Stuka", "ki61": "Ki-61 Hien",
    "ki84": "Ki-84 Hayate", "mc202": "MC.202 Folgore", "mig3": "MiG-3",
    "p40e": "P-40E Warhawk", "p47n": "P-47N Thunderbolt", "p51d": "P-51D Mustang",
    "sbd": "SBD Dauntless", "spitfire": "Spitfire", "yak3": "Yak-3"
}


# ============================================================
# JSON解析
# ============================================================

def load_aircraft_json(aircraft_id):
    """航空機JSONファイルを読み込む"""
    filepath = os.path.join(AIRCRAFT_DIR, f"{aircraft_id}.json")
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_static_stats(aircraft_id, data):
    """JSONから静的スタッツを抽出"""
    props = data["properties"]
    ai = data.get("ai", {})
    weapon_mounts = data.get("weaponMounts", [])
    bboxes = data.get("boundingBoxes", [])
    passengers = data.get("passengerPositions", [])

    # 武装マウント集計
    total_front = 0
    total_drop = 0
    total_rotating = 0
    for mount in weapon_mounts:
        front_positions = mount.get("FRONT", [])
        drop_positions = mount.get("DROP", [])
        rotating_positions = mount.get("ROTATING", [])
        # (0,0,0)のダミーポジションを除外
        total_front += sum(1 for p in front_positions if not (p["x"] == 0 and p["y"] == 0 and p["z"] == 0))
        total_drop += sum(1 for p in drop_positions if not (p["x"] == 0 and p["y"] == 0 and p["z"] == 0))
        total_rotating += sum(1 for p in rotating_positions if not (p["x"] == 0 and p["y"] == 0 and p["z"] == 0))

    # サイズ計算（boundingBoxesから）
    if bboxes:
        all_z = []
        all_x = []
        for bb in bboxes:
            z = bb["z"]
            x = bb["x"]
            w = bb["width"]
            all_z.append(z)
            all_x.append(x - w / 2)
            all_x.append(x + w / 2)
        length = max(all_z) - min(all_z) if all_z else 0
        wingspan = max(all_x) - min(all_x) if all_x else 0
    else:
        length = 0
        wingspan = 0

    # 乗員数
    crew_count = sum(len(pos_set) for pos_set in passengers)

    return {
        "id": aircraft_id,
        "displayName": DISPLAY_NAMES.get(aircraft_id, aircraft_id.upper()),
        # AI分類
        "role": ai.get("role", "unknown"),
        "faction": ai.get("faction", "unknown"),
        "doctrine": ai.get("doctrine", "unknown"),
        # 飛行特性
        "engineSpeed": props.get("engineSpeed", 0),
        "yawSpeed": props.get("yawSpeed", 0),
        "pitchSpeed": props.get("pitchSpeed", 0),
        "rollFactor": props.get("rollFactor", 0),
        "mass": props.get("mass", 0),
        "lift": props.get("lift", 0),
        "glideFactor": props.get("glideFactor", 0),
        "driftDrag": props.get("driftDrag", 0),
        "wind": props.get("wind", 0),
        "groundPitch": props.get("groundPitch", 0),
        "pushSpeed": props.get("pushSpeed", 0),
        # 基本性能
        "fuel": props.get("fuel", 0),
        "durability": props.get("durability", 0),
        # 武装
        "weaponMounts": len(weapon_mounts),
        "frontGuns": total_front,
        "dropPoints": total_drop,
        "rotatingGuns": total_rotating,
        # サイズ
        "length": round(length, 2),
        "wingspan": round(wingspan, 2),
        "crew": crew_count,
    }


# ============================================================
# 理論性能算出（Immersive Aircraft物理エンジンのシミュレーション）
# ============================================================

def calc_max_speed(engine_speed, drift_drag):
    """
    最高速度の算出（水平定常飛行）

    推力: thrust = pow(enginePower, 2) * ENGINE_SPEED  (enginePower=1.0)
    毎tick: velocity = velocity * (1 - friction) * HORIZONTAL_DECAY + thrust
    平衡時: velocity = thrust / (1 - (1-friction)*HORIZONTAL_DECAY)

    ただしfrictionはdriftDragではなくデフォルト値を使う場合もある。
    ここではdriftDragをfriction的に扱うシミュレーションで算出。
    """
    velocity = 0.0
    engine_power = 1.0
    thrust = (engine_power ** 2) * engine_speed

    for tick in range(2000):  # 100秒分
        velocity = velocity * (1 - drift_drag) * HORIZONTAL_DECAY + thrust
        # 収束チェック
        if tick > 100 and abs(velocity - (velocity * (1 - drift_drag) * HORIZONTAL_DECAY + thrust)) / max(velocity, 0.001) < 0.0001:
            break

    return round(velocity, 5)


def calc_max_speed_simulation(engine_speed, drift_drag):
    """
    tick-by-tickシミュレーションで最高速度と到達時間を算出
    """
    velocity = 0.0
    engine_power = 0.0
    engine_target = 1.0
    reaction_steps = 20  # デフォルトのengine reaction speed

    max_speed = 0.0
    time_to_90pct = None
    speed_history = []

    for tick in range(2000):
        # エンジンパワーの補間（スムーズに上昇）
        engine_power += (engine_target - engine_power) / reaction_steps
        engine_power = min(engine_power, 1.0)

        # 推力
        thrust = (engine_power ** 2) * engine_speed

        # 速度更新
        velocity = velocity * (1 - drift_drag) * HORIZONTAL_DECAY + thrust

        speed_history.append(velocity)

        if velocity > max_speed:
            max_speed = velocity

        # 90%到達時間
        if time_to_90pct is None and velocity >= max_speed * 0.9 and tick > 50:
            # まだ収束してないかもしれないので、仮の90%チェック
            pass

    # 最終速度の90%に初めて達したtickを探す
    final_speed = speed_history[-1]
    threshold_90 = final_speed * 0.9
    time_to_90pct = next((t for t, s in enumerate(speed_history) if s >= threshold_90), None)

    return {
        "max_speed_bpt": round(final_speed, 5),         # blocks/tick
        "max_speed_bps": round(final_speed * 20, 2),    # blocks/second
        "max_speed_kmh": round(final_speed * 20 * 3.6, 1),  # 仮のkm/h換算（1block=1m想定）
        "time_to_90pct_ticks": time_to_90pct,
        "time_to_90pct_seconds": round(time_to_90pct / 20, 1) if time_to_90pct else None,
    }


def calc_turn_rate(yaw_speed):
    """旋回速度（度/秒）"""
    return round(yaw_speed * TICKS_PER_SECOND, 1)


def calc_turn_radius(speed_bpt, yaw_speed_deg_per_tick):
    """
    旋回半径（ブロック）
    radius = speed / angular_velocity(rad/tick)
    """
    if yaw_speed_deg_per_tick == 0:
        return float('inf')
    omega_rad = math.radians(yaw_speed_deg_per_tick)
    if omega_rad == 0:
        return float('inf')
    radius = speed_bpt / omega_rad
    return round(radius, 2)


def calc_stall_speed():
    """
    失速速度の算出
    gravity = max(0, 1 - speed * 1.5) * (-0.04)
    speed * 1.5 >= 1.0 で重力ゼロ → stall_speed = 1/1.5 ≈ 0.667 blocks/tick
    これ以下では重力が発生し始める
    """
    # 全機共通（速度依存の重力式は同一）
    return round(1.0 / 1.5, 4)


def calc_energy_retention_90deg(engine_speed, drift_drag, yaw_speed, lift):
    """
    90度旋回後のエネルギー保持率をシミュレーション

    仮定: 最高速度で旋回開始、エンジン全開維持
    旋回中はlift値により速度ベクトルが機首方向に補正されるが、
    同時にdragで速度が失われる
    """
    # まず最高速度を算���
    max_speed = calc_max_speed(engine_speed, drift_drag)

    # 90度旋回に必要なtick数
    if yaw_speed == 0:
        return 0.0
    ticks_for_90deg = 90.0 / yaw_speed

    # 旋回中の速度減衰シミュレーション
    speed = max_speed
    engine_power = 1.0
    thrust = (engine_power ** 2) * engine_speed

    for _ in range(int(ticks_for_90deg)):
        # 旋回中は推力の一部が方向転換に消費される
        # liftが高い→方向転換での速度損失が少ない
        effective_thrust = thrust * (0.5 + lift * 2)  # lift効果の近似
        speed = speed * (1 - drift_drag) * HORIZONTAL_DECAY + effective_thrust
        speed = max(speed, 0)

    retention = speed / max_speed if max_speed > 0 else 0
    return round(retention, 3)


def calc_wind_sensitivity(wind, mass):
    """風の影響度（wind / mass比率）"""
    if mass == 0:
        return 0
    return round(wind / mass, 6)


def calculate_performance(stats):
    """全理論性能を算出"""
    speed_data = calc_max_speed_simulation(stats["engineSpeed"], stats["driftDrag"])
    max_speed_bpt = speed_data["max_speed_bpt"]
    stall_speed = calc_stall_speed()

    return {
        # 速度
        "maxSpeed_bpt": speed_data["max_speed_bpt"],
        "maxSpeed_bps": speed_data["max_speed_bps"],
        "maxSpeed_kmh": speed_data["max_speed_kmh"],
        "accelTo90pct_ticks": speed_data["time_to_90pct_ticks"],
        "accelTo90pct_sec": speed_data["time_to_90pct_seconds"],
        # 旋回
        "turnRate_dps": calc_turn_rate(stats["yawSpeed"]),
        "turnRadiusAtMax_blocks": calc_turn_radius(max_speed_bpt, stats["yawSpeed"]),
        "turnRadiusAt75pct_blocks": calc_turn_radius(max_speed_bpt * 0.75, stats["yawSpeed"]),
        "turnRadiusAt50pct_blocks": calc_turn_radius(max_speed_bpt * 0.5, stats["yawSpeed"]),
        # 失速
        "stallSpeed_bpt": stall_speed,
        "stallSpeed_bps": round(stall_speed * 20, 2),
        # エネルギー
        "energyRetention90deg": calc_energy_retention_90deg(
            stats["engineSpeed"], stats["driftDrag"], stats["yawSpeed"], stats["lift"]
        ),
        # 風感度
        "windSensitivity": calc_wind_sensitivity(stats["wind"], stats["mass"]),
        # ピッチ速度
        "pitchRate_dps": round(stats["pitchSpeed"] * 20, 1),
    }


# ============================================================
# 出力
# ============================================================

def output_csv(all_data, filepath):
    """CSV一覧表を出力"""
    if not all_data:
        return

    # カラム定義
    columns = [
        # 基本情報
        "id", "displayName", "role", "faction", "doctrine",
        # 飛行特性
        "engineSpeed", "yawSpeed", "pitchSpeed", "rollFactor",
        "mass", "lift", "glideFactor", "driftDrag", "wind",
        # 基本性能
        "fuel", "durability",
        # 武装
        "weaponMounts", "frontGuns", "dropPoints", "rotatingGuns",
        # サイズ
        "length", "wingspan", "crew",
        # 理論性能
        "maxSpeed_bpt", "maxSpeed_bps", "maxSpeed_kmh",
        "accelTo90pct_ticks", "accelTo90pct_sec",
        "turnRate_dps",
        "turnRadiusAtMax_blocks", "turnRadiusAt75pct_blocks", "turnRadiusAt50pct_blocks",
        "stallSpeed_bpt", "stallSpeed_bps",
        "energyRetention90deg", "windSensitivity", "pitchRate_dps",
    ]

    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for entry in all_data:
            writer.writerow(entry)

    print(f"CSV saved: {filepath}")


def output_json(all_data, filepath):
    """JSON出力（AI用構造化データ）"""
    output = {}
    for entry in all_data:
        aircraft_id = entry["id"]
        output[aircraft_id] = {
            "id": f"warfare_wings:{aircraft_id}",
            "displayName": entry["displayName"],
            "ai": {
                "role": entry["role"],
                "faction": entry["faction"],
                "doctrine": entry["doctrine"],
            },
            "rawProperties": {
                k: entry[k] for k in [
                    "engineSpeed", "yawSpeed", "pitchSpeed", "rollFactor",
                    "mass", "lift", "glideFactor", "driftDrag", "wind",
                    "groundPitch", "pushSpeed", "fuel", "durability"
                ]
            },
            "weaponry": {
                "mountCount": entry["weaponMounts"],
                "frontGuns": entry["frontGuns"],
                "dropPoints": entry["dropPoints"],
                "rotatingGuns": entry["rotatingGuns"],
            },
            "dimensions": {
                "length_blocks": entry["length"],
                "wingspan_blocks": entry["wingspan"],
                "crew": entry["crew"],
            },
            "theoreticalPerformance": {
                k: entry[k] for k in [
                    "maxSpeed_bpt", "maxSpeed_bps", "maxSpeed_kmh",
                    "accelTo90pct_ticks", "accelTo90pct_sec",
                    "turnRate_dps",
                    "turnRadiusAtMax_blocks", "turnRadiusAt75pct_blocks", "turnRadiusAt50pct_blocks",
                    "stallSpeed_bpt", "stallSpeed_bps",
                    "energyRetention90deg", "windSensitivity", "pitchRate_dps",
                ] if k in entry
            },
        }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"JSON saved: {filepath}")


# ============================================================
# メイン
# ============================================================

def main():
    print("=" * 70)
    print("Warfare Wings 航空機データ解析")
    print("=" * 70)

    all_data = []

    for aircraft_id in sorted(BASE_AIRCRAFT):
        try:
            raw_data = load_aircraft_json(aircraft_id)
            stats = extract_static_stats(aircraft_id, raw_data)
            performance = calculate_performance(stats)

            # statsとperformanceをマージ
            combined = {**stats, **performance}
            all_data.append(combined)

            print(f"  {stats['displayName']:30s} | {stats['role']:15s} | "
                  f"maxSpeed={performance['maxSpeed_bps']:6.2f} b/s | "
                  f"turnRate={performance['turnRate_dps']:5.1f} d/s | "
                  f"turnR@max={performance['turnRadiusAtMax_blocks']:6.1f} b")

        except FileNotFoundError:
            print(f"  [SKIP] {aircraft_id}.json not found")
        except Exception as e:
            print(f"  [ERROR] {aircraft_id}: {e}")

    print()
    print(f"Parsed {len(all_data)} aircraft")
    print()

    # ロール別サマリー
    roles = {}
    for d in all_data:
        role = d["role"]
        if role not in roles:
            roles[role] = []
        roles[role].append(d)

    for role, aircraft_list in sorted(roles.items()):
        print(f"--- {role.upper()} ({len(aircraft_list)}機) ---")
        # 速度順にソート
        sorted_list = sorted(aircraft_list, key=lambda x: x["maxSpeed_bps"], reverse=True)
        for a in sorted_list:
            print(f"  {a['displayName']:30s} | speed={a['maxSpeed_bps']:5.2f} | "
                  f"yaw={a['yawSpeed']:4.1f} | mass={a['mass']:5.1f} | "
                  f"doctrine={a['doctrine']}")
        print()

    # 出力
    csv_path = os.path.join(OUTPUT_DIR, "aircraft_stats.csv")
    json_path = os.path.join(OUTPUT_DIR, "aircraft_stats.json")

    output_csv(all_data, csv_path)
    output_json(all_data, json_path)

    print()
    print("Done!")


if __name__ == "__main__":
    main()
