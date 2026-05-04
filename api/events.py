"""
Event Emitter for real-time dashboard updates.

Allows any module to broadcast events to the React frontend.
"""

import asyncio
from typing import Any, Dict
from datetime import datetime, timezone
from .websocket import ws_manager


class EventEmitter:
    """
    Standardized event emission for the dashboard.
    """

    @staticmethod
    def _create_payload(event_type: str, data: Dict[str, Any]) -> dict:
        return {
            "type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data
        }

    @classmethod
    async def emit_agent_state(cls, project_id: str, agent_name: str, state: str, details: str = ""):
        """state: thinking, acting, blocked, finished"""
        payload = cls._create_payload("agent_state_changed", {
            "agent": agent_name,
            "state": state,
            "details": details
        })
        await ws_manager.broadcast_to_project(project_id, payload)

    @classmethod
    async def emit_thinking_chunk(cls, project_id: str, agent_name: str, chunk: str):
        """For streaming the chain-of-thought live."""
        payload = cls._create_payload("agent_thinking", {
            "agent": agent_name,
            "chunk": chunk
        })
        await ws_manager.broadcast_to_project(project_id, payload)

    @classmethod
    async def emit_message_bus_event(cls, project_id: str, msg: dict):
        """When an inter-agent message is sent/received."""
        payload = cls._create_payload("message_bus_event", msg)
        await ws_manager.broadcast_to_project(project_id, payload)

    @classmethod
    async def emit_tool_usage(cls, project_id: str, agent_name: str, tool_name: str, args: dict):
        """When an agent calls a tool or MCP server."""
        payload = cls._create_payload("tool_usage", {
            "agent": agent_name,
            "tool": tool_name,
            "args": args
        })
        await ws_manager.broadcast_to_project(project_id, payload)

    @classmethod
    async def emit_budget_update(cls, project_id: str, usage_report: dict):
        """Real-time token cost updates."""
        payload = cls._create_payload("budget_update", usage_report)
        await ws_manager.broadcast_to_project(project_id, payload)

    @classmethod
    async def emit_human_gate_pending(cls, project_id: str, gate_name: str, artifact: dict):
        """Requires human approval from dashboard."""
        payload = cls._create_payload("human_gate_pending", {
            "gate_name": gate_name,
            "artifact": artifact
        })
        await ws_manager.broadcast_to_project(project_id, payload)


# Global instance not needed, using classmethods
