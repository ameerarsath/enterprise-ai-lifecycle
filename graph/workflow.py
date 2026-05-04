"""
LangGraph workflow — full 4-phase multi-agent pipeline with SafeGraph.

Flow:
  Client Brief → Orchestrator → Manager
    ├── Phase 1 — Discovery:  [Business Analyst, Scrum Master, SEO]  (parallel)
    ├── Phase 2 — Build:      [Frontend, Backend, DB]                (parallel)
    ├── Phase 3 — Assurance:  [QA, Security]                         (parallel)
    └── Phase 4 — Deploy:     [Deploy + Monitor]
                                  ↓
                         (feedback loop → Orchestrator)

Safety: All nodes wrapped with SafeGraph circuit breaker.
"""

from typing import Literal
from langgraph.graph import StateGraph, END

from state.project_state import ProjectState
from graph.safe_graph import safe_node_wrapper, get_recursion_limit

# -- Agent node functions --
from agents.orchestrator import orchestrator_node
from agents.manager import manager_node
from agents.business_analyst import business_analyst_node
from agents.scrum_master import scrum_master_node
from agents.seo import seo_node
from agents.frontend import frontend_node
from agents.backend import backend_node
from agents.database import database_node
from agents.qa import qa_node
from agents.security import security_node
from agents.deploy import deploy_node


# ---------------------------------------------------------------------------
# Phase fan-out / fan-in nodes
# ---------------------------------------------------------------------------

def discovery_fanout(state: ProjectState) -> dict:
    return {"current_phase": "discovery"}

def discovery_fanin(state: ProjectState) -> dict:
    return {"current_phase": "discovery"}

def build_fanout(state: ProjectState) -> dict:
    return {"current_phase": "build"}

def build_fanin(state: ProjectState) -> dict:
    return {"current_phase": "build"}

def assurance_fanout(state: ProjectState) -> dict:
    return {"current_phase": "assurance"}

def assurance_fanin(state: ProjectState) -> dict:
    return {"current_phase": "assurance"}


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

def after_manager_router(
    state: ProjectState,
) -> Literal["discovery_fanout", "build_fanout", "assurance_fanout", "deploy", "__end__"]:
    """Route from Manager to the correct phase."""
    # [03] Check if circuit breaker should end the workflow
    if state.get("is_finished", False):
        return END

    phase = state.get("current_phase", "intake")
    if phase in ("intake", "discovery"):
        return "discovery_fanout"
    elif phase == "build":
        return "build_fanout"
    elif phase == "assurance":
        return "assurance_fanout"
    elif phase == "deploy":
        return "deploy"
    return END


def after_deploy_router(
    state: ProjectState,
) -> Literal["orchestrator", "__end__"]:
    """
    After deploy:
      - If finished (or circuit breaker) → END
      - If feedback_notes exist → loop back (max retries enforced by SafeGraph)
    """
    if state.get("is_finished", False):
        return END

    # [03] Check phase retries — prevent infinite feedback loops
    retries = state.get("phase_retries", {})
    if retries.get("deploy", 0) >= 3:
        return END

    feedback = state.get("feedback_notes", [])
    if feedback:
        return "orchestrator"
    return END


# ---------------------------------------------------------------------------
# Build the graph (with SafeGraph wrapping)
# ---------------------------------------------------------------------------

def build_workflow() -> StateGraph:
    """Construct and return the compiled LangGraph workflow."""

    workflow = StateGraph(ProjectState)

    # ---- Wrap all agent nodes with SafeGraph ----
    workflow.add_node("orchestrator", safe_node_wrapper("orchestrator", orchestrator_node))
    workflow.add_node("manager", safe_node_wrapper("manager", manager_node))

    # Discovery phase
    workflow.add_node("discovery_fanout", discovery_fanout)
    workflow.add_node("business_analyst", safe_node_wrapper("business_analyst", business_analyst_node))
    workflow.add_node("scrum_master", safe_node_wrapper("scrum_master", scrum_master_node))
    workflow.add_node("seo", safe_node_wrapper("seo", seo_node))
    workflow.add_node("discovery_fanin", discovery_fanin)

    # Build phase
    workflow.add_node("build_fanout", build_fanout)
    workflow.add_node("frontend", safe_node_wrapper("frontend", frontend_node))
    workflow.add_node("backend", safe_node_wrapper("backend", backend_node))
    workflow.add_node("database", safe_node_wrapper("database", database_node))
    workflow.add_node("build_fanin", build_fanin)

    # Assurance phase
    workflow.add_node("assurance_fanout", assurance_fanout)
    workflow.add_node("qa", safe_node_wrapper("qa", qa_node))
    workflow.add_node("security", safe_node_wrapper("security", security_node))
    workflow.add_node("assurance_fanin", assurance_fanin)

    # Deploy
    workflow.add_node("deploy", safe_node_wrapper("deploy", deploy_node))

    # ---- Entry point ----
    workflow.set_entry_point("orchestrator")

    # ---- Edges ----
    workflow.add_edge("orchestrator", "manager")
    workflow.add_conditional_edges("manager", after_manager_router)

    # Discovery fan-out → parallel → fan-in
    workflow.add_edge("discovery_fanout", "business_analyst")
    workflow.add_edge("discovery_fanout", "scrum_master")
    workflow.add_edge("discovery_fanout", "seo")
    workflow.add_edge("business_analyst", "discovery_fanin")
    workflow.add_edge("scrum_master", "discovery_fanin")
    workflow.add_edge("seo", "discovery_fanin")
    workflow.add_edge("discovery_fanin", "orchestrator")

    # Build fan-out → parallel → fan-in
    workflow.add_edge("build_fanout", "frontend")
    workflow.add_edge("build_fanout", "backend")
    workflow.add_edge("build_fanout", "database")
    workflow.add_edge("frontend", "build_fanin")
    workflow.add_edge("backend", "build_fanin")
    workflow.add_edge("database", "build_fanin")
    workflow.add_edge("build_fanin", "orchestrator")

    # Assurance fan-out → parallel → fan-in
    workflow.add_edge("assurance_fanout", "qa")
    workflow.add_edge("assurance_fanout", "security")
    workflow.add_edge("qa", "assurance_fanin")
    workflow.add_edge("security", "assurance_fanin")
    workflow.add_edge("assurance_fanin", "orchestrator")

    # Deploy → feedback loop or END
    workflow.add_conditional_edges("deploy", after_deploy_router)

    return workflow


# Build and compile with recursion limit
workflow = build_workflow()
app = workflow.compile()
