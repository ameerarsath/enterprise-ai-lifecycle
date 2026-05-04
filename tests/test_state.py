"""
Tests for ProjectState and inter-agent communication.
"""
import pytest
from state.project_state import ProjectState, Requirement, Task, HumanGates, AgentComm
from agents.base import BaseAgent, AgentRegistry, AgentMessage, registry


# ---------------------------------------------------------------------------
# State structure tests
# ---------------------------------------------------------------------------

class TestProjectState:

    def test_requirement_structure(self):
        req: Requirement = {
            "id": "FR-01",
            "title": "User authentication",
            "description": "Users can log in with email and password",
            "priority": "must",
        }
        assert req["id"] == "FR-01"
        assert req["priority"] == "must"

    def test_task_structure(self):
        task: Task = {
            "id": "build-frontend-0",
            "title": "Build login page",
            "assigned_agent": "frontend",
            "status": "pending",
            "output": None,
        }
        assert task["assigned_agent"] == "frontend"
        assert task["status"] == "pending"

    def test_human_gates_structure(self):
        gates: HumanGates = {
            "prd_approved": False,
            "architecture_approved": False,
            "deploy_approved": False,
        }
        assert not gates["prd_approved"]

    def test_agent_comm_structure(self):
        comm: AgentComm = {
            "from_agent": "frontend",
            "to_agent": "backend",
            "type": "request",
            "content": "What API endpoints are available?",
            "context": {"requesting_for": "api_integration"},
            "timestamp": "2026-01-01T00:00:00Z",
        }
        assert comm["from_agent"] == "frontend"
        assert comm["type"] == "request"

    def test_full_project_state(self):
        state: ProjectState = {
            "project_id": "test-123",
            "client_name": "Acme Corp",
            "raw_brief": "Build an e-commerce platform",
            "current_phase": "intake",
            "requirements": [],
            "active_tasks": [],
            "completed_tasks": [],
            "blockers": [],
            "messages": [],
            "agent_communications": [],
            "artifacts": {},
            "human_gates": {
                "prd_approved": False,
                "architecture_approved": False,
                "deploy_approved": False,
            },
            "feedback_notes": [],
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
            "next_step": None,
            "is_finished": False,
        }
        assert state["project_id"] == "test-123"
        assert state["current_phase"] == "intake"
        assert state["agent_communications"] == []


# ---------------------------------------------------------------------------
# Agent Registry tests
# ---------------------------------------------------------------------------

class DummyAgent(BaseAgent):
    """Minimal agent for testing."""
    name = "dummy"
    description = "Test agent"
    system_prompt = "You are a test agent."

    def run(self, state):
        return {"messages": [{"role": "assistant", "content": "dummy ran"}]}

    def handle_request(self, from_agent, query, context=None):
        return f"Dummy response to {from_agent}: {query}"


class DummyAgent2(BaseAgent):
    """Second test agent."""
    name = "dummy2"
    description = "Test agent 2"
    system_prompt = "You are a test agent 2."

    def run(self, state):
        return {"messages": [{"role": "assistant", "content": "dummy2 ran"}]}

    def handle_request(self, from_agent, query, context=None):
        return f"Dummy2 response to {from_agent}: {query}"


class TestAgentRegistry:

    def setup_method(self):
        """Reset registry before each test."""
        registry.clear()

    def test_register_and_discover(self):
        agent = DummyAgent()
        assert "dummy" in registry.list_agents()
        assert registry.get_agent("dummy") is agent

    def test_unknown_agent_returns_none(self):
        assert registry.get_agent("nonexistent") is None

    def test_list_agents(self):
        DummyAgent()
        DummyAgent2()
        agents = registry.list_agents()
        assert "dummy" in agents
        assert "dummy2" in agents

    def test_clear_registry(self):
        DummyAgent()
        assert len(registry.list_agents()) == 1
        registry.clear()
        assert len(registry.list_agents()) == 0


class TestInterAgentCommunication:

    def setup_method(self):
        registry.clear()

    def test_ask_agent(self):
        agent1 = DummyAgent()
        agent2 = DummyAgent2()

        response = agent1.ask_agent("dummy2", "What is 2+2?")
        assert "Dummy2 response to dummy" in response
        assert "What is 2+2?" in response

    def test_ask_nonexistent_agent(self):
        agent1 = DummyAgent()
        response = agent1.ask_agent("nonexistent", "Hello?")
        assert "ERROR" in response

    def test_notify_agent(self):
        agent1 = DummyAgent()
        agent2 = DummyAgent2()

        agent1.notify_agent("dummy2", "Heads up: something changed")
        notifications = agent2.get_notifications()
        assert len(notifications) == 1
        assert notifications[0]["from"] == "dummy"
        assert "something changed" in notifications[0]["message"]

    def test_broadcast(self):
        agent1 = DummyAgent()
        agent2 = DummyAgent2()

        agent1.broadcast("Architecture decision made")
        # agent2 should have received it, agent1 should not
        assert len(agent2.get_notifications()) == 1
        assert len(agent1.get_notifications()) == 0

    def test_message_log(self):
        agent1 = DummyAgent()
        agent2 = DummyAgent2()

        agent1.ask_agent("dummy2", "Question 1")
        agent1.notify_agent("dummy2", "FYI info")

        log = registry.get_message_log()
        # ask_agent produces 1 entry (request), notify produces 1
        # Note: DummyAgent overrides handle_request, so no auto-logged response
        assert len(log) == 2
        assert log[0]["type"] == "request"
        assert log[1]["type"] == "notify"

    def test_clear_notifications(self):
        agent1 = DummyAgent()
        agent2 = DummyAgent2()

        agent1.notify_agent("dummy2", "Message 1")
        agent1.notify_agent("dummy2", "Message 2")
        assert len(agent2.get_notifications()) == 2

        agent2.clear_notifications()
        assert len(agent2.get_notifications()) == 0

    def test_agent_message_to_dict(self):
        msg = AgentMessage(
            from_agent="frontend",
            to_agent="backend",
            message_type="request",
            content="Need API spec",
            context={"page": "login"},
        )
        d = msg.to_dict()
        assert d["from_agent"] == "frontend"
        assert d["to_agent"] == "backend"
        assert d["type"] == "request"
        assert d["content"] == "Need API spec"
        assert d["context"]["page"] == "login"
        assert "timestamp" in d
