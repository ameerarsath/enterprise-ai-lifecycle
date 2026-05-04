"""
MessageBus — Lossless inter-agent communication via Redis Streams.

Solves: [01] Context bleed · [06] Orchestrator overload · [07] Race conditions
"""

import json
import logging
from typing import Any, Dict, List, Optional
import uuid

# In a real app, use redis.asyncio
# We use a mock here that simulates the Redis Streams API behavior
# to keep the codebase runnable without a live Redis instance during dev.

logger = logging.getLogger(__name__)


class AgentMessage:
    def __init__(self, msg_id: str, project_id: str, from_agent: str, 
                 to_agent: str, msg_type: str, content: str, 
                 context: Dict[str, Any], priority: int):
        self.id = msg_id
        self.project_id = project_id
        self.from_agent = from_agent
        self.to_agent = to_agent
        self.type = msg_type
        self.content = content
        self.context = context
        self.priority = priority
        self.status = "pending"  # pending, delivered, acked, failed

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "type": self.type,
            "content": self.content,
            "context": self.context,
            "priority": self.priority,
            "status": self.status,
        }


class MessageBus:
    """
    Reliable inter-agent message delivery.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            # stream_key -> list of messages
            cls._streams: Dict[str, List[AgentMessage]] = {}
            # Dead letter queue
            cls._dlq: List[AgentMessage] = []
        return cls._instance

    def _get_stream_key(self, project_id: str, agent_name: str) -> str:
        return f"stream:{project_id}:{agent_name}"

    async def send(
        self,
        project_id: str,
        from_agent: str,
        to_agent: str,
        msg_type: str,
        content: str,
        context: Optional[Dict[str, Any]] = None,
        priority: int = 1,
    ) -> str:
        """
        Send a message to an agent's stream.
        """
        msg_id = str(uuid.uuid4())
        msg = AgentMessage(
            msg_id=msg_id,
            project_id=project_id,
            from_agent=from_agent,
            to_agent=to_agent,
            msg_type=msg_type,
            content=content,
            context=context or {},
            priority=priority,
        )

        stream_key = self._get_stream_key(project_id, to_agent)
        if stream_key not in self._streams:
            self._streams[stream_key] = []
        
        self._streams[stream_key].append(msg)
        
        # Sort by priority (higher number = higher priority)
        self._streams[stream_key].sort(key=lambda m: m.priority, reverse=True)

        logger.debug(f"Message sent: {from_agent} -> {to_agent} [{msg_id}]")
        return msg_id

    async def receive(
        self, project_id: str, agent_name: str, count: int = 5
    ) -> List[AgentMessage]:
        """
        Receive pending messages for an agent.
        [06] Limits batch size to prevent context overload.
        """
        stream_key = self._get_stream_key(project_id, agent_name)
        stream = self._streams.get(stream_key, [])
        
        results = []
        for msg in stream:
            if msg.status == "pending":
                msg.status = "delivered"
                results.append(msg)
                if len(results) >= count:
                    break
        
        return results

    async def acknowledge(self, project_id: str, agent_name: str, message_id: str) -> bool:
        """
        Acknowledge a message as processed.
        """
        stream_key = self._get_stream_key(project_id, agent_name)
        stream = self._streams.get(stream_key, [])
        
        for msg in stream:
            if msg.id == message_id:
                msg.status = "acked"
                return True
        return False

    async def fail_message(self, project_id: str, agent_name: str, message_id: str) -> None:
        """
        Mark a message as failed. Moves it to the DLQ.
        """
        stream_key = self._get_stream_key(project_id, agent_name)
        stream = self._streams.get(stream_key, [])
        
        for msg in stream:
            if msg.id == message_id:
                msg.status = "failed"
                self._dlq.append(msg)
                stream.remove(msg)
                break

    async def get_dead_letters(self) -> List[dict]:
        return [m.to_dict() for m in self._dlq]

    async def get_full_log(self, project_id: str) -> List[dict]:
        """Get all messages for a project (for dashboard)."""
        all_msgs = []
        for key, stream in self._streams.items():
            if key.startswith(f"stream:{project_id}:"):
                all_msgs.extend([m.to_dict() for m in stream])
        return all_msgs

    def clear(self):
        self._streams.clear()
        self._dlq.clear()


# Global instance
message_bus = MessageBus()
