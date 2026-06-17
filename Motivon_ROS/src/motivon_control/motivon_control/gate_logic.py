from dataclasses import dataclass


@dataclass
class GateDecision:
    source: str
    allow_motion: bool
    reason: str


def normalize_mode(value: str) -> str:
    mode = str(value or "AUTO").strip().upper()
    if mode in ("AUTONOMOUS", "AUTO"):
        return "AUTO"
    if mode == "MANUAL":
        return "MANUAL"
    if mode in ("DISABLED", "STOPPED", "IDLE"):
        return "DISABLED"
    if mode in ("ESTOP", "E_STOP", "SOFTWARE_STOP"):
        return "ESTOP"
    return "DISABLED"


def choose_gate_state(
    *,
    mode: str,
    safety_stop: bool,
    obstacle_blocks_auto: bool,
    navigation_fresh: bool,
    manual_fresh: bool,
) -> GateDecision:
    normalized = normalize_mode(mode)
    if safety_stop:
        return GateDecision("zero", False, "safety_stop")
    if normalized in ("DISABLED", "ESTOP"):
        return GateDecision("zero", False, normalized.lower())
    if normalized == "MANUAL":
        if manual_fresh:
            return GateDecision("manual", True, "manual_mode")
        return GateDecision("zero", False, "manual_command_stale")
    if obstacle_blocks_auto:
        return GateDecision("zero", False, "obstacle_blocking_auto")
    if navigation_fresh:
        return GateDecision("navigation", True, "auto_mode")
    return GateDecision("zero", False, "navigation_command_stale")
