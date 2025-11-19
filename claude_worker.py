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
from verification import (
    TaskVerifier,
    VerificationHook,
    ProjectTypeDetector,
    format_verification_error
)

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

    def log_progress(self, message: str, task_id: Optional[int] = None, level: str = 'info'):
        """Log progress message to database for real-time visibility"""
        try:
            self.queue.log_worker_progress(self.worker_id, message, task_id, level)
        except Exception as e:
            # Don't fail the task if logging fails
            print(f"[{self.worker_id}] [WARNING] Failed to log progress: {e}", file=sys.stderr)

    def execute_task(self, task: Dict) -> Dict:
        """Execute a task using Claude Code"""
        task_id = task['id']
        prompt = task['prompt']
        working_dir = task['working_dir'] or os.getcwd()
        context_files = json.loads(task['context_files']) if task['context_files'] else []
        expected_outputs = json.loads(task['expected_outputs']) if task['expected_outputs'] else []

        # Parse metadata for verification hooks
        metadata = json.loads(task['metadata']) if task['metadata'] else {}
        verification_hooks_data = metadata.get('verification_hooks', [])
        verification_hooks = [VerificationHook.from_dict(h) for h in verification_hooks_data]
        auto_verify = metadata.get('auto_verify', True)  # Auto-detect and verify by default

        print(f"[{self.worker_id}] Executing task {task_id}: {prompt[:50]}...")
        self.log_progress(f"Executing: {prompt[:60]}...", task_id=task_id)

        # Get job_id for shared context
        job_id = task.get('job_id')

        # Build comprehensive prompt with context
        full_prompt = f"Task ID: {task_id}\n\n"

        # Inject shared context for worker coordination
        if job_id:
            shared_context = self.queue.get_shared_context(job_id=job_id)
        else:
            shared_context = self.queue.get_shared_context()

        if shared_context:
            full_prompt += "Project Conventions (follow these):\n"
            for key, value in shared_context.items():
                full_prompt += f"- {key}: {value}\n"
            full_prompt += "\n"

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

        try:
            # Execute Claude Code using -p flag for non-interactive mode
            # Use bypassPermissions mode to allow autonomous tool execution
            # Pass prompt via stdin to handle long prompts properly
            result = subprocess.run(
                ['claude', '-p', '--permission-mode', 'bypassPermissions'],
                input=full_prompt,
                cwd=working_dir,
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

            # Validate exit code (Issue #11 fix)
            if result.returncode != 0:
                error_msg = f"Claude CLI exited with code {result.returncode}"
                if result.stderr:
                    error_msg += f": {result.stderr.strip()}"
                output['error'] = error_msg
                return output

            # Initialize verifier
            verifier = TaskVerifier(working_dir)

            # Check for expected output files
            missing_files = []
            if expected_outputs:
                print(f"[{self.worker_id}] [VERIFY] Checking expected outputs...")
                all_exist, file_status = verifier.check_expected_outputs(expected_outputs)
                output['expected_files_present'] = file_status

                if not all_exist:
                    missing_files = [f for f, exists in file_status.items() if not exists]
                    output['error'] = f"Expected output files not created: {', '.join(missing_files)}"
                    return output

            # Auto-detect verification hooks if enabled and none provided
            if auto_verify and not verification_hooks:
                print(f"[{self.worker_id}] [VERIFY] Auto-detecting project type...")
                project_types = ProjectTypeDetector.detect_project_types(working_dir)
                if project_types:
                    print(f"[{self.worker_id}] [VERIFY] Detected project types: {', '.join(project_types)}")
                    verification_hooks = ProjectTypeDetector.get_default_hooks(project_types, working_dir)
                    if verification_hooks:
                        print(f"[{self.worker_id}] [VERIFY] Using {len(verification_hooks)} auto-detected hooks")

            # Run verification hooks
            if verification_hooks:
                print(f"[{self.worker_id}] [VERIFY] Running {len(verification_hooks)} verification hooks...")
                all_passed, verification_results = verifier.verify_task(verification_hooks)

                # Store verification results in output
                output['verification_results'] = [r.to_dict() for r in verification_results]

                if not all_passed:
                    error_msg = format_verification_error(verification_results, missing_files)
                    output['error'] = f"Verification failed:\n{error_msg}"
                    print(f"[{self.worker_id}] [VERIFY] ❌ Verification failed")
                    return output

                print(f"[{self.worker_id}] [VERIFY] ✅ All verifications passed")
            else:
                print(f"[{self.worker_id}] [VERIFY] No verification hooks configured")

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
                self.log_progress(f"Claimed: {task_preview}", task_id=task['id'])

                # Mark as in progress
                self.queue.start_task(task['id'], self.worker_id)
                print(f"[{self.worker_id}] [EXEC] Executing task {task['id']}...")
                self.log_progress("Executing task with Claude CLI", task_id=task['id'])

                # Execute
                result = self.execute_task(task)

                # Mark as complete or failed
                if result.get('error'):
                    print(f"[{self.worker_id}] [FAIL] ❌ Task {task['id']} failed")
                    print(f"[{self.worker_id}] [FAIL] Error: {result['error']}")
                    self.log_progress(f"Task failed: {result['error'][:100]}", task_id=task['id'], level='error')
                    self.queue.fail_task(task['id'], self.worker_id, result['error'])
                else:
                    print(f"[{self.worker_id}] [COMPLETE] ✅ Task {task['id']} completed successfully")
                    if result.get('return_code') is not None:
                        print(f"[{self.worker_id}] [COMPLETE] Exit code: {result['return_code']}")
                    self.log_progress("Task completed successfully", task_id=task['id'])
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
