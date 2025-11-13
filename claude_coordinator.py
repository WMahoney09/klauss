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
from typing import List, Dict
from pathlib import Path

from claude_queue import TaskQueue

class ClaudeCoordinator:
    def __init__(self, num_workers: int = 4, db_path: str = "claude_tasks.db"):
        self.num_workers = num_workers
        self.db_path = db_path
        self.queue = TaskQueue(db_path)
        self.workers: List[subprocess.Popen] = []
        self.running = True

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
        print(f"Database: {self.db_path}")
        print(f"Logs will be written to: logs/worker_*.log")
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
    num_workers = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    db_path = sys.argv[2] if len(sys.argv) > 2 else "claude_tasks.db"

    print("=" * 60)
    print("Claude Code Parallel Task Coordinator")
    print("=" * 60)
    print()

    coordinator = ClaudeCoordinator(num_workers, db_path)
    coordinator.run()
