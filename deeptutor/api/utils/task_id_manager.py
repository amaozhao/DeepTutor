"""
Task ID Manager - Assigns unique IDs to each background task
"""

from datetime import datetime, timedelta
import threading
from typing import Optional
import uuid

from deeptutor.auth.context import current_user_id
from deeptutor.auth.resource_ids import validate_task_id


class TaskIDManager:
    """Singleton class for managing task IDs"""

    _instance: Optional["TaskIDManager"] = None
    _lock = threading.Lock()
    _task_ids: dict[str, str] = {}  # task_key -> task_id
    _task_metadata: dict[str, dict] = {}  # task_id -> metadata

    @classmethod
    def get_instance(cls) -> "TaskIDManager":
        """Get singleton instance"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def _owner_id(self, user_id: str | None = None) -> str | None:
        owner = str(user_id or current_user_id() or "").strip()
        if not owner:
            try:
                from deeptutor.multi_user.context import get_current_user

                owner = str(get_current_user().id or "").strip()
            except Exception:
                owner = ""
        return owner or None

    def _lookup_key(self, task_key: str, user_id: str | None = None) -> str:
        owner = self._owner_id(user_id) or "_legacy"
        return f"{owner}:{task_key}"

    def generate_task_id(self, task_type: str, task_key: str, user_id: str | None = None) -> str:
        """
        Generate unique ID for task

        Args:
            task_type: Task type (e.g., 'kb_init', 'kb_upload', 'question_gen', 'solve', 'research')
            task_key: Task unique identifier (e.g., knowledge base name, question ID, etc.)

        Returns:
            Task ID (format: {task_type}_{timestamp}_{uuid})
        """
        with self._lock:
            lookup_key = self._lookup_key(task_key, user_id)
            # If task already exists, return existing ID
            if lookup_key in self._task_ids:
                return self._task_ids[lookup_key]

            # Generate new ID
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            unique_id = str(uuid.uuid4())[:8]
            task_id = f"{task_type}_{timestamp}_{unique_id}"
            owner = self._owner_id(user_id)

            # Save mapping and metadata
            self._task_ids[lookup_key] = task_id
            self._task_metadata[task_id] = {
                "task_type": task_type,
                "task_key": task_key,
                "created_at": datetime.now().isoformat(),
                "status": "running",
            }
            if owner:
                self._task_metadata[task_id]["user_id"] = owner

            return task_id

    def get_task_id(self, task_key: str, user_id: str | None = None) -> str | None:
        """Get task ID"""
        with self._lock:
            return self._task_ids.get(self._lookup_key(task_key, user_id))

    def update_task_status(self, task_id: str, status: str, **kwargs):
        """Update task status"""
        with self._lock:
            if task_id in self._task_metadata:
                self._task_metadata[task_id]["status"] = status
                self._task_metadata[task_id].update(kwargs)
                if status in ["completed", "error", "cancelled"]:
                    self._task_metadata[task_id]["finished_at"] = datetime.now().isoformat()

    def get_task_metadata(self, task_id: str) -> dict | None:
        """Get task metadata"""
        with self._lock:
            return self._task_metadata.get(task_id, {}).copy()

    def is_task_owned_by(self, task_id: str, user_id: str | None) -> bool:
        try:
            safe_task_id = validate_task_id(task_id)
        except ValueError:
            return False
        owner = self._owner_id(user_id)
        with self._lock:
            metadata = self._task_metadata.get(safe_task_id)
            if not metadata or not owner:
                return False
            return metadata.get("user_id") == owner

    def cleanup_old_tasks(self, max_age_hours: int = 24):
        """Clean up old tasks (completed tasks older than specified hours)"""
        with self._lock:
            cutoff = datetime.now() - timedelta(hours=max_age_hours)

            to_remove = []
            for task_id, metadata in self._task_metadata.items():
                if metadata.get("status") in ["completed", "error", "cancelled"]:
                    finished_at = metadata.get("finished_at")
                    if finished_at:
                        try:
                            finished_time = datetime.fromisoformat(finished_at)
                            if finished_time < cutoff:
                                to_remove.append(task_id)
                        except:
                            pass

            for task_id in to_remove:
                metadata = self._task_metadata.pop(task_id, {})
                task_key = metadata.get("task_key")
                if task_key:
                    self._task_ids.pop(self._lookup_key(task_key, metadata.get("user_id")), None)
