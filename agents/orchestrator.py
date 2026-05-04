"""
Orchestrator Agent
Routes tasks · monitors progress · resolves conflicts
"""

from typing import Any, Dict
from agents.base import BaseAgent


class OrchestratorAgent(BaseAgent):

    name = "orchestrator"
    description = "Routes tasks, monitors progress, resolves conflicts"
    system_prompt = """You are the Orchestrator Agent for an Enterprise AI Development Lifecycle System.

Your role is the central brain of the system. You receive client project requirements and coordinate all specialist agents to deliver complete software projects.

RESPONSIBILITIES:
- Parse incoming client briefs and extract structured requirements
- Decompose requirements into tasks and assign each to the correct specialist agent
- Maintain a shared project state object (JSON) that all agents read and write
- Monitor agent outputs and validate completion before routing to the next stage
- Detect conflicts between agent outputs and resolve or escalate them
- Enforce human-in-the-loop checkpoints at: PRD approval, architecture sign-off, and pre-deploy review
- Track overall project progress and report status to the Manager Agent

PROJECT STATE SCHEMA you maintain:
{
  "project_id": "",
  "client_name": "",
  "requirements": [],
  "current_phase": "discovery|build|assurance|deploy",
  "active_tasks": [],
  "completed_tasks": [],
  "blockers": [],
  "artifacts": {
    "prd": null,
    "architecture": null,
    "code": {},
    "tests": {},
    "security_report": null
  },
  "human_gates": {
    "prd_approved": false,
    "architecture_approved": false,
    "deploy_approved": false
  }
}

ROUTING RULES:
- New project brief → Business Analytics Agent first
- After PRD created → Scrum Master Agent for sprint planning
- After sprints defined → Frontend, Backend, DB agents (parallel where possible)
- After code complete → QA Agent and Security Agent (parallel)
- After both pass → request human deploy approval
- After approval → Deploy pipeline

RESPONSE FORMAT:
Always respond in JSON with keys: "action", "target_agent", "task", "context", "blockers"

Never skip a validation step. If an agent output is incomplete or contradicts another, flag it before routing forward."""

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        phase = state.get("current_phase", "intake")
        blockers = state.get("blockers", [])
        feedback = state.get("feedback_notes", [])
        artifacts = state.get("artifacts", {})

        context = (
            f"PROJECT STATE:\n"
            f"  Project ID: {state.get('project_id', 'N/A')}\n"
            f"  Client: {state.get('client_name', 'N/A')}\n"
            f"  Current phase: {phase}\n"
            f"  Active tasks: {state.get('active_tasks', [])}\n"
            f"  Completed tasks: {len(state.get('completed_tasks', []))}\n"
            f"  Blockers: {blockers}\n"
            f"  Human gates: {state.get('human_gates', {})}\n"
            f"  Feedback from deploy: {feedback}\n"
            f"  Available artifacts: {list(artifacts.keys())}\n\n"
            f"  Raw brief: {state.get('raw_brief', 'N/A')}\n\n"
            f"Determine the next action: which agent to route to, what task to assign, "
            f"and whether any blockers need resolution."
        )

        response = self._invoke_llm(context)

        # Determine next phase
        next_phase = self._resolve_next_phase(state)

        return {
            "current_phase": next_phase,
            "messages": [
                {"role": "assistant", "content": f"[Orchestrator] {response}"}
            ],
        }

    def _resolve_next_phase(self, state: Dict[str, Any]) -> str:
        """Determine the next phase based on current state and routing rules."""
        phase = state.get("current_phase", "intake")
        gates = state.get("human_gates", {})
        feedback = state.get("feedback_notes", [])

        # Feedback loop: deploy sent issues back
        if feedback and phase == "deploy":
            return "discovery"

        phase_order = ["intake", "discovery", "build", "assurance", "deploy"]
        current_idx = phase_order.index(phase) if phase in phase_order else 0

        # Enforce human gates before advancing
        if phase == "discovery" and not gates.get("prd_approved", False):
            return "discovery"
        if phase == "build" and not gates.get("architecture_approved", False):
            return "build"

        if current_idx < len(phase_order) - 1:
            return phase_order[current_idx + 1]

        return "deploy"


# Node function for LangGraph
_agent = None

def orchestrator_node(state: Dict[str, Any]) -> Dict[str, Any]:
    global _agent
    if _agent is None:
        _agent = OrchestratorAgent()
    return _agent.run(state)
