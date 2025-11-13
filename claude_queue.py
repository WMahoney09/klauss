#!/usr/bin/env python3
"""
Claude Code Task Queue Manager
Manages a SQLite-based task queue for parallel Claude Code execution
"""

import sqlite3
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List
from enum import Enum
import threading

class TaskStatus(Enum):
    PENDING = "pending"
    CLAIMED = "claimed"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class TaskQueue:
    def __init__(self, db_path: str = "claude_tasks.db"):
        self.db_path = db_path
        self.local = threading.local()
        self._init_db()

    def _get_conn(self):
        """Get thread-local database connection"""
        if not hasattr(self.local, 'conn'):
            self.local.conn = sqlite3.connect(self.db_path, timeout=30.0)
            self.local.conn.row_factory = sqlite3.Row
        return self.local.conn

    def _init_db(self):
        """Initialize database schema"""
        conn = self._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prompt TEXT NOT NULL,
                working_dir TEXT,
                context_files TEXT,  -- JSON array of files to read
                expected_outputs TEXT,  -- JSON array of expected output files
                metadata TEXT,  -- JSON for additional data
                status TEXT NOT NULL DEFAULT 'pending',
                worker_id TEXT,
                job_id TEXT,  -- Group related tasks together
                parent_task_id INTEGER,  -- For hierarchical tasks
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                claimed_at TIMESTAMP,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                result TEXT,  -- JSON with results/outputs
                error TEXT,
                priority INTEGER DEFAULT 0,
                FOREIGN KEY (parent_task_id) REFERENCES tasks(id)
            )
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_status
            ON tasks(status, priority DESC, created_at)
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS workers (
                worker_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                current_task_id INTEGER,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_heartbeat TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                stats TEXT  -- JSON with worker statistics
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                description TEXT,
                orchestrator_id TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                metadata TEXT  -- JSON for job-level data
            )
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_job_tasks
            ON tasks(job_id, status)
        """)

        conn.commit()

    def add_task(self, prompt: str, working_dir: Optional[str] = None,
                 context_files: Optional[List[str]] = None,
                 expected_outputs: Optional[List[str]] = None,
                 metadata: Optional[Dict] = None,
                 priority: int = 0,
                 job_id: Optional[str] = None,
                 parent_task_id: Optional[int] = None) -> int:
        """Add a new task to the queue"""
        conn = self._get_conn()
        cursor = conn.execute("""
            INSERT INTO tasks (prompt, working_dir, context_files,
                             expected_outputs, metadata, priority, job_id, parent_task_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            prompt,
            working_dir,
            json.dumps(context_files) if context_files else None,
            json.dumps(expected_outputs) if expected_outputs else None,
            json.dumps(metadata) if metadata else None,
            priority,
            job_id,
            parent_task_id
        ))
        conn.commit()
        return cursor.lastrowid

    def claim_task(self, worker_id: str) -> Optional[Dict]:
        """Atomically claim the next available task"""
        conn = self._get_conn()

        # Use transaction to ensure atomicity
        conn.execute("BEGIN EXCLUSIVE")
        try:
            # Get highest priority pending task
            cursor = conn.execute("""
                SELECT * FROM tasks
                WHERE status = 'pending'
                ORDER BY priority DESC, created_at ASC
                LIMIT 1
            """)
            task = cursor.fetchone()

            if not task:
                conn.rollback()
                return None

            # Claim it
            conn.execute("""
                UPDATE tasks
                SET status = 'claimed', worker_id = ?, claimed_at = ?
                WHERE id = ?
            """, (worker_id, datetime.now(), task['id']))

            conn.commit()
            return dict(task)
        except Exception as e:
            conn.rollback()
            raise e

    def start_task(self, task_id: int, worker_id: str):
        """Mark task as in progress"""
        conn = self._get_conn()
        conn.execute("""
            UPDATE tasks
            SET status = 'in_progress', started_at = ?
            WHERE id = ? AND worker_id = ?
        """, (datetime.now(), task_id, worker_id))
        conn.commit()

    def complete_task(self, task_id: int, worker_id: str, result: Optional[Dict] = None):
        """Mark task as completed"""
        conn = self._get_conn()
        conn.execute("""
            UPDATE tasks
            SET status = 'completed', completed_at = ?, result = ?
            WHERE id = ? AND worker_id = ?
        """, (datetime.now(), json.dumps(result) if result else None, task_id, worker_id))
        conn.commit()

    def fail_task(self, task_id: int, worker_id: str, error: str):
        """Mark task as failed"""
        conn = self._get_conn()
        conn.execute("""
            UPDATE tasks
            SET status = 'failed', completed_at = ?, error = ?
            WHERE id = ? AND worker_id = ?
        """, (datetime.now(), error, task_id, worker_id))
        conn.commit()

    def register_worker(self, worker_id: str):
        """Register a new worker"""
        conn = self._get_conn()
        conn.execute("""
            INSERT OR REPLACE INTO workers (worker_id, status, last_heartbeat)
            VALUES (?, 'idle', ?)
        """, (worker_id, datetime.now()))
        conn.commit()

    def update_worker_heartbeat(self, worker_id: str, status: str = 'active',
                                current_task_id: Optional[int] = None):
        """Update worker heartbeat"""
        conn = self._get_conn()
        conn.execute("""
            UPDATE workers
            SET last_heartbeat = ?, status = ?, current_task_id = ?
            WHERE worker_id = ?
        """, (datetime.now(), status, current_task_id, worker_id))
        conn.commit()

    def get_task(self, task_id: int) -> Optional[Dict]:
        """Get task by ID"""
        conn = self._get_conn()
        cursor = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_all_tasks(self, status: Optional[str] = None) -> List[Dict]:
        """Get all tasks, optionally filtered by status"""
        conn = self._get_conn()
        if status:
            cursor = conn.execute(
                "SELECT * FROM tasks WHERE status = ? ORDER BY priority DESC, created_at",
                (status,)
            )
        else:
            cursor = conn.execute("SELECT * FROM tasks ORDER BY created_at DESC")
        return [dict(row) for row in cursor.fetchall()]

    def get_all_workers(self) -> List[Dict]:
        """Get all registered workers"""
        conn = self._get_conn()
        cursor = conn.execute("SELECT * FROM workers ORDER BY worker_id")
        return [dict(row) for row in cursor.fetchall()]

    def get_stats(self) -> Dict:
        """Get queue statistics"""
        conn = self._get_conn()
        stats = {}

        for status in TaskStatus:
            cursor = conn.execute(
                "SELECT COUNT(*) as count FROM tasks WHERE status = ?",
                (status.value,)
            )
            stats[status.value] = cursor.fetchone()[0]

        cursor = conn.execute("SELECT COUNT(*) as count FROM workers WHERE status = 'active'")
        stats['active_workers'] = cursor.fetchone()[0]

        cursor = conn.execute("SELECT COUNT(*) as count FROM workers")
        stats['total_workers'] = cursor.fetchone()[0]

        return stats

    def create_job(self, job_id: str, description: str, orchestrator_id: str,
                   metadata: Optional[Dict] = None):
        """Create a new job"""
        conn = self._get_conn()
        conn.execute("""
            INSERT INTO jobs (job_id, description, orchestrator_id, metadata)
            VALUES (?, ?, ?, ?)
        """, (job_id, description, orchestrator_id, json.dumps(metadata) if metadata else None))
        conn.commit()

    def get_job(self, job_id: str) -> Optional[Dict]:
        """Get job by ID"""
        conn = self._get_conn()
        cursor = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_job_tasks(self, job_id: str, status: Optional[str] = None) -> List[Dict]:
        """Get all tasks for a job"""
        conn = self._get_conn()
        if status:
            cursor = conn.execute(
                "SELECT * FROM tasks WHERE job_id = ? AND status = ? ORDER BY created_at",
                (job_id, status)
            )
        else:
            cursor = conn.execute(
                "SELECT * FROM tasks WHERE job_id = ? ORDER BY created_at",
                (job_id,)
            )
        return [dict(row) for row in cursor.fetchall()]

    def get_job_stats(self, job_id: str) -> Dict:
        """Get statistics for a specific job"""
        conn = self._get_conn()
        stats = {}

        for status in TaskStatus:
            cursor = conn.execute(
                "SELECT COUNT(*) as count FROM tasks WHERE job_id = ? AND status = ?",
                (job_id, status.value)
            )
            stats[status.value] = cursor.fetchone()[0]

        return stats

    def complete_job(self, job_id: str):
        """Mark job as completed"""
        conn = self._get_conn()
        conn.execute("""
            UPDATE jobs
            SET status = 'completed', completed_at = ?
            WHERE job_id = ?
        """, (datetime.now(), job_id))
        conn.commit()

    def wait_for_job_completion(self, job_id: str, poll_interval: float = 2.0,
                                timeout: Optional[float] = None) -> bool:
        """Wait for all tasks in a job to complete"""
        import time as time_module
        start_time = time_module.time()

        while True:
            stats = self.get_job_stats(job_id)
            pending = stats['pending'] + stats['claimed'] + stats['in_progress']

            if pending == 0:
                return True

            if timeout and (time_module.time() - start_time) > timeout:
                return False

            time_module.sleep(poll_interval)

    def get_child_tasks(self, parent_task_id: int) -> List[Dict]:
        """Get all child tasks of a parent task"""
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT * FROM tasks WHERE parent_task_id = ? ORDER BY created_at",
            (parent_task_id,)
        )
        return [dict(row) for row in cursor.fetchall()]

    def cleanup_stale_tasks(self, timeout_seconds: int = 3600):
        """Reset tasks claimed by workers that haven't sent heartbeat"""
        conn = self._get_conn()
        conn.execute("""
            UPDATE tasks
            SET status = 'pending', worker_id = NULL, claimed_at = NULL
            WHERE status IN ('claimed', 'in_progress')
            AND worker_id IN (
                SELECT worker_id FROM workers
                WHERE julianday('now') - julianday(last_heartbeat) > ?
            )
        """, (timeout_seconds / 86400.0,))
        conn.commit()

    # Convenience aliases for more intuitive API
    def list_tasks(self, status: Optional[str] = None, job_id: Optional[str] = None) -> List[Dict]:
        """
        List tasks with optional filters

        Args:
            status: Filter by task status (pending, claimed, in_progress, completed, failed)
            job_id: Filter by job ID

        Returns:
            List of task dictionaries

        Examples:
            # Get all pending tasks
            pending_tasks = queue.list_tasks(status='pending')

            # Get all tasks for a job
            job_tasks = queue.list_tasks(job_id='job_abc123')

            # Get completed tasks for a job
            completed = queue.list_tasks(status='completed', job_id='job_abc123')

            # Get all tasks
            all_tasks = queue.list_tasks()
        """
        if job_id:
            return self.get_job_tasks(job_id, status)
        else:
            return self.get_all_tasks(status)

    def list_workers(self) -> List[Dict]:
        """
        List all registered workers

        Returns:
            List of worker dictionaries with status and heartbeat info
        """
        return self.get_all_workers()
