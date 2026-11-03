"""Common complete mission evidence for independent verifier regression fixtures."""


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
