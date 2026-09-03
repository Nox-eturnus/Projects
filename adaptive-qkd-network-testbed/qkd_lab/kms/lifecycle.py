from __future__ import annotations

from qkd_lab.kms.models import KeyState


ALLOWED_TRANSITIONS = {
    KeyState.AVAILABLE: {KeyState.RESERVED, KeyState.CONSUMED, KeyState.VOID},
    KeyState.RESERVED: {KeyState.AVAILABLE, KeyState.CONSUMED, KeyState.VOID},
    KeyState.CONSUMED: set(),
    KeyState.VOID: set(),
}


def transition_allowed(old: KeyState, new: KeyState) -> bool:
    return new in ALLOWED_TRANSITIONS[old]