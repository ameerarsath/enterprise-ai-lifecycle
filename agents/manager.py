"""
Manager Agent
Sprint planning · resource allocation · reporting
"""

from typing import Any, Dict
from agents.base import BaseAgent


class ManagerAgent(BaseAgent):

    name = "manager"
    description = "Sprint planning, resource allocation, reporting"
    system_prompt = """You are the Manager Agent in an Enterprise AI Development Lifecycle System.

You operate one layer below the Orchestrator. Your job is agile project management — sprint planning, velocity tracking, and reporting.

RESPONSIBILITIES:
- Convert the PRD (from BA Agent) into user stories with acceptance criteria
- Estimate story points for each task
- Organize stories into 2-week sprints
- Track which agents are working on which tasks
- Flag blockers to the Orchestrator immediately
- Generate daily status summaries and sprint retrospectives
- Maintain the backlog and re-prioritize when scope changes

USER STORY FORMAT:
"As a [user type], I want [action] so that [benefit]"
Acceptance criteria: Given [context], When [action], Then [outcome]

SPRINT RULES:
- Max 40 story points per sprint
- Frontend, Backend, DB work can run in parallel
- QA tasks cannot start until the sprint's build tasks are complete
- Security review runs after QA passes

Always output a structured sprint board in JSON:
{
  "sprint_number": 1,
  "goal": "",
  "stories": [
    {"id": "US-01", "title": "", "points": 0, "assigned_agent": "", "status": "todo|in_progress|done", "acceptance_criteria": []}
  ],
  "velocity": 0,
  "blockers": []
}"""

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        phase = state.get("current_phase", "intake")
        requirements = state.get("requirements", [])
        artifacts = state.get("artifacts", {})
        brief = state.get("raw_brief", "")

        context = (
            f"CURRENT STATE:\n"
            f"  Phase: {phase}\n"
            f"  Requirements count: {len(requirements)}\n"
            f"  Requirements: {requirements}\n"
            f"  PRD: {artifacts.get('prd', 'Not yet created')}\n"
            f"  Backlog: {artifacts.get('backlog', 'Not yet created')}\n"
            f"  Active tasks: {state.get('active_tasks', [])}\n"
            f"  Completed tasks: {len(state.get('completed_tasks', []))}\n"
            f"  Project brief: {brief}\n"
            f"  Human Feedback/Chat: {state.get('feedback_notes', [])}\n\n"
            f"Create or update the sprint plan. If the human requested changes "
            f"to the timeline or priority in the chat history, adjust the stories accordingly."
        )

        response = self._invoke_llm(context)

        # Create task assignments based on phase
        new_tasks = self._create_phase_tasks(phase, requirements)

        return {
            "active_tasks": new_tasks,
            "messages": [
                {"role": "assistant", "content": f"[Manager] {response}"}
            ],
        }

    def _create_phase_tasks(self, phase: str, requirements: list) -> list:
        """Create task assignments for the given phase."""
        phase_agents = {
            "discovery": ["business_analyst", "scrum_master", "seo"],
            "build":     ["frontend", "backend", "database"],
            "assurance": ["qa", "security"],
            "deploy":    ["deploy"],
        }

        agents = phase_agents.get(phase, [])
        tasks = []
        for i, agent_name in enumerate(agents):
            tasks.append({
                "id": f"{phase}-{agent_name}-{i}",
                "title": f"{phase.title()} task for {agent_name}",
                "assigned_agent": agent_name,
                "status": "pending",
                "output": None,
            })
        return tasks


# Node function for LangGraph
_agent = None

def manager_node(state: Dict[str, Any]) -> Dict[str, Any]:
    global _agent
    if _agent is None:
        _agent = ManagerAgent()
    return _agent.run(state)
