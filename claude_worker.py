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
from config import Config

class ClaudeWorker:
    def __init__(self, worker_id: str, db_path: Optional[str] = None, config: Optional[Config] = None):
        """
        Initialize worker

        Args:
            worker_id: Unique identifier for this worker
            db_path: Explicit database path (overrides config)
            config: Pre-loaded Config object (optional)
        """
        self.worker_id = worker_id

        # Load config if not provided
        if config is None:
            config = Config.load()
        self.config = config

        # Determine database path with precedence:
        # 1. Explicit db_path argument (highest priority)
        # 2. Config database path (from .klauss.toml or auto-detected)
        if db_path:
            final_db_path = db_path
        else:
            final_db_path = self.config.database.path

        self.queue = TaskQueue(final_db_path)
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

    def startup_health_check(self):
        """Validate worker configuration before starting task loop"""
        print(f"[{self.worker_id}] [STARTUP] Performing health check...")

        # 1. Check database exists and is accessible
        db_path = Path(self.queue.db_path)
        if not db_path.exists():
            print(f"[{self.worker_id}] [ERROR] ❌ Database file does not exist: {self.queue.db_path}")
            print(f"[{self.worker_id}] [ERROR]")
            print(f"[{self.worker_id}] [ERROR] This usually means the orchestrator hasn't created tasks yet,")
            print(f"[{self.worker_id}] [ERROR] or workers and orchestrator are using different databases.")
            print(f"[{self.worker_id}] [ERROR]")
            print(f"[{self.worker_id}] [ERROR] Suggestions:")
            print(f"[{self.worker_id}] [ERROR]   1. Run the orchestrator first to create tasks")
            print(f"[{self.worker_id}] [ERROR]   2. Check database path configuration in .klauss.toml")
            print(f"[{self.worker_id}] [ERROR]   3. Ensure orchestrator and workers run from same project root")
            sys.exit(1)

        # 2. Check database size
        db_size = db_path.stat().st_size
        print(f"[{self.worker_id}] [CONFIG] Database: {self.queue.db_path}")
        print(f"[{self.worker_id}] [CONFIG] Database size: {db_size} bytes")

        # 3. Test database connection
        try:
            self.queue._get_conn().execute("SELECT 1")
            print(f"[{self.worker_id}] [CONFIG] ✅ Database connection successful")
        except Exception as e:
            print(f"[{self.worker_id}] [ERROR] ❌ Cannot connect to database: {e}")
            sys.exit(1)

        # 4. Check for pending tasks
        try:
            pending = self.queue.list_tasks(status='pending')
            print(f"[{self.worker_id}] [CONFIG] Pending tasks visible: {len(pending)}")

            if len(pending) == 0:
                print(f"[{self.worker_id}] [WARNING] ⚠️  No pending tasks found")
                print(f"[{self.worker_id}] [WARNING] Worker will wait for new tasks...")
            else:
                print(f"[{self.worker_id}] [CONFIG] ✅ Tasks are available to claim")
        except Exception as e:
            print(f"[{self.worker_id}] [ERROR] ❌ Error checking tasks: {e}")
            sys.exit(1)

        # 5. Log working directory
        print(f"[{self.worker_id}] [CONFIG] Working directory: {os.getcwd()}")

        print(f"[{self.worker_id}] [STARTUP] ✅ Health check passed")

    def run(self):
        """Main worker loop"""
        print(f"[{self.worker_id}] [STARTUP] Starting worker")
        print(f"[{self.worker_id}] [STARTUP] Worker ID: {self.worker_id}")

        # Perform startup health check
        self.startup_health_check()

        # Register worker
        self.queue.register_worker(self.worker_id)
        print(f"[{self.worker_id}] [STARTUP] ✅ Worker registered")

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
                    print(f"[{self.worker_id}] [IDLE] No tasks available, waiting...")
                    time.sleep(2)
                    continue

                # Execute task
                self.current_task_id = task['id']
                task_preview = task['prompt'][:60] + "..." if len(task['prompt']) > 60 else task['prompt']
                print(f"[{self.worker_id}] [CLAIM] ✅ Claimed task {task['id']}")
                print(f"[{self.worker_id}] [CLAIM] Prompt: {task_preview}")

                # Mark as in progress
                self.queue.start_task(task['id'], self.worker_id)
                print(f"[{self.worker_id}] [EXEC] Executing task {task['id']}...")

                # Execute
                result = self.execute_task(task)

                # Mark as complete or failed
                if result.get('error'):
                    print(f"[{self.worker_id}] [FAIL] ❌ Task {task['id']} failed")
                    print(f"[{self.worker_id}] [FAIL] Error: {result['error']}")
                    self.queue.fail_task(task['id'], self.worker_id, result['error'])
                else:
                    print(f"[{self.worker_id}] [COMPLETE] ✅ Task {task['id']} completed successfully")
                    if result.get('return_code') is not None:
                        print(f"[{self.worker_id}] [COMPLETE] Exit code: {result['return_code']}")
                    self.queue.complete_task(task['id'], self.worker_id, result)

                self.current_task_id = None

            except Exception as e:
                print(f"[{self.worker_id}] [ERROR] ❌ Error in main loop: {e}", file=sys.stderr)
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

        print(f"[{self.worker_id}] [SHUTDOWN] Worker stopped")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: claude_worker.py <worker_id> [db_path]")
        sys.exit(1)

    worker_id = sys.argv[1]

    # Explicit db_path argument takes precedence over config
    db_path = sys.argv[2] if len(sys.argv) > 2 else None

    worker = ClaudeWorker(worker_id, db_path=db_path)
    worker.run()
