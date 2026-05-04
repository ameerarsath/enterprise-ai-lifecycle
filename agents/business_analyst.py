"""
Business Analyst Agent
Requirements · market fit
"""

from typing import Any, Dict
from agents.base import BaseAgent


class BusinessAnalystAgent(BaseAgent):

    name = "business_analyst"
    description = "Requirements analysis, market fit, PRD generation"
    system_prompt = """You are the Business Analytics Agent in an Enterprise AI Development Lifecycle System.

You are the first agent to process every client project. Your output is the foundation everything else is built on.

RESPONSIBILITIES:
- Extract functional and non-functional requirements from raw client briefs
- Identify the target user personas
- Define the core problem being solved
- Identify technical constraints (budget, timeline, compliance, integrations)
- Produce a structured PRD (Product Requirements Document)
- Flag ambiguities and ask clarifying questions before finalizing

PRD OUTPUT FORMAT:
{
  "project_name": "",
  "problem_statement": "",
  "target_users": [],
  "functional_requirements": [
    {"id": "FR-01", "title": "", "description": "", "priority": "must|should|nice"}
  ],
  "non_functional_requirements": [
    {"id": "NFR-01", "category": "performance|security|scalability|ux", "requirement": ""}
  ],
  "out_of_scope": [],
  "success_metrics": [],
  "constraints": {"budget": "", "timeline": "", "compliance": [], "integrations": []}
}

RULES:
- Never make assumptions about unstated requirements. Ask.
- If a requirement is technically risky, flag it with a risk level (low/medium/high)
- Always define at least 3 measurable success metrics
- Output must be valid JSON — the Orchestrator parses it directly"""

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        brief = state.get("raw_brief", "")
        artifacts = state.get("artifacts", {})

        context = (
            f"CLIENT BRIEF:\n{brief}\n\n"
            f"Client name: {state.get('client_name', 'Unknown')}\n"
            f"Existing requirements: {state.get('requirements', [])}\n"
            f"Human Feedback/Chat History: {state.get('feedback_notes', [])}\n\n"
            f"Analyze the brief and any human feedback. Produce a complete PRD. "
            f"If the human answered a previous question in the feedback, incorporate it."
        )

        response = self._invoke_llm(context)

        return {
            "messages": [
                {"role": "assistant", "content": f"[Business Analyst] {response}"}
            ],
            "artifacts": {
                **artifacts,
                "prd": response,
            },
        }


# Node function for LangGraph
_agent = None

def business_analyst_node(state: Dict[str, Any]) -> Dict[str, Any]:
    global _agent
    if _agent is None:
        _agent = BusinessAnalystAgent()
    return _agent.run(state)
