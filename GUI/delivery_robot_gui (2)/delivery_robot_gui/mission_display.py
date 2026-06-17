STATION_FROM_TARGET = {
    "HOME": "Home",
    "WP1": "Station A",
    "WP2": "Station B",
    "WP3": "Station C",
}

NEXT_STATION = {
    "Station A": "Station B",
    "Station B": "Station C",
    "Station C": "Home",
}


def station_name_from_target(target):
    return STATION_FROM_TARGET.get(str(target or "").upper(), str(target or "") or "-")


def destination_text(mission):
    state = str(mission.get("state", "") or "")
    station = str(mission.get("current_station", "") or "")
    target = str(mission.get("current_target", "") or "")

    if state in ("IDLE", "REQUESTS_RECEIVED"):
        return "Home"
    if target.upper() == "HOME" or state == "RETURNING_HOME":
        return "Home"
    if station and state.startswith("NAVIGATING_TO_"):
        return f"{station} -> {station_name_from_target(target)}"
    if station:
        return station
    return station_name_from_target(target)


def order_is_active_for_user(mission, user_name):
    if not mission or not user_name:
        return False
    active_user = str(mission.get("active_user", "") or "")
    if active_user and active_user == user_name:
        return True
    return bool(mission.get("mission_active")) and str(
        mission.get("state", "")
    ) not in ("IDLE", "COMPLETE", "ABORTED", "FAULTED")
