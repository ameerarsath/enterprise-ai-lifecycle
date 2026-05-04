"""
Session Store — Hot Memory (Redis).

Solves: [09] Memory fragmentation across sessions
"""

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class SessionStore:
    """
    Manages active session memory for agents using Redis.
    Data is persisted across container restarts (AOF).
    TTL ensures it auto-clears after a sprint ends.
    """

    def __init__(self, redis_client=None, ttl_sec: int = 86400):
        self._redis = redis_client
        self._ttl_sec = ttl_sec
        # In-memory fallback
        self._data: Dict[str, List[dict]] = {}

    def _get_key(self, project_id: str, agent_name: str) -> str:
        return f"session:{project_id}:{agent_name}"

    async def save_interaction(
        self, project_id: str, agent_name: str, 
        input_context: str, thinking: dict, output: dict
    ):
        """Save a single agent run to hot memory."""
        key = self._get_key(project_id, agent_name)
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "thinking": thinking,
            "output_summary": str(output)[:1000]  # Store summary to save space
        }
        
        if self._redis:
            # Append to redis list and set TTL
            await self._redis.rpush(key, json.dumps(record))
            await self._redis.expire(key, self._ttl_sec)
        else:
            if key not in self._data:
                self._data[key] = []
            self._data[key].append(record)
            # Keep only last 5 interactions to prevent unbounded growth
            if len(self._data[key]) > 5:
                self._data[key].pop(0)

    async def get_recent_memory(
        self, project_id: str, agent_name: str, limit: int = 3
    ) -> List[dict]:
        """Get the most recent interactions for this agent."""
        key = self._get_key(project_id, agent_name)
        
        if self._redis:
            # LTRIM to ensure we don't hold too much
            await self._redis.ltrim(key, -limit, -1)
            raw = await self._redis.lrange(key, 0, -1)
            return [json.loads(r) for r in raw]
        else:
            return self._data.get(key, [])[-limit:]

    async def clear(self, project_id: str, agent_name: str):
        key = self._get_key(project_id, agent_name)
        if self._redis:
            await self._redis.delete(key)
        else:
            if key in self._data:
                del self._data[key]


# Global instance
session_store = SessionStore()
