"""
Progress Broadcaster - Manages WebSocket broadcasting of knowledge base progress
"""

import asyncio
import logging
from typing import Optional

from fastapi import WebSocket

from deeptutor.auth.context import current_user_id

logger = logging.getLogger(__name__)


class ProgressBroadcaster:
    """Manages WebSocket broadcasting of knowledge base progress"""

    _instance: Optional["ProgressBroadcaster"] = None
    _lock = asyncio.Lock()

    def __init__(self) -> None:
        self._connections: dict[tuple[str | None, str], set[WebSocket]] = {}

    @classmethod
    def get_instance(cls) -> "ProgressBroadcaster":
        """Get singleton instance"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _key(self, kb_name: str, user_id: str | None = None) -> tuple[str | None, str]:
        owner = str(user_id or current_user_id() or "").strip() or None
        return owner, str(kb_name or "").strip()

    async def connect(self, kb_name: str, websocket: WebSocket, user_id: str | None = None):
        """Connect WebSocket to specified knowledge base"""
        key = self._key(kb_name, user_id)
        async with self._lock:
            if key not in self._connections:
                self._connections[key] = set()
            self._connections[key].add(websocket)
            logger.debug(
                f"Connected WebSocket for KB '{kb_name}' (total: {len(self._connections[key])})"
            )

    async def disconnect(self, kb_name: str, websocket: WebSocket, user_id: str | None = None):
        """Disconnect WebSocket connection"""
        key = self._key(kb_name, user_id)
        async with self._lock:
            if key in self._connections:
                self._connections[key].discard(websocket)
                if not self._connections[key]:
                    del self._connections[key]
                logger.debug(f"Disconnected WebSocket for KB '{kb_name}'")

    async def broadcast(self, kb_name: str, progress: dict, user_id: str | None = None):
        """Broadcast progress update to all WebSocket connections for specified knowledge base"""
        key = self._key(kb_name, user_id)
        async with self._lock:
            if key not in self._connections:
                return

            # Create list of connections to remove (closed connections)
            to_remove = []

            for websocket in self._connections[key]:
                try:
                    await websocket.send_json({"type": "progress", "data": progress})
                except Exception as e:
                    # Connection closed or error, mark for removal
                    logger.debug(f"Error sending to WebSocket for KB '{kb_name}': {e}")
                    to_remove.append(websocket)

            # Remove closed connections
            for ws in to_remove:
                self._connections[key].discard(ws)

            if not self._connections[key]:
                del self._connections[key]

    def get_connection_count(self, kb_name: str, user_id: str | None = None) -> int:
        """Get connection count for specified knowledge base"""
        return len(self._connections.get(self._key(kb_name, user_id), set()))
