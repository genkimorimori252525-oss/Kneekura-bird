"""Common complete mission evidence for independent verifier regression fixtures."""

PILOT_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
PILOT_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


def fill_interior_frames(rows, start, end):
    """Build a complete baseline once; never repair mutated test evidence in verify()."""
    result = list(rows)
    template = next(row for row in result if row.get("event") == "frame"
                    and start < row.get("server_tick", -1) < end)
    observed = {row["server_tick"] for row in result if row.get("event") == "frame"
                and type(row.get("server_tick")) is int}
    for when in range(start + 1, end):
        if when in observed:
            continue
        frame = dict(template, server_tick=when)
        index = next((i for i, row in enumerate(result)
                      if type(row.get("server_tick")) is int and row["server_tick"] > when), len(result))
        result.insert(index, frame)
    return result


def combat_identity(rows, primary):
    pilot, target = (PILOT_A, PILOT_B) if primary else (PILOT_B, PILOT_A)
    result = []
    for source in rows:
        row = dict(source)
        row.setdefault("pilot_uuid", pilot)
        row.setdefault("pilot_entity_id", "minecraft:villager")
        event = row.get("event")
        if "server_tick" not in row and event in ("combat_target_acquired", "air_combat_action_transition", "weapon_fire"):
            row["server_tick"] = {"combat_target_acquired": 12, "air_combat_action_transition": 13,
                                  "weapon_fire": 14}[event]
        if event == "mutual_dogfight_validation_started":
            row["reason"] = row.get("reason", "") + f":primary_pilot_uuid={PILOT_A}:opponent_pilot_uuid={PILOT_B}"
        elif event == "combat_target_acquired":
            row["reason"] = row.get("reason", "") + f":uuid={target}"
        elif event == "weapon_fire":
            row["reason"] = row.get("reason", "") + f":target_uuid={target}"
        result.append(row)
    return result


def complete_summary(uid):
    return {"state": "complete", "total": 1, "completed": 1, "results": [{
        "aircraft_uuid": uid, "entity_id": "warfare_wings:a6m", "passed": True,
        "reason": "completed_full_mission", "final_phase": "PARKED",
        "last_transition_reason": "complete_stop_stable_for_40_ticks",
    }]}


def parked_cleanup(rows, uid):
    name = rows[0]["aircraft_name"]
    common = {"aircraft_name": name, "aircraft_uuid": uid, "server_tick": 1000, "phase": "PARKED"}
    return list(rows) + [
        dict(common, event="phase_transition", reason="BRAKE->PARKED:complete_stop_stable_for_40_ticks"),
        dict(common, event="frame", reason="", on_ground=True, horizontal_speed_bps=0.0, speed_bps=0.0),
        dict(common, event="session_end", reason="validation_aircraft_cleanup"),
    ]
