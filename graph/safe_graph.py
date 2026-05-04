"""
SafeGraph — Production safety mechanisms for LangGraph workflow.

Solves:
  [03] Infinite routing loops — step counter + circuit breaker
  [07] Race conditions — Redis distributed locks
  [02] Deadlock prevention — timeout on parallel agents
"""

import asyncio
import hashlib
import json
import uuid
from typing import Any, Dict, Optional

from state.project_state import ProjectState


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_TOTAL_STEPS = 50           # Hard cap on total node visits
MAX_PHASE_RETRIES = 3          # Max times a single phase can re-run
MAX_CONSECUTIVE_SAME_NODE = 3  # Circuit breaker: same node 3x → force END
DEADLOCK_TIMEOUT_SEC = 120     # Kill parallel agents if stalled
RECURSION_LIMIT = 50           # LangGraph recursion_limit config


# ---------------------------------------------------------------------------
# Step Counter & Circuit Breaker
# ---------------------------------------------------------------------------

class StepTracker:
    """
    Tracks step counts and detects infinite loops.
    Embedded in every node via the safe_node_wrapper.
    """

    def __init__(self):
        self._visit_history: list = []

    def record_visit(self, node_name: str, state: Dict[str, Any]) -> None:
        """Record a node visit."""
        self._visit_history.append(node_name)

    def get_steps_taken(self, state: Dict[str, Any]) -> int:
        """Get total steps from state."""
        return state.get("steps_taken", 0)

    def should_break(self, node_name: str, state: Dict[str, Any]) -> bool:
        """
        Check if the circuit breaker should trigger.
        Returns True if we should force END.
        """
        steps = self.get_steps_taken(state)

        # Hard cap on total steps
        if steps >= MAX_TOTAL_STEPS:
            return True

        # Phase retry cap
        phase = state.get("current_phase", "intake")
        retries = state.get("phase_retries", {})
        if retries.get(phase, 0) >= MAX_PHASE_RETRIES:
            return True

        # Consecutive same-node detection (loop trap)
        if len(self._visit_history) >= MAX_CONSECUTIVE_SAME_NODE:
            recent = self._visit_history[-MAX_CONSECUTIVE_SAME_NODE:]
            if all(n == node_name for n in recent):
                return True

        # State plateau detection — state hash unchanged for 2 iterations
        current_hash = compute_state_hash(state)
        stored_hash = state.get("state_hash", "")
        if current_hash == stored_hash and steps > 0:
            # State hasn't changed — likely stuck
            return True

        return False

    def get_visit_count(self, node_name: str) -> int:
        """How many times has this node been visited?"""
        return self._visit_history.count(node_name)


# Global step tracker
_step_tracker = StepTracker()


def compute_state_hash(state: Dict[str, Any]) -> str:
    """
    Compute a SHA-256 hash of the meaningful state fields.
    Used for plateau detection — if hash doesn't change, we're stuck.
    """
    hashable = {
        "phase": state.get("current_phase", ""),
        "active_tasks": str(state.get("active_tasks", [])),
        "completed_tasks": len(state.get("completed_tasks", [])),
        "blockers": str(state.get("blockers", [])),
        "artifacts_keys": sorted(state.get("artifacts", {}).keys()),
    }
    raw = json.dumps(hashable, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Safe Node Wrapper
# ---------------------------------------------------------------------------

def safe_node_wrapper(node_name: str, node_fn):
    """
    Wraps a LangGraph node function with safety checks.

    Before execution:
      - Check step counter / circuit breaker
      - Increment steps_taken

    After execution:
      - Update state_hash for plateau detection
      - Track phase retries
    """

    def wrapped(state: ProjectState) -> Dict[str, Any]:
        # --- Pre-execution safety checks ---
        if _step_tracker.should_break(node_name, state):
            # Circuit breaker triggered — graceful exit
            return {
                "messages": [{
                    "role": "system",
                    "content": (
                        f"[SafeGraph] Circuit breaker triggered at node '{node_name}'. "
                        f"Steps: {state.get('steps_taken', 0)}, "
                        f"Phase retries: {state.get('phase_retries', {})}. "
                        f"Forcing workflow termination."
                    ),
                }],
                "is_finished": True,
                "blockers": state.get("blockers", []) + [
                    f"SafeGraph: Circuit breaker at {node_name}"
                ],
            }

        # Record visit
        _step_tracker.record_visit(node_name, state)

        # --- Execute the actual node ---
        result = node_fn(state)

        # --- Post-execution updates ---
        steps = state.get("steps_taken", 0) + 1
        result["steps_taken"] = steps
        result["state_hash"] = compute_state_hash({**state, **result})

        # Track phase retries (for fan-in nodes that loop back)
        if node_name.endswith("_fanin"):
            phase = state.get("current_phase", "intake")
            retries = dict(state.get("phase_retries", {}))
            retries[phase] = retries.get(phase, 0) + 1
            result["phase_retries"] = retries

        return result

    wrapped.__name__ = f"safe_{node_name}"
    return wrapped


# ---------------------------------------------------------------------------
# Distributed Lock (Redis-backed)
# ---------------------------------------------------------------------------

class StateLock:
    """
    Redis-backed distributed lock for safe concurrent state writes.
    Uses SET NX PX pattern for atomic lock acquisition.

    Usage:
        lock = StateLock(redis_client)
        async with lock.acquire("project_123"):
            # Critical section — only one agent writes at a time
            state["artifacts"]["prd"] = new_prd
    """

    def __init__(self, redis_client=None, ttl_ms: int = 30_000):
        self._redis = redis_client
        self._ttl_ms = ttl_ms
        self._locks: Dict[str, str] = {}  # Fallback in-memory locks

    class _LockContext:
        def __init__(self, lock: "StateLock", key: str, identifier: str):
            self._lock = lock
            self._key = key
            self._id = identifier

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            await self._lock._release(self._key, self._id)

    async def acquire(self, resource: str, timeout_sec: float = 10.0) -> _LockContext:
        """Acquire a distributed lock on a resource."""
        identifier = str(uuid.uuid4())
        lock_key = f"lock:state:{resource}"

        if self._redis:
            # Redis-backed lock
            deadline = asyncio.get_event_loop().time() + timeout_sec
            while asyncio.get_event_loop().time() < deadline:
                acquired = await self._redis.set(
                    lock_key, identifier, nx=True, px=self._ttl_ms
                )
                if acquired:
                    return self._LockContext(self, lock_key, identifier)
                await asyncio.sleep(0.1)
            raise TimeoutError(
                f"Could not acquire lock on '{resource}' within {timeout_sec}s"
            )
        else:
            # In-memory fallback (development)
            if lock_key not in self._locks:
                self._locks[lock_key] = identifier
                return self._LockContext(self, lock_key, identifier)
            raise TimeoutError(f"Lock '{resource}' already held (in-memory)")

    async def _release(self, key: str, identifier: str) -> None:
        """Release a lock, verifying ownership."""
        if self._redis:
            # Lua script: only delete if we own the lock
            script = """
            if redis.call("get", KEYS[1]) == ARGV[1] then
                return redis.call("del", KEYS[1])
            else
                return 0
            end
            """
            await self._redis.eval(script, 1, key, identifier)
        else:
            if self._locks.get(key) == identifier:
                del self._locks[key]


# ---------------------------------------------------------------------------
# Deadlock Timeout for Parallel Agents
# ---------------------------------------------------------------------------

async def run_with_timeout(coro, timeout: float = DEADLOCK_TIMEOUT_SEC):
    """
    Run a coroutine with a timeout.
    If it exceeds the timeout, cancel and return a blocker message.
    """
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        return {
            "blockers": [
                f"SafeGraph: Agent exceeded {timeout}s deadlock timeout"
            ],
            "messages": [{
                "role": "system",
                "content": f"[SafeGraph] Deadlock timeout ({timeout}s) — agent cancelled.",
            }],
        }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_step_tracker() -> StepTracker:
    """Get the global step tracker."""
    return _step_tracker


def reset_step_tracker() -> None:
    """Reset the step tracker (for tests)."""
    global _step_tracker
    _step_tracker = StepTracker()


def get_recursion_limit() -> int:
    """Get the recursion limit for LangGraph config."""
    return RECURSION_LIMIT
