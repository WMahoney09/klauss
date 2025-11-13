#!/usr/bin/env python3
"""
Claude Code Orchestrator Interface
Allows Claude Code instances to delegate work to worker pool
"""

import uuid
import json
import time
import subprocess
import sys
from typing import List, Dict, Optional, Callable
from pathlib import Path

from claude_queue import TaskQueue
from config import Config, ProjectBoundaryError

class ClaudeOrchestrator:
    """
    Interface for Claude Code to orchestrate parallel task execution

    Usage from Claude Code:
        from orchestrator import ClaudeOrchestrator

        orch = ClaudeOrchestrator("my_orchestrator")
        job = orch.create_job("Build authentication system")

        # Break down into sub-tasks
        orch.add_subtask(job, "Implement user login endpoint", priority=5)
        orch.add_subtask(job, "Implement user registration endpoint", priority=5)
        orch.add_subtask(job, "Write authentication middleware", priority=4)
        orch.add_subtask(job, "Add unit tests for auth endpoints", priority=3)

        # Wait for completion
        results = orch.wait_and_collect(job)

        # Synthesize results
        print(f"All tasks completed! {len(results)} results collected")
    """

    def __init__(self, orchestrator_id: str,
                 db_path: Optional[str] = None,
                 allow_external_dirs: bool = False,
                 use_coordination: bool = False,
                 **config_overrides):
        """
        Initialize orchestrator

        Args:
            orchestrator_id: Unique ID for this orchestrator
            db_path: Explicit database path (overrides config)
            allow_external_dirs: Allow tasks outside project boundaries
            use_coordination: Use shared coordination database from config
            **config_overrides: Additional config overrides
        """
        self.orchestrator_id = orchestrator_id

        # Build config overrides
        overrides = config_overrides.copy()
        if allow_external_dirs:
            overrides.setdefault('safety', {})['allow_external_dirs'] = True

        # Load configuration
        self.config = Config.load(overrides)

        # Determine database path
        if db_path:
            # Explicit path overrides everything
            final_db_path = db_path
        elif use_coordination and self.config.coordination.enabled:
            # Use shared coordination database from config
            final_db_path = self.config.coordination.shared_db
        else:
            # Use auto-detected project database
            final_db_path = self.config.database.path

        self.queue = TaskQueue(final_db_path)
        self.current_job_id: Optional[str] = None

        # Always print database path for debugging
        print(f"📁 Orchestrator '{orchestrator_id}' initialized")
        print(f"   Database: {final_db_path}")

        # Print additional info if detailed logging enabled
        if self.config.monitoring.detailed_logging:
            print(f"   Project: {self.config.project.name}")
            print(f"   Project Root: {self.config.project_root}")

    def check_workers_running(self) -> int:
        """
        Check how many workers are currently running

        Returns:
            Number of active claude_worker.py processes
        """
        try:
            result = subprocess.run(
                ["ps", "aux"],
                capture_output=True,
                text=True,
                timeout=5
            )
            # Count lines with claude_worker.py
            worker_count = result.stdout.count("claude_worker.py")
            return worker_count
        except Exception:
            return 0

    def calculate_optimal_workers(self, job_id: str, max_workers: int = 10) -> int:
        """
        Calculate optimal number of workers based on pending tasks

        Args:
            job_id: Job ID to check
            max_workers: Maximum workers to suggest

        Returns:
            Recommended worker count
        """
        stats = self.queue.get_job_stats(job_id)
        pending_tasks = stats['pending'] + stats['claimed']

        # Optimal = number of parallel tasks, capped at max
        optimal = min(pending_tasks, max_workers)

        # Minimum of 1 worker if any tasks
        return max(1, optimal)

    def start_workers(self, count: int, ask_permission: bool = True) -> bool:
        """
        Start worker processes with optional user confirmation

        Args:
            count: Number of workers to start
            ask_permission: If True, prompt user for confirmation

        Returns:
            True if workers started, False if user declined or error
        """
        if ask_permission:
            response = input(
                f"\n💡 I'd like to start {count} workers for parallel execution.\n"
                f"   This will spawn {count} Claude Code instances to work simultaneously.\n"
                f"   Start workers? (y/n): "
            ).strip().lower()

            if response not in ['y', 'yes']:
                print("⏭️  Skipping parallel execution (workers not started)")
                return False

        print(f"🚀 Starting {count} workers...")

        # Find klauss directory and coordinator script
        if not self.config.klauss_dir:
            print("❌ Error: Could not find klauss directory")
            return False

        coordinator_script = self.config.klauss_dir / "claude_coordinator.py"
        if not coordinator_script.exists():
            print(f"❌ Error: Coordinator script not found: {coordinator_script}")
            return False

        try:
            # Start coordinator in background
            process = subprocess.Popen(
                [sys.executable, str(coordinator_script), str(count), self.queue.db_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True  # Detach from parent
            )

            # Give workers a moment to start
            time.sleep(2)

            # Check if workers are running
            running = self.check_workers_running()
            if running >= count:
                print(f"✅ {running} workers started successfully!")
                return True
            else:
                print(f"⚠️  Started but only detected {running} workers (expected {count})")
                return running > 0

        except Exception as e:
            print(f"❌ Error starting workers: {e}")
            return False

    def ensure_workers_available(self, job_id: str) -> bool:
        """
        Ensure workers are available before executing job.
        Prompts user to start workers if needed.

        Args:
            job_id: Job ID to check

        Returns:
            True if workers are available, False otherwise
        """
        # Check current workers
        current_workers = self.check_workers_running()

        if current_workers > 0:
            print(f"✓ {current_workers} workers already running")
            return True

        # Calculate optimal worker count
        optimal = self.calculate_optimal_workers(job_id)

        print(f"\n📊 Job Analysis:")
        print(f"   - {self.queue.get_job_stats(job_id)['pending']} tasks can run in parallel")
        print(f"   - Suggesting {optimal} workers for optimal execution")

        # Prompt to start workers
        return self.start_workers(optimal, ask_permission=True)

    def stop_workers(self) -> bool:
        """
        Stop all running workers

        Returns:
            True if workers were stopped, False if none running
        """
        worker_count = self.check_workers_running()

        if worker_count == 0:
            print("No workers currently running")
            return False

        print(f"🛑 Stopping {worker_count} workers...")

        try:
            # Kill all claude_worker processes
            subprocess.run(
                ["pkill", "-f", "claude_worker.py"],
                timeout=5
            )

            # Also kill coordinator
            subprocess.run(
                ["pkill", "-f", "claude_coordinator.py"],
                timeout=5
            )

            # Wait a moment and check
            time.sleep(1)
            remaining = self.check_workers_running()

            if remaining == 0:
                print("✅ All workers stopped")
                return True
            else:
                print(f"⚠️  {remaining} workers still running (may need force kill)")
                return False

        except Exception as e:
            print(f"❌ Error stopping workers: {e}")
            return False

    def get_worker_status(self) -> Dict:
        """
        Get detailed status of running workers

        Returns:
            Dict with worker information
        """
        try:
            # Get worker processes
            result = subprocess.run(
                ["ps", "aux"],
                capture_output=True,
                text=True,
                timeout=5
            )

            workers = []
            for line in result.stdout.split('\n'):
                if 'claude_worker.py' in line:
                    parts = line.split()
                    if len(parts) >= 11:
                        workers.append({
                            'pid': parts[1],
                            'cpu': parts[2],
                            'mem': parts[3],
                            'started': ' '.join(parts[8:10]),
                        })

            # Get queue stats
            queue_stats = self.queue.get_stats()
            db_workers = self.queue.get_all_workers()

            return {
                'process_count': len(workers),
                'processes': workers,
                'queue_stats': queue_stats,
                'registered_workers': db_workers
            }

        except Exception as e:
            return {'error': str(e)}

    def create_job(self, description: str, metadata: Optional[Dict] = None) -> str:
        """Create a new job and return job ID"""
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        self.queue.create_job(job_id, description, self.orchestrator_id, metadata)
        self.current_job_id = job_id
        print(f"Created job {job_id}: {description}")
        return job_id

    def add_subtask(self, job_id: str, prompt: str,
                   working_dir: Optional[str] = None,
                   context_files: Optional[List[str]] = None,
                   expected_outputs: Optional[List[str]] = None,
                   priority: Optional[int] = None,
                   parent_task_id: Optional[int] = None,
                   metadata: Optional[Dict] = None,
                   allow_external: bool = False) -> int:
        """
        Add a sub-task to a job

        Args:
            job_id: Job ID to add task to
            prompt: Task description/instruction
            working_dir: Directory where task should execute
            context_files: Files to provide as context
            expected_outputs: Expected output files
            priority: Task priority (uses config default if None)
            parent_task_id: Parent task ID for hierarchical tasks
            metadata: Additional task metadata
            allow_external: Allow this task to work outside project boundaries

        Returns:
            Task ID

        Raises:
            ProjectBoundaryError: If working_dir is outside project and not allowed
        """
        # Use default priority from config if not specified
        if priority is None:
            priority = self.config.defaults.priority

        # Validate working directory
        self.config.validate_working_dir(working_dir, allow_external)

        # Add task to queue
        task_id = self.queue.add_task(
            prompt=prompt,
            working_dir=working_dir,
            context_files=context_files,
            expected_outputs=expected_outputs,
            metadata=metadata,
            priority=priority,
            job_id=job_id,
            parent_task_id=parent_task_id
        )
        print(f"  └─ Task {task_id}: {prompt[:60]}...")
        return task_id

    def get_job_status(self, job_id: str) -> Dict:
        """Get current status of a job"""
        stats = self.queue.get_job_stats(job_id)
        total = sum(stats.values())
        completed = stats['completed']
        failed = stats['failed']
        in_progress = stats['in_progress'] + stats['claimed']
        pending = stats['pending']

        return {
            'job_id': job_id,
            'total_tasks': total,
            'completed': completed,
            'failed': failed,
            'in_progress': in_progress,
            'pending': pending,
            'progress_pct': (completed / total * 100) if total > 0 else 0
        }

    def wait_and_collect(self, job_id: str,
                        poll_interval: Optional[float] = None,
                        timeout: Optional[float] = None,
                        show_progress: Optional[bool] = None,
                        auto_start_workers: bool = True) -> Dict[int, Dict]:
        """
        Wait for all tasks in a job to complete and collect results

        Args:
            job_id: Job ID to wait for
            poll_interval: Seconds between status checks (uses config default if None)
            timeout: Maximum seconds to wait (None = no timeout)
            show_progress: Show progress updates (uses config default if None)
            auto_start_workers: Check and prompt for workers if needed (default: True)

        Returns:
            Dict mapping task_id to result data
        """
        # Use config defaults
        if poll_interval is None:
            poll_interval = self.config.defaults.poll_interval
        if show_progress is None:
            show_progress = self.config.monitoring.progress_updates

        # Check if workers are available (with user prompt if needed)
        if auto_start_workers:
            if not self.ensure_workers_available(job_id):
                print("\n⚠️  Warning: No workers available. Tasks will not execute.")
                print("   You can start workers manually: ./manage.sh start <count>")

        print(f"\nWaiting for job {job_id} to complete...")
        start_time = time.time()

        while True:
            status = self.get_job_status(job_id)

            if show_progress:
                elapsed = int(time.time() - start_time)
                print(f"[{elapsed}s] Progress: {status['completed']}/{status['total_tasks']} tasks "
                      f"({status['progress_pct']:.1f}%) | "
                      f"In Progress: {status['in_progress']} | "
                      f"Pending: {status['pending']} | "
                      f"Failed: {status['failed']}")

            # Check if all done
            if status['in_progress'] + status['pending'] == 0:
                break

            # Check timeout
            if timeout and (time.time() - start_time) > timeout:
                print(f"\nTimeout reached after {timeout}s")
                break

            time.sleep(poll_interval)

        # Collect results
        tasks = self.queue.get_job_tasks(job_id)
        results = {}

        for task in tasks:
            task_id = task['id']
            results[task_id] = {
                'task_id': task_id,
                'prompt': task['prompt'],
                'status': task['status'],
                'result': json.loads(task['result']) if task['result'] else None,
                'error': task['error'],
                'working_dir': task['working_dir'],
                'expected_outputs': json.loads(task['expected_outputs']) if task['expected_outputs'] else None
            }

        # Mark job as complete
        self.queue.complete_job(job_id)

        print(f"\n✓ Job {job_id} completed!")
        print(f"  Total: {status['total_tasks']} | "
              f"Completed: {status['completed']} | "
              f"Failed: {status['failed']}")

        return results

    def get_completed_tasks(self, job_id: str) -> List[Dict]:
        """Get all completed tasks for a job"""
        return self.queue.get_job_tasks(job_id, status='completed')

    def get_failed_tasks(self, job_id: str) -> List[Dict]:
        """Get all failed tasks for a job"""
        return self.queue.get_job_tasks(job_id, status='failed')

    def retry_failed_tasks(self, job_id: str) -> List[int]:
        """Create new tasks for all failed tasks in a job"""
        failed = self.get_failed_tasks(job_id)
        new_task_ids = []

        for task in failed:
            new_task_id = self.add_subtask(
                job_id=job_id,
                prompt=task['prompt'],
                working_dir=task['working_dir'],
                context_files=json.loads(task['context_files']) if task['context_files'] else None,
                expected_outputs=json.loads(task['expected_outputs']) if task['expected_outputs'] else None,
                priority=task['priority'],
                metadata=json.loads(task['metadata']) if task['metadata'] else None
            )
            new_task_ids.append(new_task_id)

        print(f"Retrying {len(new_task_ids)} failed tasks")
        return new_task_ids

    def create_hierarchical_tasks(self, job_id: str, parent_task_id: int,
                                  subtasks: List[Dict]) -> List[int]:
        """
        Create child tasks under a parent task

        Args:
            job_id: The job ID
            parent_task_id: Parent task ID
            subtasks: List of task dictionaries with 'prompt', 'priority', etc.

        Returns:
            List of created task IDs
        """
        task_ids = []
        for subtask in subtasks:
            task_id = self.add_subtask(
                job_id=job_id,
                prompt=subtask['prompt'],
                working_dir=subtask.get('working_dir'),
                context_files=subtask.get('context_files'),
                expected_outputs=subtask.get('expected_outputs'),
                priority=subtask.get('priority', 0),
                parent_task_id=parent_task_id,
                metadata=subtask.get('metadata')
            )
            task_ids.append(task_id)

        return task_ids

    def synthesize_results(self, results: Dict[int, Dict],
                          synthesis_prompt: Optional[str] = None) -> str:
        """
        Helper to format results for synthesis

        Returns a formatted string suitable for passing to Claude for synthesis
        """
        output = []
        output.append("=" * 60)
        output.append("TASK EXECUTION RESULTS")
        output.append("=" * 60)
        output.append("")

        completed = [r for r in results.values() if r['status'] == 'completed']
        failed = [r for r in results.values() if r['status'] == 'failed']

        output.append(f"Summary: {len(completed)} completed, {len(failed)} failed")
        output.append("")

        # Completed tasks
        if completed:
            output.append("COMPLETED TASKS")
            output.append("-" * 60)
            for result in completed:
                output.append(f"\nTask {result['task_id']}: {result['prompt']}")
                output.append(f"Working Dir: {result['working_dir'] or 'N/A'}")

                if result['result']:
                    output.append(f"Return Code: {result['result'].get('return_code', 'N/A')}")

                    if result['result'].get('stdout'):
                        output.append(f"\nOutput:\n{result['result']['stdout'][:500]}")

                    if result['result'].get('expected_files_present'):
                        output.append(f"\nExpected Files: {result['result']['expected_files_present']}")

                output.append("")

        # Failed tasks
        if failed:
            output.append("\nFAILED TASKS")
            output.append("-" * 60)
            for result in failed:
                output.append(f"\nTask {result['task_id']}: {result['prompt']}")
                output.append(f"Error: {result['error']}")
                output.append("")

        # Add synthesis prompt if provided
        if synthesis_prompt:
            output.append("=" * 60)
            output.append("SYNTHESIS REQUEST")
            output.append("=" * 60)
            output.append(synthesis_prompt)

        return "\n".join(output)


# Convenience functions for quick usage
def quick_delegate(tasks: List[str], orchestrator_id: str = "quick_orch",
                   priority: int = 5) -> Dict[int, Dict]:
    """
    Quick delegation for simple parallel tasks

    Example:
        results = quick_delegate([
            "Create a factorial function in Python",
            "Create a fibonacci function in Python",
            "Create a prime checker function in Python"
        ])
    """
    orch = ClaudeOrchestrator(orchestrator_id)
    job_id = orch.create_job(f"Quick parallel execution of {len(tasks)} tasks")

    for task in tasks:
        orch.add_subtask(job_id, task, priority=priority)

    return orch.wait_and_collect(job_id)


if __name__ == '__main__':
    # Example usage
    print("Claude Code Orchestrator - Example Usage")
    print("=" * 60)

    orch = ClaudeOrchestrator("example_orchestrator")

    # Create a job
    job = orch.create_job("Build a simple web application")

    # Add tasks
    orch.add_subtask(job, "Create a simple HTTP server in Python", priority=5)
    orch.add_subtask(job, "Write HTML template for homepage", priority=4)
    orch.add_subtask(job, "Create CSS stylesheet", priority=3)
    orch.add_subtask(job, "Write JavaScript for interactivity", priority=3)

    print("\nTasks submitted. Workers will process them in parallel.")
    print("Run 'python3 claude_coordinator.py 4' to start workers")
    print("Run 'python3 claude_dashboard.py' to monitor progress")
