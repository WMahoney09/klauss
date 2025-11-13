#!/usr/bin/env python3
"""
Claude Code Worker
Executes tasks from the queue using Claude Code CLI
"""

import os
import sys
import time
import json
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Optional, Dict
import signal

from claude_queue import TaskQueue

class ClaudeWorker:
    def __init__(self, worker_id: str, db_path: str = "claude_tasks.db"):
        self.worker_id = worker_id
        self.queue = TaskQueue(db_path)
        self.current_task_id: Optional[int] = None
        self.running = True
        self.heartbeat_thread = None

    def start_heartbeat(self):
        """Start heartbeat thread"""
        def heartbeat():
            while self.running:
                try:
                    status = 'active' if self.current_task_id else 'idle'
                    self.queue.update_worker_heartbeat(
                        self.worker_id, status, self.current_task_id
                    )
                except Exception as e:
                    print(f"[{self.worker_id}] Heartbeat error: {e}", file=sys.stderr)
                time.sleep(5)

        self.heartbeat_thread = threading.Thread(target=heartbeat, daemon=True)
        self.heartbeat_thread.start()

    def execute_task(self, task: Dict) -> Dict:
        """Execute a task using Claude Code"""
        task_id = task['id']
        prompt = task['prompt']
        working_dir = task['working_dir'] or os.getcwd()
        context_files = json.loads(task['context_files']) if task['context_files'] else []
        expected_outputs = json.loads(task['expected_outputs']) if task['expected_outputs'] else []

        print(f"[{self.worker_id}] Executing task {task_id}: {prompt[:50]}...")

        # Build Claude Code command
        # We'll use a temp file to pass the full prompt with context
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            # Build comprehensive prompt with context
            full_prompt = f"Task ID: {task_id}\n\n"

            if context_files:
                full_prompt += "Context files to review:\n"
                for file_path in context_files:
                    full_prompt += f"- {file_path}\n"
                full_prompt += "\n"

            if expected_outputs:
                full_prompt += "Expected outputs:\n"
                for output in expected_outputs:
                    full_prompt += f"- {output}\n"
                full_prompt += "\n"

            full_prompt += f"Task:\n{prompt}\n\n"
            full_prompt += "Please complete this task. When done, respond with 'TASK_COMPLETE'."

            f.write(full_prompt)
            prompt_file = f.name

        try:
            # Execute Claude Code
            # Note: We assume 'claude' is in PATH
            result = subprocess.run(
                ['claude', '--message', full_prompt, '--working-dir', working_dir],
                capture_output=True,
                text=True,
                timeout=1800  # 30 minute timeout
            )

            # Parse results
            output = {
                'stdout': result.stdout,
                'stderr': result.stderr,
                'return_code': result.returncode,
                'working_dir': working_dir
            }

            # Check for expected outputs
            if expected_outputs:
                output['expected_files_present'] = {}
                for expected_file in expected_outputs:
                    file_path = Path(working_dir) / expected_file
                    output['expected_files_present'][expected_file] = file_path.exists()

            return output

        except subprocess.TimeoutExpired:
            return {
                'error': 'Task execution timeout (30 minutes)',
                'timeout': True
            }
        except Exception as e:
            return {
                'error': str(e),
                'exception_type': type(e).__name__
            }
        finally:
            # Cleanup temp file
            try:
                os.unlink(prompt_file)
            except:
                pass

    def run(self):
        """Main worker loop"""
        print(f"[{self.worker_id}] Starting worker")
        print(f"[{self.worker_id}] Database: {self.queue.db_path}")

        # Verify database exists and is accessible
        db_path = Path(self.queue.db_path)
        if not db_path.exists():
            print(f"[{self.worker_id}] ⚠️  Warning: Database file does not exist yet: {self.queue.db_path}")
            print(f"[{self.worker_id}] Database will be created on first connection")
        else:
            db_size = db_path.stat().st_size
            print(f"[{self.worker_id}] Database size: {db_size} bytes")

        # Register worker
        self.queue.register_worker(self.worker_id)

        # Start heartbeat
        self.start_heartbeat()

        # Setup signal handlers
        def shutdown(signum, frame):
            print(f"\n[{self.worker_id}] Shutting down...")
            self.running = False

        signal.signal(signal.SIGINT, shutdown)
        signal.signal(signal.SIGTERM, shutdown)

        # Main loop
        while self.running:
            try:
                # Claim next task
                task = self.queue.claim_task(self.worker_id)

                if not task:
                    # No tasks available, wait a bit
                    print(f"[{self.worker_id}] No tasks available, waiting...")
                    time.sleep(2)
                    continue

                # Execute task
                self.current_task_id = task['id']
                print(f"[{self.worker_id}] Claimed task {task['id']}")

                # Mark as in progress
                self.queue.start_task(task['id'], self.worker_id)

                # Execute
                result = self.execute_task(task)

                # Mark as complete or failed
                if result.get('error'):
                    print(f"[{self.worker_id}] Task {task['id']} failed: {result['error']}")
                    self.queue.fail_task(task['id'], self.worker_id, result['error'])
                else:
                    print(f"[{self.worker_id}] Task {task['id']} completed successfully")
                    self.queue.complete_task(task['id'], self.worker_id, result)

                self.current_task_id = None

            except Exception as e:
                print(f"[{self.worker_id}] Error in main loop: {e}", file=sys.stderr)
                if self.current_task_id:
                    try:
                        self.queue.fail_task(
                            self.current_task_id,
                            self.worker_id,
                            f"Worker error: {e}"
                        )
                    except:
                        pass
                    self.current_task_id = None
                time.sleep(5)

        print(f"[{self.worker_id}] Worker stopped")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: claude_worker.py <worker_id> [db_path]")
        sys.exit(1)

    worker_id = sys.argv[1]

    # Determine database path with proper precedence:
    # 1. Explicit argument (highest priority)
    # 2. KLAUSS_DB_PATH environment variable
    # 3. Default to "claude_tasks.db"
    if len(sys.argv) > 2:
        db_path = sys.argv[2]
    elif 'KLAUSS_DB_PATH' in os.environ:
        db_path = os.environ['KLAUSS_DB_PATH']
        print(f"Using database from KLAUSS_DB_PATH: {db_path}")
    else:
        db_path = "claude_tasks.db"
        print(f"Using default database: {db_path}")
        print(f"Tip: Set KLAUSS_DB_PATH environment variable or pass db_path as argument")

    worker = ClaudeWorker(worker_id, db_path)
    worker.run()
