"""
Base agent class and LLM provider factory for the multi-agent system.
Each agent can be configured to use a different LLM provider/model.
Includes inter-agent communication via AgentRegistry.
"""

import os
import asyncio
import json
import logging
from .model_wrapper import model_wrapper
from .guardrail import GuardRail
from .token_budget import token_budget
from .message_bus import message_bus
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# LLM Factory
# ---------------------------------------------------------------------------

def get_llm(
    provider: str = "anthropic",
    model: Optional[str] = None,
    temperature: float = 0.3,
):
    """
    Return a LangChain chat model for the given provider.

    Supported providers:
        - "anthropic"  → ChatAnthropic  (default model: claude-sonnet-4-20250514)
        - "openai"     → ChatOpenAI     (default model: gpt-4o)
        - "google"     → ChatGoogleGenerativeAI (default model: gemini-2.0-flash)
    """
    provider = provider.lower()

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=model or "claude-sonnet-4-20250514",
            temperature=temperature,
            api_key=os.getenv("ANTHROPIC_API_KEY"),
        )

    elif provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model or "gpt-4o",
            temperature=temperature,
            api_key=os.getenv("OPENAI_API_KEY"),
        )

    elif provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=model or "gemini-2.0-flash",
            temperature=temperature,
            google_api_key=os.getenv("GOOGLE_API_KEY"),
        )

    elif provider == "nvidia":
        # [NEW] Enterprise Nvidia NIM support
        from langchain_nvidia_ai_endpoints import ChatNVIDIA
        return ChatNVIDIA(
            model=model or "nvidia/llama-3.1-405b-instruct",
            temperature=temperature,
            api_key=os.getenv("NVIDIA_API_KEY")
        )

    elif provider == "openrouter":
        # [NEW] Multi-model aggregator support
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=model or "anthropic/claude-3.5-sonnet",
            temperature=temperature,
            openai_api_key=os.getenv("OPENROUTER_API_KEY"),
            openai_api_base="https://openrouter.ai/api/v1"
        )

    else:
        raise ValueError(
            f"Unsupported LLM provider: '{provider}'. "
            "Choose from: anthropic, openai, google, nvidia, openrouter"
        )


# ---------------------------------------------------------------------------
# Agent Configuration Registry
# ---------------------------------------------------------------------------

# Maps agent_name -> (provider, model).
# Users update this dict or set env vars like ORCHESTRATOR_LLM_PROVIDER.
AGENT_LLM_CONFIG: Dict[str, Dict[str, str]] = {
    "orchestrator":      {"provider": "anthropic", "model": "claude-sonnet-4-20250514"},
    "manager":           {"provider": "anthropic", "model": "claude-sonnet-4-20250514"},
    "business_analyst":  {"provider": "anthropic", "model": "claude-sonnet-4-20250514"},
    "scrum_master":      {"provider": "anthropic", "model": "claude-sonnet-4-20250514"},
    "seo":               {"provider": "anthropic", "model": "claude-sonnet-4-20250514"},
    "frontend":          {"provider": "anthropic", "model": "claude-sonnet-4-20250514"},
    "backend":           {"provider": "anthropic", "model": "claude-sonnet-4-20250514"},
    "database":          {"provider": "anthropic", "model": "claude-sonnet-4-20250514"},
    "qa":                {"provider": "anthropic", "model": "claude-sonnet-4-20250514"},
    "security":          {"provider": "anthropic", "model": "claude-sonnet-4-20250514"},
    "deploy":            {"provider": "anthropic", "model": "claude-sonnet-4-20250514"},
}


def get_agent_llm(agent_name: str, temperature: float = 0.3):
    """Get the configured LLM for a specific agent."""
    # Check for env-var overrides first:
    #   e.g. ORCHESTRATOR_LLM_PROVIDER=openai, ORCHESTRATOR_LLM_MODEL=gpt-4o
    env_prefix = agent_name.upper()
    provider = os.getenv(f"{env_prefix}_LLM_PROVIDER")
    model = os.getenv(f"{env_prefix}_LLM_MODEL")

    if not provider:
        config = AGENT_LLM_CONFIG.get(agent_name, {})
        provider = config.get("provider", "anthropic")
        model = model or config.get("model")

    return get_llm(provider=provider, model=model, temperature=temperature)


# ---------------------------------------------------------------------------
# Inter-Agent Communication
# ---------------------------------------------------------------------------

class AgentMessage:
    """A message sent between agents."""

    def __init__(
        self,
        from_agent: str,
        to_agent: str,
        message_type: str,
        content: str,
        context: Optional[Dict[str, Any]] = None,
    ):
        self.from_agent = from_agent
        self.to_agent = to_agent
        self.message_type = message_type  # "request" | "response" | "notify"
        self.content = content
        self.context = context or {}
        self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "type": self.message_type,
            "content": self.content,
            "context": self.context,
            "timestamp": self.timestamp,
        }


class AgentRegistry:
    """
    Singleton registry that allows agents to discover and communicate
    with each other at runtime.

    Usage from any agent:
        response = self.ask_agent("backend", "What auth strategy are you using?")
        self.notify_agent("orchestrator", "Found a blocker: missing API spec")
    """

    _instance = None
    _agents: Dict[str, "BaseAgent"] = {}
    _message_log: List[Dict[str, Any]] = []

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._agents = {}
            cls._message_log = []
        return cls._instance

    def register(self, agent: "BaseAgent") -> None:
        """Register an agent so others can find it."""
        self._agents[agent.name] = agent

    def get_agent(self, name: str) -> Optional["BaseAgent"]:
        """Look up a registered agent by name."""
        return self._agents.get(name)

    def list_agents(self) -> List[str]:
        """Return names of all registered agents."""
        return list(self._agents.keys())

    def send_message(self, msg: AgentMessage) -> Optional[str]:
        """
        Route a message to the target agent.
        - "request"  → invokes the target agent's handle_request() and returns
                        the response.
        - "notify"   → fire-and-forget; the target logs the notification.
        """
        self._message_log.append(msg.to_dict())

        target = self.get_agent(msg.to_agent)
        if target is None:
            return f"[ERROR] Agent '{msg.to_agent}' not found in registry."

        if msg.message_type == "request":
            return target.handle_request(
                from_agent=msg.from_agent,
                query=msg.content,
                context=msg.context,
            )
        elif msg.message_type == "notify":
            target.handle_notification(
                from_agent=msg.from_agent,
                message=msg.content,
                context=msg.context,
            )
            return None

        return None

    def get_message_log(self) -> List[Dict[str, Any]]:
        """Return the full inter-agent message log."""
        return list(self._message_log)

    def clear(self) -> None:
        """Reset registry (useful for tests)."""
        self._agents.clear()
        self._message_log.clear()


# Global registry instance
registry = AgentRegistry()


# ---------------------------------------------------------------------------
# Base Agent
# ---------------------------------------------------------------------------

class BaseAgent(ABC):
    """Abstract base class for all lifecycle agents."""

    name: str = "base"
    description: str = ""
    system_prompt: str = ""

    def __init__(self, temperature: float = 0.3):
        self.llm = get_agent_llm(self.name, temperature=temperature)
        self._notifications: List[Dict[str, Any]] = []
        # Auto-register with the global registry
        registry.register(self)

    @abstractmethod
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the agent's logic against the current project state.
        Returns a partial state update dict.
        """
        # [31] Compress context to save tokens
        compressed_state = token_budget.compress_state(state, self.name)
        
        # Format base messages
        system_prompt = self._get_full_system_prompt()
        state_msg = f"Current State:\n{json.dumps(compressed_state, indent=2)}"

        try:
            # -------------------------------------------------------------
            # Step 1: THINK [19]
            # -------------------------------------------------------------
            think_prompt = (
                system_prompt + 
                "\n\nBefore acting, you MUST think. Output a JSON object with your chain of thought:\n"
                "{\n"
                '  "analysis": "what you understand",\n'
                '  "approach": "your plan",\n'
                '  "complexity": "low|medium|high",\n'
                '  "tools_needed": ["tool_names"],\n'
                '  "agents_to_consult": ["agent_names"]\n'
                "}\n"
                "Keep it simple. Avoid microservices or complex patterns unless explicitly requested."
            )
            
            logger.info(f"{self.name} is thinking...")
            thinking_output = asyncio.run(model_wrapper.generate_json(
                system_prompt=think_prompt,
                messages=[{"role": "user", "content": state_msg}],
                temperature=0.2
            ))
            
            # [19] Complexity Gate
            if thinking_output.get("complexity") == "high":
                logger.warning(f"{self.name} detected high complexity. Enforcing simplicity constraint.")
                state_msg += "\n\nCRITICAL INSTRUCTION: Your proposed approach is too complex. You MUST simplify it. Use standard monolithic patterns. Do not over-engineer."

            # -------------------------------------------------------------
            # Step 2: ACT
            # -------------------------------------------------------------
            act_prompt = (
                system_prompt +
                "\n\nBased on your thinking, perform your assigned task and generate the final structured output."
            )
            
            # Inject thinking into the context for the action step
            act_messages = [
                {"role": "user", "content": state_msg},
                {"role": "assistant", "content": f"My Thinking:\n{json.dumps(thinking_output, indent=2)}"},
                {"role": "user", "content": "Now execute the plan and provide the final JSON output."}
            ]
            
            logger.info(f"{self.name} is acting...")
            final_output = asyncio.run(model_wrapper.generate_json(
                system_prompt=act_prompt,
                messages=act_messages,
                temperature=0.2
            ))
            
            # [40] Audit Logging
            from .audit import audit_logger
            audit_logger.log(
                project_id=state.get("project_id", "unknown"),
                agent_name=self.name,
                phase=state.get("current_phase", "unknown"),
                action_type="think_and_act",
                input_context=state_msg,
                thinking=json.dumps(thinking_output),
                output=json.dumps(final_output),
                tools_used=thinking_output.get("tools_needed", []),
                agents_consulted=thinking_output.get("agents_to_consult", []),
                success=True
            )
            
            # [35] Track usage (mocked token counts)
            token_budget.track_usage(
                project_id=state.get("project_id", "unknown"),
                agent_name=self.name,
                input_tokens=1000,
                output_tokens=500
            )
            
            # [05][25] Validate and clean output
            final_output, warnings = GuardRail.validate_output(self.name, final_output)
            if warnings:
                logger.warning(f"GuardRail warnings for {self.name}: {warnings}")
                if "guardrail_warnings" not in final_output:
                    final_output["guardrail_warnings"] = []
                final_output["guardrail_warnings"].extend(warnings)

            return final_output

        except Exception as e:
            logger.error(f"Agent {self.name} failed: {e}")
            from .audit import audit_logger
            from api.events import EventEmitter
            
            # Broadcast the error to the Dashboard UI
            asyncio.run(EventEmitter.emit_error(
                project_id=state.get("project_id", "unknown"),
                agent_name=self.name,
                error_msg=str(e),
                fatal=False  # Agents can often retry, so not fatal by default
            ))

            audit_logger.log(
                project_id=state.get("project_id", "unknown"),
                agent_name=self.name,
                phase=state.get("current_phase", "unknown"),
                action_type="think_and_act",
                input_context=state_msg,
                thinking=None,
                output="",
                success=False,
                error=str(e)
            )
            return {
                "blockers": state.get("blockers", []) + [f"{self.name} error: {str(e)}"]
            }

    # ------------------------------------------------------------------
    # Inter-agent communication — outbound
    # ------------------------------------------------------------------

    def ask_agent(
        self,
        target_agent: str,
        query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Send a request to another agent and get a response.

        Example:
            schema_info = self.ask_agent(
                "database",
                "What is the users table schema?",
                context={"table": "users"}
            )
        """
        msg_id = asyncio.run(message_bus.send(
            project_id="global",  # Ideally passed from state
            from_agent=self.name,
            to_agent=target_agent,
            msg_type="request",
            content=query,
            context=context
        ))
        # Note: In a fully async workflow, this would await the response.
        # For LangGraph compatibility, we return a pending receipt.
        return f"Message queued with ID: {msg_id}"

    def notify_agent(
        self,
        target_agent: str,
        message: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Send a fire-and-forget notification to another agent.

        Example:
            self.notify_agent(
                "orchestrator",
                "Blocker: missing API spec from backend agent",
                context={"blocker_type": "missing_dependency"}
            )
        """
        asyncio.run(message_bus.send(
            project_id="global",
            from_agent=self.name,
            to_agent=target_agent,
            msg_type="notify",
            content=message,
            context=context
        ))

    def broadcast(
        self,
        message: str,
        exclude: Optional[List[str]] = None,
    ) -> None:
        """
        Send a notification to ALL other registered agents.

        Example:
            self.broadcast("Architecture decision: using microservices pattern")
        """
        exclude = exclude or []
        agents = registry.list_agents()
        for a in agents:
            if a != self.name and a not in exclude:
                asyncio.run(message_bus.send(
                    project_id="global",
                    from_agent=self.name,
                    to_agent=a,
                    msg_type="notify",
                    content=message,
                    context={}
                ))

    # ------------------------------------------------------------------
    # Inter-agent communication — inbound
    # ------------------------------------------------------------------

    def handle_request(
        self,
        from_agent: str,
        query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Handle an incoming request from another agent.
        Uses the agent's LLM to generate a contextual response.
        Override in subclasses for custom handling.
        """
        prompt = (
            f"Another agent ({from_agent}) is asking for your help.\n\n"
            f"Their question: {query}\n\n"
            f"Additional context: {context or 'None'}\n\n"
            f"Respond concisely with the information they need, "
            f"based on your expertise as the {self.name} agent."
        )
        response = self._invoke_llm(prompt)

        # Log the response
        response_msg = AgentMessage(
            from_agent=self.name,
            to_agent=from_agent,
            message_type="response",
            content=response,
            context=context or {},
        )
        registry._message_log.append(response_msg.to_dict())

        return response

    def handle_notification(
        self,
        from_agent: str,
        message: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Handle an incoming notification from another agent.
        Stores it for later reference. Override for custom behavior.
        """
        self._notifications.append({
            "from": from_agent,
            "message": message,
            "context": context or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def get_notifications(self) -> List[Dict[str, Any]]:
        """Return all received notifications."""
        pending = asyncio.run(message_bus.receive(
            project_id="global", 
            agent_name=self.name
        ))
        return [m.to_dict() for m in pending]

    def clear_notifications(self) -> None:
        """Clear processed notifications."""
        self._notifications.clear()

    # ------------------------------------------------------------------
    # LLM helpers
    # ------------------------------------------------------------------

    def _invoke_llm(self, user_message: str) -> str:
        """Helper to call the LLM with the agent's system prompt."""
        from langchain_core.messages import SystemMessage, HumanMessage

        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=user_message),
        ]
        response = self.llm.invoke(messages)
        return response.content
