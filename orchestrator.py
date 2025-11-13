#!/usr/bin/env python3
"""
Claude Code Orchestrator Interface
Allows Claude Code instances to delegate work to worker pool
"""

import uuid
import json
import time
from typing import List, Dict, Optional, Callable
from pathlib import Path

from claude_queue import TaskQueue

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

    def __init__(self, orchestrator_id: str, db_path: str = "claude_tasks.db"):
        self.orchestrator_id = orchestrator_id
        self.queue = TaskQueue(db_path)
        self.current_job_id: Optional[str] = None

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
                   priority: int = 0,
                   parent_task_id: Optional[int] = None,
                   metadata: Optional[Dict] = None) -> int:
        """Add a sub-task to a job"""
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

    def wait_and_collect(self, job_id: str, poll_interval: float = 3.0,
                        timeout: Optional[float] = None,
                        show_progress: bool = True) -> Dict[int, Dict]:
        """
        Wait for all tasks in a job to complete and collect results

        Returns:
            Dict mapping task_id to result data
        """
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
