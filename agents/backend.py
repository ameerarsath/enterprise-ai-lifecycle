"""
Backend Agent
APIs · logic · services

Communicates with:
  - Database agent: requests schema details for model definitions
  - Frontend agent: notifies about API changes and new endpoints
  - Security agent: requests auth pattern recommendations
"""

from typing import Any, Dict
from agents.base import BaseAgent, registry


class BackendAgent(BaseAgent):

    name = "backend"
    description = "APIs, business logic, services"
    system_prompt = """You are the Backend Agent in an Enterprise AI Development Lifecycle System.

You build the server-side logic, APIs, and business rules for client projects.

TECH STACK YOU BUILD FOR:
- Runtime: Python 3.12 + FastAPI
- ORM: SQLAlchemy + Alembic
- Auth: JWT + role-based access control
- Cache: Redis
- Queue: Celery
- Testing: Pytest

RESPONSIBILITIES:
- Design and implement REST API endpoints from user stories
- Implement business logic and validation
- Define data models (coordinate with DB Agent on schema)
- Write integration tests for every endpoint
- Produce an OpenAPI spec that the Frontend Agent consumes
- Document all environment variables required

INTER-AGENT COLLABORATION:
- You CAN ask the Database Agent for schema details and table relationships
- You CAN ask the Security Agent for auth and encryption recommendations
- You SHOULD notify the Frontend Agent about new/changed API endpoints
- You SHOULD notify the QA Agent about endpoints that need testing

API ENDPOINT OUTPUT FORMAT:
{
  "endpoint": "POST /api/v1/projects",
  "description": "",
  "auth_required": true,
  "request_schema": {},
  "response_schema": {},
  "error_codes": [],
  "test_cases": []
}

CODE RULES:
- Every endpoint has input validation via Pydantic
- All DB operations go through the service layer — never direct in routes
- All sensitive config via environment variables — never hardcoded
- Rate limiting on all public endpoints
- Return standardized error responses: {"error": {"code": "", "message": "", "details": {}}}"""

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        artifacts = state.get("artifacts", {})
        requirements = state.get("requirements", [])
        comms = list(state.get("agent_communications", []))

        # --- Inter-agent communication ---
        # Ask Database for schema if available
        db_schema = artifacts.get("db_schema")
        if not db_schema and registry.get_agent("database"):
            db_schema = self.ask_agent(
                "database",
                "What is the database schema? I need table definitions, "
                "relationships, and column types to build the ORM models and API.",
                context={"requesting_for": "backend_orm_models"},
            )
            comms.append({
                "from_agent": self.name, "to_agent": "database",
                "type": "request", "content": "Requested DB schema for ORM models",
                "context": {}, "timestamp": "",
            })

        # Ask Security for auth recommendations
        if registry.get_agent("security"):
            auth_advice = self.ask_agent(
                "security",
                "What authentication and authorization patterns should I implement? "
                "Any specific JWT configurations or RBAC rules?",
                context={"requesting_for": "backend_auth_setup"},
            )
            comms.append({
                "from_agent": self.name, "to_agent": "security",
                "type": "request", "content": "Requested auth pattern recommendations",
                "context": {}, "timestamp": "",
            })
        else:
            auth_advice = "Default: JWT + RBAC"

        # Notify Frontend about API being built
        if registry.get_agent("frontend"):
            self.notify_agent(
                "frontend",
                "Backend API endpoints are being generated. "
                "OpenAPI spec will be available in artifacts.",
            )

        context = (
            f"USER STORIES & REQUIREMENTS:\n"
            f"  Requirements: {requirements}\n\n"
            f"  PRD: {artifacts.get('prd', 'N/A')}\n\n"
            f"  Sprint backlog: {artifacts.get('backlog', 'N/A')}\n\n"
            f"  DB schema: {db_schema or 'N/A'}\n\n"
            f"  Auth recommendations: {auth_advice}\n\n"
            f"  Architecture: {artifacts.get('architecture', 'N/A')}\n\n"
            f"Design and implement the backend API endpoints following the tech stack "
            f"and code rules. Produce an OpenAPI-compatible specification for each endpoint."
        )

        response = self._invoke_llm(context)

        return {
            "messages": [
                {"role": "assistant", "content": f"[Backend] {response}"}
            ],
            "artifacts": {
                **artifacts,
                "backend_code": response,
            },
            "agent_communications": comms,
        }


# Node function for LangGraph
_agent = None

def backend_node(state: Dict[str, Any]) -> Dict[str, Any]:
    global _agent
    if _agent is None:
        _agent = BackendAgent()
    return _agent.run(state)
