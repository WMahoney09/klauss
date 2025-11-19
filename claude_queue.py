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

        # Shared context for worker coordination
        conn.execute("""
            CREATE TABLE IF NOT EXISTS shared_context (
                context_id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT,  -- NULL for global context
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(job_id, key)
        """)
        
        # Worker logs for progress visibility
        conn.execute("""
            CREATE TABLE IF NOT EXISTS worker_logs (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                worker_id TEXT NOT NULL,
                task_id INTEGER,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                message TEXT NOT NULL,
                level TEXT DEFAULT 'info',  -- 'info', 'warning', 'error'
                FOREIGN KEY (task_id) REFERENCES tasks(id)
            )
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_shared_context_job
            ON shared_context(job_id)
        """)

        # Task dependencies
        conn.execute("""
            CREATE TABLE IF NOT EXISTS task_dependencies (
                task_id INTEGER NOT NULL,
                depends_on_task_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (task_id, depends_on_task_id),
                FOREIGN KEY (task_id) REFERENCES tasks(id),
                FOREIGN KEY (depends_on_task_id) REFERENCES tasks(id)
            )
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_task_dependencies
            ON task_dependencies(task_id)
            CREATE INDEX IF NOT EXISTS idx_worker_logs_task
            ON worker_logs(task_id, timestamp)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_worker_logs_worker
            ON worker_logs(worker_id, timestamp DESC)
        """)

        conn.commit()

    # Public API Methods

    def get_connection(self):
        """
        Get a database connection for custom queries

        Returns:
            sqlite3.Connection: Thread-local database connection

        Example:
            ```python
            conn = queue.get_connection()
            cursor = conn.execute("SELECT * FROM tasks WHERE status = ?", ("pending",))
            for row in cursor:
                print(row['id'], row['prompt'])
            ```

        Note:
            The connection is thread-local and managed internally.
            It's safe to use across multiple calls in the same thread.
        """
        return self._get_conn()

    def log_worker_progress(self, worker_id: str, message: str,
                           task_id: Optional[int] = None, level: str = 'info'):
        """
        Log worker progress message for real-time visibility

        Args:
            worker_id: Worker identifier
            message: Progress message
            task_id: Optional task ID this log relates to
            level: Log level ('info', 'warning', 'error')

        Example:
            ```python
            queue.log_worker_progress("worker_1", "Starting TypeScript compilation", task_id=123)
            queue.log_worker_progress("worker_1", "Compilation passed", task_id=123)
            ```
        """
        conn = self._get_conn()
        conn.execute("""
            INSERT INTO worker_logs (worker_id, task_id, message, level)
            VALUES (?, ?, ?, ?)
        """, (worker_id, task_id, message, level))
        conn.commit()

    def get_worker_logs(self, worker_id: Optional[str] = None,
                       task_id: Optional[int] = None,
                       limit: int = 100) -> List[Dict]:
        """
        Get worker progress logs

        Args:
            worker_id: Optional worker ID to filter by
            task_id: Optional task ID to filter by
            limit: Maximum number of logs to return (default: 100)

        Returns:
            List of log dictionaries with keys: log_id, worker_id, task_id,
            timestamp, message, level

        Example:
            ```python
            # Get all logs for a specific worker
            logs = queue.get_worker_logs(worker_id="worker_1")

            # Get all logs for a specific task
            logs = queue.get_worker_logs(task_id=123)

            # Get recent logs across all workers
            logs = queue.get_worker_logs(limit=50)
            ```
        """
        conn = self._get_conn()

        query = "SELECT * FROM worker_logs WHERE 1=1"
        params = []

        if worker_id:
            query += " AND worker_id = ?"
            params.append(worker_id)

        if task_id:
            query += " AND task_id = ?"
            params.append(task_id)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        cursor = conn.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    def get_active_progress(self) -> List[Dict]:
        """
        Get current progress across all active workers

        Returns:
            List of dictionaries with worker status and current task info:
            - worker_id: Worker identifier
            - status: Worker status ('active', 'idle')
            - current_task_id: Current task ID (if any)
            - task_prompt: Current task prompt (if any)
            - task_status: Current task status
            - recent_log: Most recent log message

        Example:
            ```python
            progress = queue.get_active_progress()
            for worker in progress:
                if worker['current_task_id']:
                    print(f"{worker['worker_id']}: {worker['task_prompt'][:50]}...")
                else:
                    print(f"{worker['worker_id']}: Idle")
            ```
        """
        conn = self._get_conn()

        cursor = conn.execute("""
            SELECT
                w.worker_id,
                w.status,
                w.current_task_id,
                t.prompt as task_prompt,
                t.status as task_status,
                (
                    SELECT message
                    FROM worker_logs
                    WHERE worker_id = w.worker_id
                    ORDER BY timestamp DESC
                    LIMIT 1
                ) as recent_log
            FROM workers w
            LEFT JOIN tasks t ON w.current_task_id = t.id
            ORDER BY w.worker_id
        """)

        return [dict(row) for row in cursor.fetchall()]

    def get_job_progress(self, job_id: str) -> Dict:
        """
        Get detailed progress information for a specific job

        Args:
            job_id: Job identifier

        Returns:
            Dictionary with comprehensive job progress:
            - job_info: Job metadata
            - stats: Task statistics (pending, in_progress, completed, failed)
            - active_tasks: List of currently executing tasks with worker info
            - recent_logs: Recent log messages for this job's tasks

        Example:
            ```python
            progress = queue.get_job_progress("job_abc123")
            print(f"Progress: {progress['stats']['completed']}/{progress['stats']['total']}")
            for task in progress['active_tasks']:
                print(f"  {task['worker_id']}: {task['prompt'][:50]}...")
            ```
        """
        conn = self._get_conn()

        # Get job info
        job = self.get_job(job_id)

        # Get stats
        stats = self.get_job_stats(job_id)

        # Get active tasks with worker info
        cursor = conn.execute("""
            SELECT
                t.id,
                t.prompt,
                t.status,
                t.worker_id,
                t.started_at,
                w.last_heartbeat
            FROM tasks t
            LEFT JOIN workers w ON t.worker_id = w.worker_id
            WHERE t.job_id = ? AND t.status IN ('claimed', 'in_progress')
            ORDER BY t.started_at
        """, (job_id,))
        active_tasks = [dict(row) for row in cursor.fetchall()]

        # Get recent logs for this job's tasks
        cursor = conn.execute("""
            SELECT
                wl.worker_id,
                wl.task_id,
                wl.timestamp,
                wl.message,
                wl.level,
                t.prompt as task_prompt
            FROM worker_logs wl
            JOIN tasks t ON wl.task_id = t.id
            WHERE t.job_id = ?
            ORDER BY wl.timestamp DESC
            LIMIT 50
        """, (job_id,))
        recent_logs = [dict(row) for row in cursor.fetchall()]

        return {
            'job_info': job,
            'stats': stats,
            'active_tasks': active_tasks,
            'recent_logs': recent_logs
        }

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
        """
        Atomically claim the next available task

        Only claims tasks whose dependencies are met (all dependent tasks completed).

        Args:
            worker_id: Worker identifier claiming the task

        Returns:
            Task dictionary if claimed, None if no tasks available
        """
        conn = self._get_conn()

        # Use transaction to ensure atomicity
        conn.execute("BEGIN EXCLUSIVE")
        try:
            # Get pending tasks ordered by priority
            # We'll check dependencies for each until we find one we can claim
            cursor = conn.execute("""
                SELECT * FROM tasks
                WHERE status = 'pending'
                ORDER BY priority DESC, created_at ASC
                LIMIT 10
            """)
            tasks = cursor.fetchall()

            if not tasks:
                conn.rollback()
                return None

            # Find first task with met dependencies
            for task in tasks:
                if self.are_dependencies_met(task['id']):
                    # Claim it
                    conn.execute("""
                        UPDATE tasks
                        SET status = 'claimed', worker_id = ?, claimed_at = ?
                        WHERE id = ?
                    """, (worker_id, datetime.now(), task['id']))

                    conn.commit()
                    return dict(task)

            # No tasks with met dependencies
            conn.rollback()
            return None

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

    # Shared Context API

    def set_shared_context(self, key: str, value: str, job_id: Optional[str] = None):
        """
        Set a shared context value for worker coordination

        Args:
            key: Context key (e.g., "css_import_pattern", "type_import_style")
            value: Context value (convention, pattern, or decision)
            job_id: Optional job ID to scope context (None for global)

        Example:
            ```python
            # Set global convention
            queue.set_shared_context(
                "css_imports",
                "Always use: import * as styles from './Component.css'"
            )

            # Set job-specific context
            queue.set_shared_context(
                "api_pattern",
                "All API calls use fetch with error handling wrapper",
                job_id="job_abc123"
            )
            ```
        """
        conn = self._get_conn()
        conn.execute("""
            INSERT INTO shared_context (job_id, key, value, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(job_id, key) DO UPDATE SET
                value = excluded.value,
                updated_at = CURRENT_TIMESTAMP
        """, (job_id, key, value))
        conn.commit()

    def get_shared_context(self, job_id: Optional[str] = None) -> Dict[str, str]:
        """
        Get all shared context for workers

        Args:
            job_id: Optional job ID to get job-specific context

        Returns:
            Dictionary of key-value context pairs

        Example:
            ```python
            # Get global context
            context = queue.get_shared_context()
            # {'css_imports': 'import * as styles...', 'type_imports': '...'}

            # Get job-specific context (includes global context)
            context = queue.get_shared_context(job_id="job_abc123")
            ```

        Note:
            Job-specific context includes both job-scoped and global contexts,
            with job-scoped values taking precedence.
        """
        conn = self._get_conn()

        # Get global context
        cursor = conn.execute("""
            SELECT key, value FROM shared_context
            WHERE job_id IS NULL
            ORDER BY updated_at
        """)
        context = {row['key']: row['value'] for row in cursor.fetchall()}

        # Overlay job-specific context if job_id provided
        if job_id:
            cursor = conn.execute("""
                SELECT key, value FROM shared_context
                WHERE job_id = ?
                ORDER BY updated_at
            """, (job_id,))
            context.update({row['key']: row['value'] for row in cursor.fetchall()})

        return context

    def delete_shared_context(self, key: str, job_id: Optional[str] = None):
        """
        Delete a shared context entry

        Args:
            key: Context key to delete
            job_id: Optional job ID to scope deletion (None for global)
        """
        conn = self._get_conn()
        conn.execute("""
            DELETE FROM shared_context
            WHERE key = ? AND job_id IS ?
        """, (key, job_id))
        conn.commit()

    # Task Dependencies API

    def add_task_dependency(self, task_id: int, depends_on_task_id: int):
        """
        Add a dependency between tasks

        Args:
            task_id: Task that depends on another
            depends_on_task_id: Task that must complete first

        Raises:
            ValueError: If circular dependency detected

        Example:
            ```python
            # Task 2 depends on Task 1
            queue.add_task_dependency(task_id=2, depends_on_task_id=1)
            # Worker will not claim task 2 until task 1 is completed
            ```
        """
        # Check for circular dependencies
        if self._has_circular_dependency(task_id, depends_on_task_id):
            raise ValueError(
                f"Circular dependency detected: task {task_id} -> {depends_on_task_id}"
            )

        conn = self._get_conn()
        try:
            conn.execute("""
                INSERT INTO task_dependencies (task_id, depends_on_task_id)
                VALUES (?, ?)
            """, (task_id, depends_on_task_id))
            conn.commit()
        except sqlite3.IntegrityError:
            # Dependency already exists, ignore
            pass

    def get_task_dependencies(self, task_id: int) -> List[int]:
        """
        Get all tasks that this task depends on

        Args:
            task_id: Task to get dependencies for

        Returns:
            List of task IDs that must complete before this task

        Example:
            ```python
            deps = queue.get_task_dependencies(task_id=5)
            # [1, 2, 3] - task 5 depends on tasks 1, 2, and 3
            ```
        """
        conn = self._get_conn()
        cursor = conn.execute("""
            SELECT depends_on_task_id FROM task_dependencies
            WHERE task_id = ?
        """, (task_id,))
        return [row['depends_on_task_id'] for row in cursor.fetchall()]

    def are_dependencies_met(self, task_id: int) -> bool:
        """
        Check if all dependencies for a task are completed

        Args:
            task_id: Task to check

        Returns:
            True if all dependencies are completed, False otherwise

        Example:
            ```python
            if queue.are_dependencies_met(task_id=5):
                # Safe to claim and execute task 5
                task = queue.claim_task(worker_id)
            ```
        """
        conn = self._get_conn()
        cursor = conn.execute("""
            SELECT COUNT(*) as unmet_count
            FROM task_dependencies td
            JOIN tasks t ON td.depends_on_task_id = t.id
            WHERE td.task_id = ?
              AND t.status NOT IN ('completed', 'cancelled')
        """, (task_id,))
        result = cursor.fetchone()
        return result['unmet_count'] == 0

    def _has_circular_dependency(self, task_id: int, depends_on_task_id: int) -> bool:
        """
        Check if adding a dependency would create a cycle

        Args:
            task_id: Task to add dependency to
            depends_on_task_id: Task it would depend on

        Returns:
            True if this would create a circular dependency

        Implementation:
            Uses depth-first search to detect cycles
        """
        # If depends_on_task_id already depends on task_id (directly or indirectly),
        # adding task_id -> depends_on_task_id would create a cycle

        visited = set()
        stack = [depends_on_task_id]

        conn = self._get_conn()

        while stack:
            current = stack.pop()

            if current == task_id:
                # Found a path back to task_id - circular dependency
                return True

            if current in visited:
                continue

            visited.add(current)

            # Get all tasks that current depends on
            cursor = conn.execute("""
                SELECT depends_on_task_id FROM task_dependencies
                WHERE task_id = ?
            """, (current,))

            for row in cursor.fetchall():
                stack.append(row['depends_on_task_id'])

        return False
