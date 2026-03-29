from enum import Enum


class ModeState(str, Enum):
    NORMAL = "NORMAL"
    RETRYING = "RETRYING"
    READ_ONLY = "READ_ONLY"
    IDLE_SAFE = "IDLE_SAFE"


_ALLOWED_TRANSITIONS = {
    ModeState.NORMAL: {ModeState.RETRYING, ModeState.READ_ONLY, ModeState.IDLE_SAFE},
    ModeState.RETRYING: {ModeState.NORMAL, ModeState.READ_ONLY, ModeState.IDLE_SAFE},
    ModeState.READ_ONLY: {ModeState.NORMAL, ModeState.IDLE_SAFE},
    ModeState.IDLE_SAFE: {ModeState.NORMAL},
}


def is_transition_allowed(current: ModeState, target: ModeState) -> bool:
    if current == target:
        return True
    return target in _ALLOWED_TRANSITIONS[current]


def transition_to(current: ModeState, target: ModeState) -> ModeState:
    if not is_transition_allowed(current, target):
        raise ValueError(f"Invalid mode transition: {current.value} -> {target.value}")
    return target
