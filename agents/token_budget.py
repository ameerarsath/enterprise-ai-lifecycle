"""
TokenBudgetManager — Per-project and per-agent token cost control.

Solves: [31] Token explosion · [34] Expensive retries · [35] No cost ceiling · [55] Cost estimation errors
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class BudgetExhaustedError(Exception):
    """Raised when an agent or project exceeds its token budget."""
    pass


class TokenBudgetManager:
    """
    Tracks and limits token usage per project and per agent.

    [31] Context compression — only sends relevant state fields per agent
    [34] Smart retry — decreasing context on each retry attempt
    [35] Hard ceiling — raises BudgetExhaustedError when exceeded
    [55] Real tracking — actual tokens, not estimates
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._project_budgets: Dict[str, int] = {}
            cls._agent_budgets: Dict[str, int] = {}
            cls._usage: Dict[str, Dict[str, int]] = {}  # {project: {agent: tokens}}
            cls._usage_log: List[dict] = []
        return cls._instance

    # Default budgets
    DEFAULT_PROJECT_BUDGET = 2_000_000   # 2M tokens per project
    DEFAULT_AGENT_BUDGET = 200_000       # 200K per agent per sprint

    # --- Budget Management ---

    def set_project_budget(self, project_id: str, max_tokens: int) -> None:
        self._project_budgets[project_id] = max_tokens

    def set_agent_budget(self, agent_name: str, max_tokens: int) -> None:
        self._agent_budgets[agent_name] = max_tokens

    # --- Usage Tracking ---

    def track_usage(self, project_id: str, agent_name: str,
                    input_tokens: int, output_tokens: int) -> None:
        total = input_tokens + output_tokens
        if project_id not in self._usage:
            self._usage[project_id] = {}
        current = self._usage[project_id].get(agent_name, 0)
        self._usage[project_id][agent_name] = current + total

        self._usage_log.append({
            "project_id": project_id, "agent": agent_name,
            "input_tokens": input_tokens, "output_tokens": output_tokens,
            "total": total, "cumulative": current + total,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def get_project_usage(self, project_id: str) -> int:
        return sum(self._usage.get(project_id, {}).values())

    def get_agent_usage(self, project_id: str, agent_name: str) -> int:
        return self._usage.get(project_id, {}).get(agent_name, 0)

    def get_remaining_project(self, project_id: str) -> int:
        budget = self._project_budgets.get(project_id, self.DEFAULT_PROJECT_BUDGET)
        return max(0, budget - self.get_project_usage(project_id))

    def get_remaining_agent(self, project_id: str, agent_name: str) -> int:
        budget = self._agent_budgets.get(agent_name, self.DEFAULT_AGENT_BUDGET)
        return max(0, budget - self.get_agent_usage(project_id, agent_name))

    # --- Budget Checks ---

    def check_budget(self, project_id: str, agent_name: str) -> None:
        """Raises BudgetExhaustedError if over budget."""
        if self.get_remaining_project(project_id) <= 0:
            raise BudgetExhaustedError(
                f"Project '{project_id}' exceeded token budget "
                f"({self.get_project_usage(project_id)} tokens used)"
            )
        if self.get_remaining_agent(project_id, agent_name) <= 0:
            raise BudgetExhaustedError(
                f"Agent '{agent_name}' exceeded token budget "
                f"({self.get_agent_usage(project_id, agent_name)} tokens used)"
            )

    def is_over_budget(self, project_id: str) -> bool:
        return self.get_remaining_project(project_id) <= 0

    # --- Context Compression [31] ---

    AGENT_RELEVANT_FIELDS = {
        "orchestrator": ["project_id", "client_name", "current_phase", "active_tasks",
                         "completed_tasks", "blockers", "human_gates", "feedback_notes",
                         "raw_brief"],
        "manager": ["current_phase", "requirements", "active_tasks", "raw_brief"],
        "business_analyst": ["raw_brief", "client_name", "requirements"],
        "scrum_master": ["requirements", "raw_brief"],
        "seo": ["raw_brief", "client_name", "requirements"],
        "frontend": ["requirements"],
        "backend": ["requirements"],
        "database": ["requirements"],
        "qa": ["requirements"],
        "security": [],
        "deploy": [],
    }

    AGENT_RELEVANT_ARTIFACTS = {
        "orchestrator": ["prd", "backlog", "tests", "security_audit"],
        "manager": ["prd", "backlog"],
        "business_analyst": [],
        "scrum_master": ["prd"],
        "seo": ["prd"],
        "frontend": ["prd", "backlog", "seo_strategy", "backend_code"],
        "backend": ["prd", "backlog", "db_schema"],
        "database": ["prd", "backlog"],
        "qa": ["frontend_code", "backend_code", "db_schema", "backlog"],
        "security": ["frontend_code", "backend_code", "db_schema"],
        "deploy": ["frontend_code", "backend_code", "db_schema", "tests", "security_audit"],
    }

    @classmethod
    def compress_state(cls, state: Dict[str, Any], agent_name: str) -> Dict[str, Any]:
        """
        Return only the state fields relevant to this agent.
        Dramatically reduces token usage per call.
        """
        compressed = {}

        # Include relevant top-level fields
        relevant_fields = cls.AGENT_RELEVANT_FIELDS.get(agent_name, [])
        for field in relevant_fields:
            if field in state:
                compressed[field] = state[field]

        # Include only relevant artifacts
        relevant_artifacts = cls.AGENT_RELEVANT_ARTIFACTS.get(agent_name, [])
        all_artifacts = state.get("artifacts", {})
        compressed["artifacts"] = {
            k: v for k, v in all_artifacts.items()
            if k in relevant_artifacts
        }

        # Always include identity
        compressed["project_id"] = state.get("project_id", "")
        compressed["current_phase"] = state.get("current_phase", "")

        return compressed

    # --- Smart Retry [34] ---

    @classmethod
    def get_retry_strategy(cls, attempt: int, error: str) -> Dict[str, Any]:
        """
        Returns retry configuration based on attempt number.
        Each retry uses less context to save tokens.
        """
        if attempt == 1:
            return {"strategy": "full_context", "context_ratio": 1.0, "hint": None}
        elif attempt == 2:
            return {"strategy": "compressed", "context_ratio": 0.5,
                    "hint": f"Previous attempt failed: {error[:200]}. Try a different approach."}
        elif attempt == 3:
            return {"strategy": "minimal", "context_ratio": 0.2,
                    "hint": f"IMPORTANT: Two previous attempts failed. Error: {error[:100]}. "
                            "Produce a minimal, correct output."}
        else:
            return {"strategy": "escalate", "context_ratio": 0, "hint": None}

    # --- Reporting ---

    def get_usage_report(self, project_id: str) -> Dict[str, Any]:
        usage = self._usage.get(project_id, {})
        budget = self._project_budgets.get(project_id, self.DEFAULT_PROJECT_BUDGET)
        total = sum(usage.values())
        return {
            "project_id": project_id,
            "budget": budget,
            "used": total,
            "remaining": max(0, budget - total),
            "percent_used": round((total / budget) * 100, 1) if budget > 0 else 0,
            "per_agent": dict(usage),
        }

    def get_usage_log(self) -> List[dict]:
        return list(self._usage_log)

    def clear(self):
        self._project_budgets.clear()
        self._agent_budgets.clear()
        self._usage.clear()
        self._usage_log.clear()


# Global instance
token_budget = TokenBudgetManager()
