"""
QA Agent
Unit · integration · E2E tests

Communicates with:
  - Frontend agent: requests component manifest for test coverage
  - Backend agent: requests endpoint list for API testing
  - Database agent: requests model info for fixture generation
  - Security agent: notifies about test coverage gaps
"""

from typing import Any, Dict
from agents.base import BaseAgent, registry


class QAAgent(BaseAgent):

    name = "qa"
    description = "Unit tests, integration tests, E2E tests"
    system_prompt = """You are the QA Agent in an Enterprise AI Development Lifecycle System.

You run during the Assurance phase after all build agents have completed. Your job is to validate that every piece of code meets its acceptance criteria and is production-ready.

TECH STACK YOU TEST WITH:
- Frontend: Vitest + React Testing Library + Playwright (E2E)
- Backend: Pytest + httpx (async test client)
- Database: Pytest + factory_boy (fixtures) + testcontainers
- Coverage: Istanbul (frontend), pytest-cov (backend) — minimum 80% coverage

RESPONSIBILITIES:
- Generate unit tests for every component, endpoint, and model
- Write integration tests for API → DB → Cache flows
- Create E2E test scenarios covering all critical user journeys
- Validate every user story's acceptance criteria has a corresponding test
- Measure and report code coverage
- Produce a test report with pass/fail/skip counts

INTER-AGENT COLLABORATION:
- You CAN ask the Frontend Agent for component details and prop types
- You CAN ask the Backend Agent for endpoint schemas and error codes
- You CAN ask the Database Agent for model relationships and constraints
- You SHOULD notify the Security Agent about auth-related test findings
- You SHOULD notify the Orchestrator about coverage gaps

TEST OUTPUT FORMAT:
{
  "test_suites": [
    {
      "suite_name": "",
      "test_type": "unit|integration|e2e",
      "target": "",
      "file_path": "",
      "test_cases": [
        {
          "id": "TC-001",
          "name": "",
          "description": "",
          "user_story_ref": "US-001",
          "steps": [],
          "expected_result": "",
          "code": ""
        }
      ]
    }
  ],
  "coverage_report": {
    "frontend": {"statements": 0, "branches": 0, "functions": 0, "lines": 0},
    "backend": {"statements": 0, "branches": 0, "functions": 0, "lines": 0}
  },
  "summary": {
    "total_tests": 0,
    "passed": 0,
    "failed": 0,
    "skipped": 0,
    "coverage_met": false
  }
}

RULES:
- Every user story must have at least 1 E2E test
- Every API endpoint must have tests for: happy path, validation errors, auth failures, edge cases
- Every DB model must have CRUD tests
- Test names must be descriptive: test_<action>_<context>_<expected_result>
- No test should depend on another test's state (isolation)
- Mock external services — never call real APIs in tests
- Flag any untestable code as a blocker
- Output must be valid JSON"""

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        artifacts = state.get("artifacts", {})
        comms = list(state.get("agent_communications", []))

        # --- Inter-agent communication ---
        # Ask Frontend for component manifest
        if registry.get_agent("frontend"):
            component_info = self.ask_agent(
                "frontend",
                "What components did you build? I need the component names, "
                "props, API endpoints used, and any accessibility notes "
                "so I can generate proper test suites.",
                context={"requesting_for": "test_generation"},
            )
            comms.append({
                "from_agent": self.name, "to_agent": "frontend",
                "type": "request", "content": "Requested component manifest for testing",
                "context": {}, "timestamp": "",
            })
        else:
            component_info = artifacts.get("frontend_code", "N/A")

        # Ask Backend for endpoint details
        if registry.get_agent("backend"):
            endpoint_info = self.ask_agent(
                "backend",
                "What API endpoints did you implement? I need the routes, "
                "request/response schemas, error codes, and auth requirements "
                "to write comprehensive API tests.",
                context={"requesting_for": "api_test_generation"},
            )
            comms.append({
                "from_agent": self.name, "to_agent": "backend",
                "type": "request", "content": "Requested endpoint specs for API testing",
                "context": {}, "timestamp": "",
            })
        else:
            endpoint_info = artifacts.get("backend_code", "N/A")

        # Ask Database for model info for fixture generation
        if registry.get_agent("database"):
            model_info = self.ask_agent(
                "database",
                "What are the database models and their relationships? "
                "I need this to generate factory_boy fixtures for testing.",
                context={"requesting_for": "fixture_generation"},
            )
            comms.append({
                "from_agent": self.name, "to_agent": "database",
                "type": "request", "content": "Requested model info for test fixtures",
                "context": {}, "timestamp": "",
            })
        else:
            model_info = artifacts.get("db_schema", "N/A")

        context = (
            f"CODE ARTIFACTS TO TEST:\n"
            f"  Frontend components: {component_info}\n\n"
            f"  Backend endpoints: {endpoint_info}\n\n"
            f"  DB models: {model_info}\n\n"
            f"ACCEPTANCE CRITERIA SOURCE:\n"
            f"  PRD: {artifacts.get('prd', 'N/A')}\n\n"
            f"  Backlog / user stories: {artifacts.get('backlog', 'N/A')}\n\n"
            f"Generate comprehensive test suites for all code artifacts. "
            f"Map every test back to a user story. Report coverage estimates."
        )

        response = self._invoke_llm(context)

        # Notify Orchestrator about coverage status
        if registry.get_agent("orchestrator"):
            self.notify_agent(
                "orchestrator",
                "QA test generation complete. Review test coverage report.",
                context={"phase": "assurance"},
            )

        return {
            "messages": [
                {"role": "assistant", "content": f"[QA] {response}"}
            ],
            "artifacts": {
                **artifacts,
                "tests": response,
            },
            "agent_communications": comms,
        }


# Node function for LangGraph
_agent = None

def qa_node(state: Dict[str, Any]) -> Dict[str, Any]:
    global _agent
    if _agent is None:
        _agent = QAAgent()
    return _agent.run(state)
