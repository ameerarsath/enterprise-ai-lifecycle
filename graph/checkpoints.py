"""
Checkpoint configuration for persisting LangGraph state across runs.

Solves: 
  [41] State persistence failures — PostgresSaver with connection pooling
  [45] Multi-tenant isolation — Thread scoped isolation
"""

import os
from dotenv import load_dotenv

load_dotenv()


class CheckpointManager:
    """Singleton to hold the DB connection pool."""
    _instance = None
    _saver = None

    @classmethod
    def get_saver(cls):
        if cls._saver is not None:
            return cls._saver

        db_url = os.getenv("DATABASE_URL", "")

        if db_url.startswith("postgresql"):
            try:
                import psycopg_pool
                from langgraph.checkpoint.postgres import PostgresSaver

                # [41] Connection pooling for high concurrency
                pool = psycopg_pool.ConnectionPool(
                    conninfo=db_url,
                    max_size=20,
                    kwargs={"autocommit": True}
                )
                
                cls._saver = PostgresSaver(pool)
                cls._saver.setup()
                return cls._saver
            except ImportError:
                print("Warning: psycopg_pool or langgraph-checkpoint-postgres not installed.")

        # Default fallback
        from langgraph.checkpoint.memory import MemorySaver
        cls._saver = MemorySaver()
        return cls._saver


def get_checkpointer():
    """Return a production-ready LangGraph checkpointer."""
    return CheckpointManager.get_saver()

def get_thread_config(project_id: str, phase: str, agent_name: str) -> dict:
    """
    [45] Multi-tenant isolation.
    Ensures state checkpoints are strictly scoped to the exact project,
    phase, and agent running them.
    """
    return {
        "configurable": {
            "thread_id": f"{project_id}:{phase}:{agent_name}"
        }
    }
