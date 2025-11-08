"""Job model and state management."""

import uuid
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional


class JobState(Enum):
    """Job state enumeration."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD = "dead"


class Job:
    """Represents a background job."""
    
    def __init__(
        self,
        id: str,
        command: str,
        state: JobState = JobState.PENDING,
        attempts: int = 0,
        max_retries: int = 3,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
        next_retry_at: Optional[datetime] = None,
    ):
        self.id = id
        self.command = command
        self.state = state
        self.attempts = attempts
        self.max_retries = max_retries
        self.created_at = created_at or datetime.utcnow()
        self.updated_at = updated_at or datetime.utcnow()
        self.next_retry_at = next_retry_at
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert job to dictionary for storage."""
        return {
            "id": self.id,
            "command": self.command,
            "state": self.state.value,
            "attempts": self.attempts,
            "max_retries": self.max_retries,
            "created_at": self.created_at.isoformat() + "Z",
            "updated_at": self.updated_at.isoformat() + "Z",
            "next_retry_at": self.next_retry_at.isoformat() + "Z" if self.next_retry_at else None,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Job":
        """Create job from dictionary."""
        return cls(
            id=data["id"],
            command=data["command"],
            state=JobState(data["state"]),
            attempts=data["attempts"],
            max_retries=data.get("max_retries", 3),
            created_at=datetime.fromisoformat(data["created_at"].replace("Z", "+00:00")),
            updated_at=datetime.fromisoformat(data["updated_at"].replace("Z", "+00:00")),
            next_retry_at=datetime.fromisoformat(data["next_retry_at"].replace("Z", "+00:00")) if data.get("next_retry_at") else None,
        )
    
    def mark_processing(self):
        """Mark job as being processed."""
        self.state = JobState.PROCESSING
        self.updated_at = datetime.utcnow()
    
    def mark_completed(self):
        """Mark job as completed."""
        self.state = JobState.COMPLETED
        self.updated_at = datetime.utcnow()
    
    def mark_failed(self, next_retry_at: Optional[datetime] = None):
        """Mark job as failed."""
        self.state = JobState.FAILED
        self.attempts += 1
        self.updated_at = datetime.utcnow()
        self.next_retry_at = next_retry_at
    
    def mark_dead(self):
        """Mark job as dead (moved to DLQ)."""
        self.state = JobState.DEAD
        self.updated_at = datetime.utcnow()
    
    def should_retry(self) -> bool:
        """Check if job should be retried."""
        return self.attempts < self.max_retries and self.state == JobState.FAILED
    
    def is_ready_for_retry(self) -> bool:
        """Check if job is ready to be retried (backoff delay passed)."""
        if not self.next_retry_at:
            return True
        return datetime.utcnow() >= self.next_retry_at


