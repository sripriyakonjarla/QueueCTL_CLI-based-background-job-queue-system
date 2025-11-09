"""Persistent storage for jobs using SQLite."""

import sqlite3
import json
import threading
from contextlib import contextmanager
from typing import List, Optional, Dict, Any
from datetime import datetime

from queuectl.job import Job, JobState


class Storage:
    """SQLite-based persistent storage for jobs."""
    
    def __init__(self, db_path: str = "queuectl.db"):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()
    
    def _init_db(self):
        """Initialize database schema."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    command TEXT NOT NULL,
                    state TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    max_retries INTEGER NOT NULL DEFAULT 3,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    next_retry_at TEXT,
                    worker_id TEXT
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_state ON jobs(state)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_next_retry ON jobs(next_retry_at)
            """)
            conn.commit()
    
    @contextmanager
    def _get_connection(self):
        """Get database connection with thread safety."""
        with self._lock:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            try:
                yield conn
            finally:
                conn.close()
    
    def add_job(self, job: Job) -> bool:
        """Add a new job to storage."""
        with self._get_connection() as conn:
            try:
                # Convert timezone-aware datetimes to naive UTC
                created_at = job.created_at.replace(tzinfo=None) if job.created_at.tzinfo else job.created_at
                updated_at = job.updated_at.replace(tzinfo=None) if job.updated_at.tzinfo else job.updated_at
                next_retry_at = None
                if job.next_retry_at:
                    next_retry_at = job.next_retry_at.replace(tzinfo=None) if job.next_retry_at.tzinfo else job.next_retry_at
                
                conn.execute("""
                    INSERT INTO jobs (id, command, state, attempts, max_retries, 
                                    created_at, updated_at, next_retry_at, worker_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    job.id, job.command, job.state.value, job.attempts,
                    job.max_retries, created_at.isoformat() + "Z",
                    updated_at.isoformat() + "Z",
                    next_retry_at.isoformat() + "Z" if next_retry_at else None,
                    None
                ))
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False
    
    def get_job(self, job_id: str) -> Optional[Job]:
        """Get a job by ID."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
            if row:
                return self._row_to_job(row)
            return None
    
    def update_job(self, job: Job, worker_id: Optional[str] = None):
        """Update job in storage."""
        with self._get_connection() as conn:
            # Convert timezone-aware datetimes to naive UTC to avoid double timezone suffixes
            updated_at = job.updated_at.replace(tzinfo=None) if job.updated_at.tzinfo else job.updated_at
            next_retry_at = None
            if job.next_retry_at:
                next_retry_at = job.next_retry_at.replace(tzinfo=None) if job.next_retry_at.tzinfo else job.next_retry_at
            
            conn.execute("""
                UPDATE jobs 
                SET state = ?, attempts = ?, updated_at = ?, next_retry_at = ?, worker_id = ?
                WHERE id = ?
            """, (
                job.state.value, job.attempts,
                updated_at.isoformat() + "Z",
                next_retry_at.isoformat() + "Z" if next_retry_at else None,
                worker_id,
                job.id
            ))
            conn.commit()
    
    def get_pending_job(self, worker_id: str) -> Optional[Job]:
        """Get and lock a pending job for processing (with row-level locking)."""
        with self._get_connection() as conn:
            # Use a transaction to lock the row
            conn.execute("BEGIN IMMEDIATE")
            try:
                now = datetime.utcnow().isoformat() + "Z"
                
                # First, try to get a pending job
                row = conn.execute("""
                    SELECT * FROM jobs 
                    WHERE state = ? AND (next_retry_at IS NULL OR next_retry_at <= ?)
                    ORDER BY created_at ASC
                    LIMIT 1
                """, (JobState.PENDING.value, now)).fetchone()
                
                # If no pending job, try failed jobs ready for retry
                if not row:
                    row = conn.execute("""
                        SELECT * FROM jobs 
                        WHERE state = ? AND next_retry_at <= ?
                        ORDER BY created_at ASC
                        LIMIT 1
                    """, (JobState.FAILED.value, now)).fetchone()
                
                if row:
                    job = self._row_to_job(row)
                    # Verify it's still in the expected state (prevent race condition)
                    verify_row = conn.execute(
                        "SELECT state FROM jobs WHERE id = ?", (job.id,)
                    ).fetchone()
                    
                    if verify_row and verify_row["state"] == row["state"]:
                        # Lock it by updating worker_id and state
                        cursor = conn.execute(
                            "UPDATE jobs SET state = ?, worker_id = ? WHERE id = ? AND state = ?",
                            (JobState.PROCESSING.value, worker_id, job.id, row["state"])
                        )
                        if cursor.rowcount > 0:
                            conn.commit()
                            job.state = JobState.PROCESSING
                            return job
                
                conn.commit()
                return None
            except Exception:
                conn.rollback()
                raise
    
    def list_jobs(self, state: Optional[JobState] = None) -> List[Job]:
        """List jobs, optionally filtered by state."""
        with self._get_connection() as conn:
            if state:
                rows = conn.execute(
                    "SELECT * FROM jobs WHERE state = ? ORDER BY created_at DESC",
                    (state.value,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM jobs ORDER BY created_at DESC"
                ).fetchall()
            return [self._row_to_job(row) for row in rows]
    
    def get_stats(self) -> Dict[str, int]:
        """Get statistics about job states."""
        with self._get_connection() as conn:
            rows = conn.execute("""
                SELECT state, COUNT(*) as count FROM jobs GROUP BY state
            """).fetchall()
            stats = {row["state"]: row["count"] for row in rows}
            return {
                "pending": stats.get(JobState.PENDING.value, 0),
                "processing": stats.get(JobState.PROCESSING.value, 0),
                "completed": stats.get(JobState.COMPLETED.value, 0),
                "failed": stats.get(JobState.FAILED.value, 0),
                "dead": stats.get(JobState.DEAD.value, 0),
            }
    
    def _row_to_job(self, row) -> Job:
        """Convert database row to Job object."""
        created_at = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))
        updated_at = datetime.fromisoformat(row["updated_at"].replace("Z", "+00:00"))
        next_retry_at = None
        if row["next_retry_at"]:
            next_retry_at = datetime.fromisoformat(row["next_retry_at"].replace("Z", "+00:00"))
        
        return Job(
            id=row["id"],
            command=row["command"],
            state=JobState(row["state"]),
            attempts=row["attempts"],
            max_retries=row["max_retries"],
            created_at=created_at,
            updated_at=updated_at,
            next_retry_at=next_retry_at,
        )

