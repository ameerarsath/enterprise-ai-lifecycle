from typing import Annotated, List, TypedDict, Optional, Literal, Dict, Any
from datetime import datetime
from langgraph.graph.message import add_messages


class Requirement(TypedDict):
    id: str
    title: str
    description: str
    priority: Literal["must", "should", "nice"]


class Task(TypedDict):
    id: str
    title: str
    assigned_agent: str
    status: Literal["pending", "in_progress", "done", "blocked"]
    output: Optional[Dict[str, Any]]


class HumanGates(TypedDict):
    prd_approved: bool
    architecture_approved: bool
    deploy_approved: bool


class AgentComm(TypedDict):
    """Record of an inter-agent communication."""
    from_agent: str
    to_agent: str
    type: str           # "request" | "response" | "notify"
    content: str
    context: Dict[str, Any]
    timestamp: str


class ProjectState(TypedDict):
    """
    Enterprise project state for the AI development lifecycle.
    Shared across all agents via LangGraph.
    """
    # --- Identity ---
    project_id: str
    client_name: str
    raw_brief: str

    # --- Phase tracking ---
    current_phase: Literal["intake", "discovery", "build", "assurance", "deploy"]

    # --- Task management ---
    requirements: List[Requirement]
    active_tasks: List[Task]
    completed_tasks: List[Task]
    blockers: List[str]

    # --- Agent communication ---
    messages: Annotated[List[Dict[str, Any]], add_messages]

    # --- Inter-agent communication log ---
    agent_communications: List[AgentComm]

    # --- Artifacts produced by agents ---
    artifacts: Dict[str, Any]

    # --- Governance ---
    human_gates: HumanGates

    # --- Feedback loop (deploy → orchestrator) ---
    feedback_notes: List[str]

    # --- Timestamps ---
    created_at: str
    updated_at: str

    # --- Orchestration metadata ---
    next_step: Optional[str]
    is_finished: bool

    # --- Safety fields (SafeGraph) [03][07] ---
    steps_taken: int                      # Monotonic step counter
    phase_retries: Dict[str, int]         # {"discovery": 0, "build": 1, ...}
    state_hash: str                       # SHA-256 for plateau detection

    # --- Cost tracking [35] ---
    token_usage: Dict[str, int]           # {"total": 0, "per_agent": {...}}

    # --- Guardrail warnings [25][28] ---
    guardrail_warnings: List[str]
