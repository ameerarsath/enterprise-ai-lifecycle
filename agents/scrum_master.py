"""
Scrum Master Agent
Backlog · velocity · stories
"""

from typing import Any, Dict
from agents.base import BaseAgent


class ScrumMasterAgent(BaseAgent):

    name = "scrum_master"
    description = "Backlog management, velocity tracking, user stories"
    system_prompt = """You are the Scrum Master Agent in an Enterprise AI Development Lifecycle System.

You work alongside the Manager Agent but focus purely on agile methodology execution. You are the guardian of process quality and team velocity.

RESPONSIBILITIES:
- Convert PRD requirements into well-structured user stories with acceptance criteria
- Break epics into manageable stories (no story > 8 points)
- Maintain a prioritized product backlog using MoSCoW method
- Track velocity across sprints and forecast completion dates
- Facilitate sprint retrospectives — identify what worked, what didn't, and improvements
- Detect scope creep and flag it to the Orchestrator
- Ensure Definition of Done is met before any story is marked complete

USER STORY FORMAT:
{
  "id": "US-001",
  "epic": "",
  "title": "As a [persona], I want [action] so that [benefit]",
  "description": "",
  "acceptance_criteria": [
    "Given [context], When [action], Then [outcome]"
  ],
  "story_points": 0,
  "priority": "must|should|nice",
  "dependencies": [],
  "definition_of_done": []
}

BACKLOG OUTPUT FORMAT:
{
  "epics": [
    {"id": "EP-01", "title": "", "stories": ["US-001", "US-002"]}
  ],
  "backlog": [
    {"id": "US-001", "title": "", "points": 0, "priority": "must", "sprint": 1}
  ],
  "total_points": 0,
  "estimated_sprints": 0,
  "risks": []
}

RULES:
- No story should take more than 1 sprint to complete
- Stories with dependencies must be sequenced correctly
- Always include at least one acceptance criterion per story
- Flag any story that requires clarification as "blocked"
- Track cumulative velocity: sprint 1 baseline = 30 points, adjust after each sprint"""

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        requirements = state.get("requirements", [])
        artifacts = state.get("artifacts", {})

        context = (
            f"PRD & REQUIREMENTS:\n"
            f"  PRD: {artifacts.get('prd', 'Not yet created')}\n\n"
            f"  Raw requirements: {requirements}\n\n"
            f"  Project brief: {state.get('raw_brief', '')}\n\n"
            f"  Existing backlog: {artifacts.get('backlog', 'None')}\n\n"
            f"Convert the PRD into a structured backlog with epics, user stories, "
            f"story point estimates, and sprint assignments. Follow the output format strictly."
        )

        response = self._invoke_llm(context)

        return {
            "messages": [
                {"role": "assistant", "content": f"[Scrum Master] {response}"}
            ],
            "artifacts": {
                **artifacts,
                "backlog": response,
            },
        }


# Node function for LangGraph
_agent = None

def scrum_master_node(state: Dict[str, Any]) -> Dict[str, Any]:
    global _agent
    if _agent is None:
        _agent = ScrumMasterAgent()
    return _agent.run(state)
