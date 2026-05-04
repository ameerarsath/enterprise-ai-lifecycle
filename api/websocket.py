"""
WebSocket Manager for Real-time Dashboard Updates.
"""

from typing import Dict, List, Any
from fastapi import WebSocket
import logging
import json
import asyncio

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        # project_id -> list of active connections
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, project_id: str):
        await websocket.accept()
        if project_id not in self.active_connections:
            self.active_connections[project_id] = []
        self.active_connections[project_id].append(websocket)
        logger.info(f"WebSocket connected for project {project_id}")

    def disconnect(self, websocket: WebSocket, project_id: str):
        if project_id in self.active_connections:
            self.active_connections[project_id].remove(websocket)
            if not self.active_connections[project_id]:
                del self.active_connections[project_id]
            logger.info(f"WebSocket disconnected for project {project_id}")

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast_to_project(self, project_id: str, message: dict):
        """Broadcast a structured message to all clients connected to a project."""
        if project_id in self.active_connections:
            # We serialize to JSON
            payload = json.dumps(message)
            disconnected = []
            for connection in self.active_connections[project_id]:
                try:
                    await connection.send_text(payload)
                except Exception as e:
                    logger.warning(f"Error sending message to websocket: {e}")
                    disconnected.append(connection)
                    
            for conn in disconnected:
                self.disconnect(conn, project_id)


# Global instance
ws_manager = ConnectionManager()
