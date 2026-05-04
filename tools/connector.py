"""
Tool Connectors & MCP Client Base.

Solves: [30] Tool over-permission — granular read/write access per agent.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
import time
import logging

logger = logging.getLogger(__name__)


class ToolResult:
    """Standardized result from any tool execution."""
    def __init__(self, success: bool, data: Any, error: Optional[str] = None, 
                 usage: Optional[Dict[str, Any]] = None):
        self.success = success
        self.data = data
        self.error = error
        self.usage = usage or {}

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "usage": self.usage
        }


class ToolConnector(ABC):
    """Base class for all tools (built-in and MCP)."""
    name: str
    description: str
    category: str  # "search" | "file" | "api" | "database" | "mcp"
    is_read_only: bool = True

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        pass


class ToolRegistry:
    """
    Manages tools and enforces per-agent access control [30].
    """
    
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._tools: Dict[str, ToolConnector] = {}
            # Default strict permissions matrix
            # True = full access, False = no access, "read" = read-only
            cls._permissions: Dict[str, Dict[str, Any]] = {
                "orchestrator":     {"web_search": True,  "file_rw": False, "github": False, "db_query": False},
                "business_analyst": {"web_search": True,  "file_rw": False, "github": False, "db_query": False},
                "scrum_master":     {"web_search": False, "file_rw": False, "github": False, "db_query": False},
                "seo":              {"web_search": True,  "file_rw": False, "github": False, "db_query": False},
                "frontend":         {"web_search": True,  "file_rw": True,  "github": "read", "db_query": False},
                "backend":          {"web_search": True,  "file_rw": True,  "github": "read", "db_query": "read"},
                "database":         {"web_search": False, "file_rw": True,  "github": False, "db_query": True},
                "qa":               {"web_search": False, "file_rw": "read", "github": False, "db_query": "read"},
                "security":         {"web_search": True,  "file_rw": "read", "github": False, "db_query": "read"},
                "deploy":           {"web_search": False, "file_rw": True,  "github": True,  "db_query": False},
            }
        return cls._instance

    def register_tool(self, tool: ToolConnector) -> None:
        self._tools[tool.name] = tool
        logger.info(f"Registered tool: {tool.name}")

    def list_tools(self) -> List[Dict[str, Any]]:
        return [
            {"name": t.name, "description": t.description, "category": t.category}
            for t in self._tools.values()
        ]

    def set_permission(self, agent_name: str, tool_name: str, access: Any) -> None:
        """Update permissions from dashboard."""
        if agent_name not in self._permissions:
            self._permissions[agent_name] = {}
        self._permissions[agent_name][tool_name] = access

    def get_permissions(self) -> Dict[str, Dict[str, Any]]:
        return self._permissions

    def has_permission(self, agent_name: str, tool_name: str, is_write: bool = False) -> bool:
        """Check if agent is allowed to use this tool."""
        agent_perms = self._permissions.get(agent_name, {})
        access = agent_perms.get(tool_name, False)
        
        if access is False:
            return False
        if access is True:
            return True
            
        # "read" access
        if access == "read":
            return not is_write
            
        return False

    async def execute_tool(self, agent_name: str, tool_name: str, **kwargs) -> ToolResult:
        """
        Execute tool with permission enforcement.
        """
        start_time = time.time()
        
        if tool_name not in self._tools:
            return ToolResult(False, None, f"Tool '{tool_name}' not found")
            
        tool = self._tools[tool_name]
        
        # Check permissions [30]
        # Heuristic: if kwargs has 'write', 'create', 'update', 'delete', it's a write op
        is_write_op = not tool.is_read_only and any(
            k in kwargs for k in ['content', 'query_type', 'data'] 
            if kwargs.get('query_type') in ['INSERT', 'UPDATE', 'DELETE', 'DROP']
        )
        
        if not self.has_permission(agent_name, tool_name, is_write=is_write_op):
            logger.warning(f"Permission denied: {agent_name} -> {tool_name} (write={is_write_op})")
            return ToolResult(False, None, f"Agent '{agent_name}' lacks permission to execute '{tool_name}'")

        try:
            # Execute
            result = await tool.execute(**kwargs)
            
            # Add timing
            result.usage["duration_ms"] = int((time.time() - start_time) * 1000)
            return result
            
        except Exception as e:
            logger.error(f"Tool {tool_name} error: {e}")
            return ToolResult(False, None, str(e))


# Global instance
tool_registry = ToolRegistry()
