"""
Frontend Agent
UI · components · UX

Communicates with:
  - Backend agent: requests API endpoint specs to connect components
  - SEO agent: requests meta tag and structure recommendations
  - Database agent: requests data model info for form generation
"""

from typing import Any, Dict
from agents.base import BaseAgent, registry


class FrontendAgent(BaseAgent):

    name = "frontend"
    description = "UI components, UX design, frontend code generation"
    system_prompt = """You are the Frontend Agent in an Enterprise AI Development Lifecycle System.

You receive user stories from the Manager Agent and architecture decisions from the Orchestrator, then produce production-ready frontend code.

TECH STACK YOU BUILD FOR:
- Framework: Next.js 14 (App Router)
- Styling: Tailwind CSS + shadcn/ui
- State: Zustand or React Query
- Auth: Clerk (unless spec says otherwise)
- Testing: Vitest + React Testing Library

RESPONSIBILITIES:
- Build UI components from user stories and design specs
- Implement responsive layouts (mobile-first)
- Connect to backend APIs defined by the Backend Agent
- Write unit tests for every component
- Follow accessibility standards (WCAG 2.1 AA minimum)
- Output a component manifest so the QA Agent knows what to test

INTER-AGENT COLLABORATION:
- You CAN ask the Backend Agent for API endpoint details and schemas
- You CAN ask the SEO Agent for page-specific meta tag requirements
- You CAN ask the Database Agent for entity structures to build forms
- You SHOULD notify the QA Agent about components that need testing

COMPONENT OUTPUT FORMAT — for each component:
{
  "component_name": "",
  "file_path": "",
  "props": [],
  "api_endpoints_used": [],
  "tests_written": [],
  "accessibility_notes": ""
}

CODE RULES:
- TypeScript only — no plain JS
- No inline styles — use Tailwind classes
- Every API call wrapped in React Query with loading and error states
- No hardcoded strings — use i18n keys
- Export a test file alongside every component"""

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        artifacts = state.get("artifacts", {})
        requirements = state.get("requirements", [])
        comms = list(state.get("agent_communications", []))

        # --- Inter-agent communication ---
        # Ask Backend for API spec if available
        api_spec = artifacts.get("backend_code")
        if not api_spec and registry.get_agent("backend"):
            api_spec = self.ask_agent(
                "backend",
                "What API endpoints are available? I need the routes, "
                "request/response schemas, and auth requirements to build the frontend.",
                context={"requesting_for": "frontend_api_integration"},
            )
            comms.append({
                "from_agent": self.name, "to_agent": "backend",
                "type": "request", "content": "Requested API endpoint specs",
                "context": {}, "timestamp": "",
            })

        # Ask SEO for page-specific guidance if available
        seo_guidance = artifacts.get("seo_strategy")
        if not seo_guidance and registry.get_agent("seo"):
            seo_guidance = self.ask_agent(
                "seo",
                "What are the meta tags, URL structure, and schema markup "
                "requirements for the pages I'm building?",
            )
            comms.append({
                "from_agent": self.name, "to_agent": "seo",
                "type": "request", "content": "Requested SEO page guidance",
                "context": {}, "timestamp": "",
            })

        # Notify QA about the components being built
        if registry.get_agent("qa"):
            self.notify_agent(
                "qa",
                "Frontend components are being generated. "
                "Prepare test suites for component testing.",
                context={"phase": "build"},
            )

        context = (
            f"USER STORIES & REQUIREMENTS:\n"
            f"  Requirements: {requirements}\n\n"
            f"  PRD: {artifacts.get('prd', 'N/A')}\n\n"
            f"  Sprint backlog: {artifacts.get('backlog', 'N/A')}\n\n"
            f"  SEO strategy: {seo_guidance or 'N/A'}\n\n"
            f"  Architecture: {artifacts.get('architecture', 'N/A')}\n\n"
            f"  Backend API spec: {api_spec or 'N/A'}\n\n"
            f"Build the frontend components following the tech stack and code rules. "
            f"Output a component manifest for each component created."
        )

        response = self._invoke_llm(context)

        return {
            "messages": [
                {"role": "assistant", "content": f"[Frontend] {response}"}
            ],
            "artifacts": {
                **artifacts,
                "frontend_code": response,
            },
            "agent_communications": comms,
        }


# Node function for LangGraph
_agent = None

def frontend_node(state: Dict[str, Any]) -> Dict[str, Any]:
    global _agent
    if _agent is None:
        _agent = FrontendAgent()
    return _agent.run(state)
