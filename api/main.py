"""
Enterprise AI Development Lifecycle — FastAPI Application.
"""

import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

load_dotenv()

app = FastAPI(
    title="Enterprise AI Development Lifecycle API",
    description="Backend for managing multi-agent AI development projects.",
    version="0.2.0",
)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class ProjectCreateRequest(BaseModel):
    client_name: str
    raw_brief: str


class ApproveGateRequest(BaseModel):
    gate: str  # "prd_approved" | "architecture_approved" | "deploy_approved"


# ---------------------------------------------------------------------------
# In-memory project store (swap for DB in production)
# ---------------------------------------------------------------------------

projects: dict = {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_initial_state(req: ProjectCreateRequest) -> dict:
    # [28] Sanitize client input before storing
    from agents.guardrail import GuardRail
    sanitized_brief, input_warnings = GuardRail.validate_input(req.raw_brief)

    now = datetime.now(timezone.utc).isoformat()
    return {
        "project_id": str(uuid.uuid4()),
        "client_name": req.client_name,
        "raw_brief": sanitized_brief,
        "current_phase": "intake",
        "requirements": [],
        "active_tasks": [],
        "completed_tasks": [],
        "blockers": [],
        "messages": [],
        "artifacts": {},
        "human_gates": {
            "prd_approved": False,
            "architecture_approved": False,
            "deploy_approved": False,
        },
        "feedback_notes": [],
        "agent_communications": [],
        "created_at": now,
        "updated_at": now,
        "next_step": None,
        "is_finished": False,
        # Safety fields (SafeGraph)
        "steps_taken": 0,
        "phase_retries": {},
        "state_hash": "",
        # Cost tracking
        "token_usage": {"total": 0, "per_agent": {}},
        # GuardRail warnings
        "guardrail_warnings": [w.get("type", "") for w in input_warnings],
    }



# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/")
async def health_check():
    return {
        "status": "healthy",
        "version": "0.2.0",
        "environment": os.getenv("APP_ENV", "development"),
    }


@app.post("/projects")
async def create_project(req: ProjectCreateRequest):
    """Create a new project and return its initial state."""
    state = _make_initial_state(req)
    project_id = state["project_id"]
    projects[project_id] = state
    return {"project_id": project_id, "status": "created", "phase": "intake"}


@app.get("/projects/{project_id}")
async def get_project(project_id: str):
    """Get the current state of a project."""
    if project_id not in projects:
        raise HTTPException(status_code=404, detail="Project not found")
    return projects[project_id]


@app.get("/projects/{project_id}/status")
async def get_project_status(project_id: str):
    """Get a lightweight status summary."""
    if project_id not in projects:
        raise HTTPException(status_code=404, detail="Project not found")
    state = projects[project_id]
    return {
        "project_id": project_id,
        "phase": state["current_phase"],
        "active_tasks": len(state["active_tasks"]),
        "completed_tasks": len(state["completed_tasks"]),
        "blockers": state["blockers"],
        "is_finished": state["is_finished"],
        "human_gates": state["human_gates"],
    }


@app.post("/projects/{project_id}/run")
async def run_project(project_id: str):
    """Trigger the LangGraph workflow for this project."""
    if project_id not in projects:
        raise HTTPException(status_code=404, detail="Project not found")

    state = projects[project_id]

    # Import here to avoid circular imports at module level
    from graph.workflow import app as workflow_app

    try:
        result = workflow_app.invoke(state)
        # Update stored state with result
        projects[project_id] = result
        return {
            "project_id": project_id,
            "phase": result.get("current_phase"),
            "is_finished": result.get("is_finished", False),
            "message": "Workflow execution completed.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Workflow error: {str(e)}")


@app.post("/projects/{project_id}/approve")
async def approve_gate(project_id: str, req: ApproveGateRequest):
    """Approve a human gate for the project."""
    if project_id not in projects:
        raise HTTPException(status_code=404, detail="Project not found")

    valid_gates = ["prd_approved", "architecture_approved", "deploy_approved"]
    if req.gate not in valid_gates:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid gate. Must be one of: {valid_gates}",
        )

    projects[project_id]["human_gates"][req.gate] = True
    projects[project_id]["updated_at"] = datetime.now(timezone.utc).isoformat()

    return {
        "project_id": project_id,
        "gate": req.gate,
        "approved": True,
        "human_gates": projects[project_id]["human_gates"],
    }


# ---------------------------------------------------------------------------
# WebSockets
# ---------------------------------------------------------------------------

from fastapi import WebSocket, WebSocketDisconnect
from api.websocket import ws_manager

@app.websocket("/ws/{project_id}")
async def websocket_endpoint(websocket: WebSocket, project_id: str):
    """WebSocket connection for real-time dashboard updates."""
    await ws_manager.connect(websocket, project_id)
    try:
        while True:
            # Wait for message from the Human (Dashboard Chat)
            data = await websocket.receive_text()
            
            if project_id in projects:
                # 1. Update Project State with the feedback/query
                now = datetime.now(timezone.utc).isoformat()
                msg_id = str(uuid.uuid4())
                
                # Add to feedback notes for agents to read
                projects[project_id]["feedback_notes"].append({
                    "id": msg_id,
                    "from": "human",
                    "content": data,
                    "timestamp": now
                })
                
                # 2. Broadcast the message to all clients so it appears in the chat UI
                from api.events import EventEmitter
                await EventEmitter.emit_message_bus_event(project_id, {
                    "id": msg_id,
                    "from_agent": "Human",
                    "to_agent": "System",
                    "type": "user_chat",
                    "content": data,
                    "timestamp": now
                })
                
                logger.info(f"Received human feedback for project {project_id}: {data}")

    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, project_id)


# ---------------------------------------------------------------------------
# API Key Management
# ---------------------------------------------------------------------------

class ApiKeysRequest(BaseModel):
    anthropic: Optional[str] = None
    openai: Optional[str] = None
    gemini: Optional[str] = None
    nvidia: Optional[str] = None
    openrouter: Optional[str] = None
    tavily: Optional[str] = None

@app.post("/settings/keys")
async def update_api_keys(req: ApiKeysRequest):
    """
    [55] Update API keys dynamically.
    Updates the environment variables in the current process memory.
    """
    if req.anthropic: os.environ["ANTHROPIC_API_KEY"] = req.anthropic
    if req.openai:    os.environ["OPENAI_API_KEY"] = req.openai
    if req.gemini:    os.environ["GEMINI_API_KEY"] = req.gemini
    if req.nvidia:    os.environ["NVIDIA_API_KEY"] = req.nvidia
    if req.openrouter: os.environ["OPENROUTER_API_KEY"] = req.openrouter
    if req.tavily:    os.environ["TAVILY_API_KEY"] = req.tavily
    
    logger.info("API keys updated via Dashboard Settings panel.")
    return {"status": "success", "message": "API keys updated in memory."}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("API_PORT", 8000)))
