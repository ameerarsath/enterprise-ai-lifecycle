"""
AuditLogger — Structured decision logging for every agent action.

Solves: [40] No audit trail · [51] Non-deterministic failures · [52] No error ownership · [53] Trace overload · [54] Silent truncation
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class AuditEntry:
    """A single audit log entry for one agent action."""

    def __init__(
        self,
        project_id: str,
        agent_name: str,
        phase: str,
        action_type: str,
        input_context: str,
        thinking: Optional[str],
        output: str,
        tools_used: List[str],
        agents_consulted: List[str],
        token_usage: Dict[str, int],
        duration_ms: int,
        success: bool,
        error: Optional[str] = None,
        truncation_detected: bool = False,
    ):
        self.id = f"{project_id}:{agent_name}:{datetime.now(timezone.utc).timestamp()}"
        self.project_id = project_id
        self.agent_name = agent_name
        self.phase = phase
        self.action_type = action_type
        self.input_context = input_context
        self.thinking = thinking
        self.output = output
        self.tools_used = tools_used
        self.agents_consulted = agents_consulted
        self.token_usage = token_usage
        self.duration_ms = duration_ms
        self.success = success
        self.error = error
        self.truncation_detected = truncation_detected
        self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "agent_name": self.agent_name,
            "phase": self.phase,
            "action_type": self.action_type,
            "input_summary": self.input_context[:500],
            "thinking_summary": (self.thinking or "")[:500],
            "output_summary": self.output[:500],
            "tools_used": self.tools_used,
            "agents_consulted": self.agents_consulted,
            "token_usage": self.token_usage,
            "duration_ms": self.duration_ms,
            "success": self.success,
            "error": self.error,
            "truncation_detected": self.truncation_detected,
            "timestamp": self.timestamp,
        }


class AuditLogger:
    """
    Central audit logger for full decision trail.

    [40] Every agent decision is logged with reasoning
    [51] Full input/output captured for failure replay
    [52] Error ownership — trace which agent caused downstream failures
    [53] Structured, filterable logs (not raw LangSmith traces)
    [54] Truncation detection on LLM outputs
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._entries: List[AuditEntry] = []
            cls._error_chain: Dict[str, List[str]] = {}
        return cls._instance

    def log(
        self,
        project_id: str,
        agent_name: str,
        phase: str,
        action_type: str = "run",
        input_context: str = "",
        thinking: Optional[str] = None,
        output: str = "",
        tools_used: Optional[List[str]] = None,
        agents_consulted: Optional[List[str]] = None,
        token_usage: Optional[Dict[str, int]] = None,
        duration_ms: int = 0,
        success: bool = True,
        error: Optional[str] = None,
        truncation_detected: bool = False,
    ) -> AuditEntry:
        """Log a single agent action."""
        entry = AuditEntry(
            project_id=project_id,
            agent_name=agent_name,
            phase=phase,
            action_type=action_type,
            input_context=input_context,
            thinking=thinking,
            output=output,
            tools_used=tools_used or [],
            agents_consulted=agents_consulted or [],
            token_usage=token_usage or {"input": 0, "output": 0},
            duration_ms=duration_ms,
            success=success,
            error=error,
            truncation_detected=truncation_detected,
        )
        self._entries.append(entry)

        # Track error chains for ownership [52]
        if error:
            chain_key = f"{project_id}:{phase}"
            if chain_key not in self._error_chain:
                self._error_chain[chain_key] = []
            self._error_chain[chain_key].append(agent_name)

        return entry

    # --- Query Methods ---

    def get_entries(self, project_id: str,
                    agent_name: Optional[str] = None,
                    phase: Optional[str] = None,
                    success_only: Optional[bool] = None) -> List[dict]:
        """Filter audit entries."""
        results = []
        for e in self._entries:
            if e.project_id != project_id:
                continue
            if agent_name and e.agent_name != agent_name:
                continue
            if phase and e.phase != phase:
                continue
            if success_only is not None and e.success != success_only:
                continue
            results.append(e.to_dict())
        return results

    def get_failures(self, project_id: str) -> List[dict]:
        """Get all failed actions for a project."""
        return self.get_entries(project_id, success_only=False)

    # --- Error Ownership [52] ---

    def trace_error_origin(self, project_id: str, phase: str) -> List[str]:
        """
        Trace which agents caused errors in a given phase.
        Returns the chain of agents that errored, in order.
        """
        chain_key = f"{project_id}:{phase}"
        return self._error_chain.get(chain_key, [])

    # --- Decision Report [40] ---

    def generate_decision_report(self, project_id: str) -> str:
        """
        Generate a human-readable report of all decisions made.
        Used to answer "why was this architecture chosen?" questions.
        """
        entries = self.get_entries(project_id)
        if not entries:
            return "No audit entries found for this project."

        lines = [f"# Decision Report — Project {project_id}\n"]
        current_phase = ""

        for entry in entries:
            if entry["phase"] != current_phase:
                current_phase = entry["phase"]
                lines.append(f"\n## Phase: {current_phase.upper()}\n")

            status = "✅" if entry["success"] else "❌"
            lines.append(f"### {status} {entry['agent_name']} — {entry['action_type']}")
            if entry["thinking_summary"]:
                lines.append(f"**Reasoning:** {entry['thinking_summary']}")
            lines.append(f"**Output:** {entry['output_summary']}")
            if entry["tools_used"]:
                lines.append(f"**Tools used:** {', '.join(entry['tools_used'])}")
            if entry["agents_consulted"]:
                lines.append(f"**Consulted:** {', '.join(entry['agents_consulted'])}")
            if entry["error"]:
                lines.append(f"**Error:** {entry['error']}")
            lines.append(f"**Tokens:** {entry['token_usage']} | **Duration:** {entry['duration_ms']}ms")
            lines.append("")

        return "\n".join(lines)

    # --- Failure Replay [51] ---

    def get_replay_data(self, audit_id: str) -> Optional[dict]:
        """Get full input/output for reproducing a failure."""
        for entry in self._entries:
            if entry.id == audit_id:
                return {
                    "id": entry.id,
                    "agent": entry.agent_name,
                    "full_input": entry.input_context,
                    "full_thinking": entry.thinking,
                    "full_output": entry.output,
                    "error": entry.error,
                    "timestamp": entry.timestamp,
                }
        return None

    # --- Truncation Detection [54] ---

    @staticmethod
    def detect_truncation(output: str) -> bool:
        """Check if an LLM output appears to have been truncated."""
        if not output:
            return False
        # Common truncation indicators
        indicators = [
            output.endswith("..."),
            output.endswith("…"),
            output.rstrip().endswith(",") and "{" in output,  # Truncated JSON
            output.count("{") != output.count("}"),  # Unbalanced braces
            output.count("[") != output.count("]"),  # Unbalanced brackets
            output.rstrip()[-1:] in ("\\", "/") if output.rstrip() else False,
        ]
        return any(indicators)

    # --- Stats ---

    def get_stats(self, project_id: str) -> dict:
        entries = [e for e in self._entries if e.project_id == project_id]
        total = len(entries)
        failures = sum(1 for e in entries if not e.success)
        total_tokens = sum(
            e.token_usage.get("input", 0) + e.token_usage.get("output", 0)
            for e in entries
        )
        total_duration = sum(e.duration_ms for e in entries)
        truncations = sum(1 for e in entries if e.truncation_detected)
        return {
            "total_actions": total,
            "failures": failures,
            "success_rate": round((total - failures) / total * 100, 1) if total > 0 else 0,
            "total_tokens": total_tokens,
            "total_duration_ms": total_duration,
            "truncations_detected": truncations,
        }

    def clear(self):
        self._entries.clear()
        self._error_chain.clear()


# Global instance
audit_logger = AuditLogger()
