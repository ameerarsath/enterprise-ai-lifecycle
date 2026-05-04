"""
Vector Store — Cold Memory (PostgreSQL + pgvector).

Solves: [08] Context limit · [10] Retrieval mismatch · [11] Stale memory · [12] Failure memory
"""

import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import json


class FailureMemory:
    """
    Dedicated memory for agent failures [12].
    Prevents agents from repeating the same mistakes across sessions.
    """
    
    def __init__(self):
        # Mock DB
        self._failures: Dict[str, dict] = {}
        
    def _hash(self, agent_name: str, context: str) -> str:
        # We hash the context structure, not exact text, to catch similar situations
        # For this mock, we just hash the first 100 chars
        key_content = f"{agent_name}:{context[:100]}"
        return hashlib.sha256(key_content.encode()).hexdigest()

    def record_failure(self, project_id: str, agent_name: str, 
                      context: str, error: str, root_cause: Optional[str] = None):
        h = self._hash(agent_name, context)
        self._failures[h] = {
            "project_id": project_id,
            "agent_name": agent_name,
            "error": error,
            "root_cause": root_cause or error,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    def check_known_failure(self, agent_name: str, context: str) -> Optional[dict]:
        h = self._hash(agent_name, context)
        return self._failures.get(h)


class VectorStore:
    """
    Semantic memory backed by pgvector.
    """

    def __init__(self):
        # Mock embeddings DB
        self._embeddings: List[dict] = []
        self.failures = FailureMemory()

    async def save_knowledge(
        self, project_id: str, agent_name: str, phase: str,
        content: str, category: str
    ):
        """Save a summarized piece of knowledge."""
        # [11] Stale memory prevention: Mark old entries in same category as superseded
        for e in self._embeddings:
            if (e["project_id"] == project_id and 
                e["category"] == category and 
                not e["superseded"]):
                e["superseded"] = True
                
        self._embeddings.append({
            "project_id": project_id,
            "agent_name": agent_name,
            "phase": phase,
            "content": content,
            "category": category,
            "superseded": False,  # [11]
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

    async def retrieve(
        self, project_id: str, query: str, limit: int = 3
    ) -> List[str]:
        """
        Semantic search (mocked).
        [10] Version-aware retrieval: only returns non-superseded facts.
        """
        results = []
        for e in self._embeddings:
            if e["project_id"] == project_id and not e["superseded"]:
                results.append(f"[{e['category'].upper()}] {e['content']}")
                
        # In a real app, this would do a cosine similarity search
        # on the embeddings using pgvector.
        return results[-limit:]

    def clear(self):
        self._embeddings.clear()
        self.failures._failures.clear()


# Global instance
vector_store = VectorStore()
