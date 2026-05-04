"""
Phase transition logic and validation for the project lifecycle.
"""

from typing import Any, Dict, List


# Ordered lifecycle phases
PHASE_ORDER = ["intake", "discovery", "build", "assurance", "deploy"]

# Which agents run in each phase
PHASE_AGENTS = {
    "discovery": ["business_analyst", "scrum_master", "seo"],
    "build":     ["frontend", "backend", "database"],
    "assurance": ["qa", "security"],
    "deploy":    ["deploy"],
}


def can_advance_phase(state: Dict[str, Any]) -> bool:
    """
    Check whether the current phase's work is complete enough
    to move to the next phase.
    """
    phase = state.get("current_phase", "intake")
    active = state.get("active_tasks", [])
    blockers = state.get("blockers", [])

    # Cannot advance if there are unresolved blockers
    if blockers:
        return False

    # Cannot advance if any active task is still pending or in progress
    incomplete = [t for t in active if t.get("status") in ("pending", "in_progress")]
    if incomplete:
        return False

    # Check human gates
    gates = state.get("human_gates", {})
    if phase == "discovery" and not gates.get("prd_approved", False):
        return False
    if phase == "build" and not gates.get("architecture_approved", False):
        return False
    if phase == "deploy" and not gates.get("deploy_approved", False):
        return False

    return True


def get_next_phase(current_phase: str) -> str:
    """Return the next phase in the lifecycle, or stay at deploy."""
    if current_phase not in PHASE_ORDER:
        return "intake"
    idx = PHASE_ORDER.index(current_phase)
    if idx < len(PHASE_ORDER) - 1:
        return PHASE_ORDER[idx + 1]
    return "deploy"


def should_feedback_loop(state: Dict[str, Any]) -> bool:
    """Check if the deploy phase produced feedback requiring a loop back."""
    feedback = state.get("feedback_notes", [])
    return len(feedback) > 0 and state.get("current_phase") == "deploy"


def get_phase_agents(phase: str) -> List[str]:
    """Return the list of agent names for the given phase."""
    return PHASE_AGENTS.get(phase, [])
