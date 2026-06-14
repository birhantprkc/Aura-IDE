from __future__ import annotations

from enum import Enum
import re


class DroneCommand(Enum):
    INSTALL = "install"
    REVISE = "revise"
    DISCARD = "discard"
    NEW = "new"
    LOAD = "load"
    HELP = "help"
    UNKNOWN = "unknown"


_INSTALL_PATTERNS = [
    r"\binstall\b",
    r"\binstall it\b",
    r"\binstall the drone\b",
    r"\bregister it\b",
    r"\bregister the drone\b",
]

_DISCARD_PATTERNS = [
    r"\bdiscard\b",
    r"\bdiscard it\b",
    r"\bdiscard this drone\b",
    r"\bthrow away\b",
    r"\bdelete it\b",
    r"\bdelete this drone\b",
]

_NEW_PATTERNS = [
    r"\bnew\b",
    r"\bnew drone\b",
    r"\bstart over\b",
    r"\bstart new\b",
    r"\bcreate new\b",
    r"\bdifferent drone\b",
    r"\bscratch\b",
]

_LOAD_PATTERNS = [
    r"\bload\s+(.+)",
    r"\bswitch to\s+(.+)",
]

_HELP_PATTERNS = [
    r"\bhelp\b",
    r"\bwhat can i say\b",
    r"\bwhat can you do\b",
    r"\bcommands?\b",
]


def parse_drone_command(text: str, phase: str) -> tuple[DroneCommand, str | None]:
    """Parse user text into a command and optional argument.

    Returns ``(DroneCommand, arg_or_None)``.
    """
    lowered = text.strip().lower()
    if not lowered:
        return DroneCommand.UNKNOWN, None

    # Global commands — checked first regardless of phase.
    for pattern in _NEW_PATTERNS:
        if re.search(pattern, lowered):
            return DroneCommand.NEW, None

    match = None
    for pattern in _LOAD_PATTERNS:
        match = re.search(pattern, lowered)
        if match:
            return DroneCommand.LOAD, match.group(1).strip()

    for pattern in _HELP_PATTERNS:
        if re.search(pattern, lowered):
            return DroneCommand.HELP, None

    # Phase-specific commands.
    if phase == "awaiting_decision":
        for pattern in _INSTALL_PATTERNS:
            if re.search(pattern, lowered):
                return DroneCommand.INSTALL, None

        for pattern in _DISCARD_PATTERNS:
            if re.search(pattern, lowered):
                return DroneCommand.DISCARD, None

        # In awaiting_decision, any non-command text is a revision.
        return DroneCommand.REVISE, text.strip()

    # In workshop, building, readiness_failed, proof_failed, iterating:
    # No phase-specific commands beyond global ones.
    return DroneCommand.UNKNOWN, None
