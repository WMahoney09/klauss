#!/usr/bin/env python3
"""
Claude Code Coordinator
Spawns and manages multiple Claude Code worker instances
"""

import os
import sys
import subprocess
import time
import signal
import argparse
from typing import List, Dict, Optional
from pathlib import Path

from claude_queue import TaskQueue
from config import Config
from utils import get_env_int, get_env_str

class ClaudeCoordinator:
    def __init__(self, num_workers: int = 4, db_path: Optional[str] = None,
                 idle_timeout: int = 300, config: Optional[Config] = None):
        """
        Initialize coordinator

        Args:
            num_workers: Number of workers to spawn
            db_path: Path to task database (overrides config if provided)
            idle_timeout: Seconds of inactivity before auto-shutdown (0 = disabled)
            config: Pre-loaded Config object (optional)
        """
        self.num_workers = num_workers

        # Load config if not provided
        if config is None:
            config = Config.load()
        self.config = config

        # Determine database path with precedence:
        # 1. Explicit db_path argument (highest priority)
        # 2. Config database path (from .klauss.toml or auto-detected)
        if db_path:
            self.db_path = db_path
        else:
            self.db_path = self.config.database.path

        self.queue = TaskQueue(self.db_path)
        self.workers: List[subprocess.Popen] = []
        self.running = True
        self.idle_timeout = idle_timeout
        self.last_activity_time = time.time()

    def spawn_worker(self, worker_id: str) -> subprocess.Popen:
        """Spawn a single worker process"""
        worker_script = Path(__file__).parent / "claude_worker.py"

        # Spawn worker
        process = subprocess.Popen(
            [sys.executable, str(worker_script), worker_id, self.db_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        print(f"Spawned worker {worker_id} (PID: {process.pid})")
        return process

    def monitor_worker_output(self, worker: subprocess.Popen, worker_id: str):
        """Monitor and log worker output (runs in separate thread)"""
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        log_file = log_dir / f"worker_{worker_id}.log"

        with open(log_file, 'w') as f:
            f.write(f"Worker {worker_id} log started\n")
            f.write("=" * 60 + "\n\n")

            for line in worker.stdout:
                f.write(line)
                f.flush()
                print(f"[{worker_id}] {line.rstrip()}")

    def start(self):
        """Start all workers"""
        print(f"Starting {self.num_workers} Claude Code workers...")
        print(f"📁 Database: {self.db_path}")

        # Verify database exists
        db_path = Path(self.db_path)
        if not db_path.exists():
            print(f"⚠️  Warning: Database file does not exist: {self.db_path}")
            print(f"    Make sure the orchestrator has created tasks in this database")
        else:
            db_size = db_path.stat().st_size
            print(f"    Database size: {db_size} bytes")

        print(f"📝 Logs will be written to: logs/worker_*.log")
        print()

        # Cleanup stale tasks from previous runs
        self.queue.cleanup_stale_tasks()

        # Spawn workers
        for i in range(self.num_workers):
            worker_id = f"worker_{i+1}"
            worker = self.spawn_worker(worker_id)
            self.workers.append(worker)

            # Start output monitoring in a thread
            import threading
            thread = threading.Thread(
                target=self.monitor_worker_output,
                args=(worker, worker_id),
                daemon=True
            )
            thread.start()

        print(f"\n{self.num_workers} workers started successfully!")
        print("Press Ctrl+C to stop all workers\n")

        # Setup signal handlers
        def shutdown(signum, frame):
            print("\n\nShutting down workers...")
            self.running = False
            self.stop()

        signal.signal(signal.SIGINT, shutdown)
        signal.signal(signal.SIGTERM, shutdown)

    def monitor(self):
        """Monitor workers and restart if they crash"""
        while self.running:
            time.sleep(5)

            # Check for idle timeout
            if self.idle_timeout > 0:
                stats = self.queue.get_stats()
                active_tasks = stats['pending'] + stats['claimed'] + stats['in_progress']

                if active_tasks > 0:
                    # Tasks are active, update last activity time
                    self.last_activity_time = time.time()
                else:
                    # No active tasks, check idle time
                    idle_duration = time.time() - self.last_activity_time

                    if idle_duration >= self.idle_timeout:
                        print(f"\n⏰ Workers idle for {int(idle_duration)}s (timeout: {self.idle_timeout}s)")
                        print("🛑 Auto-shutting down workers due to inactivity...")
                        self.running = False
                        self.stop()
                        return

            # Check worker processes
            for i, worker in enumerate(self.workers):
                if worker.poll() is not None:
                    # Worker died
                    worker_id = f"worker_{i+1}"
                    print(f"Worker {worker_id} died (exit code: {worker.returncode})")

                    if self.running:
                        print(f"Restarting worker {worker_id}...")
                        self.workers[i] = self.spawn_worker(worker_id)

    def stop(self):
        """Stop all workers"""
        self.running = False

        for worker in self.workers:
            if worker.poll() is None:
                print(f"Stopping worker (PID: {worker.pid})...")
                worker.terminate()

        # Wait for workers to stop (with timeout)
        timeout = 10
        for worker in self.workers:
            try:
                worker.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                print(f"Worker (PID: {worker.pid}) didn't stop, killing...")
                worker.kill()

        print("\nAll workers stopped")

    def run(self):
        """Start and monitor workers"""
        try:
            self.start()
            self.monitor()
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()


if __name__ == '__main__':
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description='Claude Code Parallel Task Coordinator',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Environment Variables:
  KLAUSS_WORKERS       Number of workers to spawn (default: 4)
  KLAUSS_DB_PATH       Path to task database (default: auto-detected)

Examples:
  # Start 10 workers
  python3 claude_coordinator.py --workers 10

  # Start workers with custom database
  python3 claude_coordinator.py --workers 5 --db tasks.db

  # Use environment variables
  KLAUSS_WORKERS=10 KLAUSS_DB_PATH=tasks.db python3 claude_coordinator.py
        '''
    )

    parser.add_argument(
        'workers',
        nargs='?',
        type=int,
        help='Number of workers to spawn (overrides KLAUSS_WORKERS)'
    )
    parser.add_argument(
        'db_path',
        nargs='?',
        help='Path to task database (overrides KLAUSS_DB_PATH)'
    )
    parser.add_argument(
        '--workers', '-w',
        dest='workers_flag',
        type=int,
        help='Number of workers to spawn (alternative to positional argument)'
    )
    parser.add_argument(
        '--db', '--db-path',
        dest='db_path_flag',
        help='Path to task database (alternative to positional argument)'
    )

    args = parser.parse_args()

    # Determine worker count with precedence:
    # 1. --workers flag
    # 2. Positional argument
    # 3. KLAUSS_WORKERS environment variable
    # 4. Default (4)
    num_workers = (
        args.workers_flag or
        args.workers or
        get_env_int('KLAUSS_WORKERS') or
        4
    )

    # Determine database path with precedence:
    # 1. --db flag
    # 2. Positional argument
    # 3. KLAUSS_DB_PATH environment variable
    # 4. None (will use config auto-detection)
    db_path = (
        args.db_path_flag or
        args.db_path or
        get_env_str('KLAUSS_DB_PATH')
    )

    print("=" * 60)
    print("Claude Code Parallel Task Coordinator")
    print("=" * 60)
    print()

    coordinator = ClaudeCoordinator(num_workers, db_path=db_path)
    coordinator.run()
