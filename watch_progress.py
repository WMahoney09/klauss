#!/usr/bin/env python3
"""
KLAUSS Progress Watcher

Real-time display of worker progress and task execution status
Uses the public API for database access
"""

import sys
import time
import argparse
from pathlib import Path
from typing import Optional
from datetime import datetime

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from claude_queue import TaskQueue
from config import Config


class ProgressWatcher:
    """Real-time progress display for KLAUSS workers"""

    def __init__(self, db_path: Optional[str] = None, job_id: Optional[str] = None):
        """
        Initialize progress watcher

        Args:
            db_path: Database path (uses config if not specified)
            job_id: Optional job ID to filter progress display
        """
        if db_path:
            self.queue = TaskQueue(db_path)
        else:
            config = Config.load()
            self.queue = TaskQueue(config.database.path)

        self.job_id = job_id

    def clear_screen(self):
        """Clear terminal screen"""
        print("\033[2J\033[H", end='')

    def format_timestamp(self, timestamp_str: Optional[str]) -> str:
        """Format timestamp for display"""
        if not timestamp_str:
            return "N/A"
        try:
            dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
            delta = now - dt
            seconds = int(delta.total_seconds())

            if seconds < 60:
                return f"{seconds}s ago"
            elif seconds < 3600:
                return f"{seconds // 60}m ago"
            else:
                return f"{seconds // 3600}h ago"
        except:
            return timestamp_str[:19] if len(timestamp_str) > 19 else timestamp_str

    def display_overall_stats(self):
        """Display overall task statistics"""
        stats = self.queue.get_stats()
        total = sum(stats.values())

        print("=" * 80)
        print(f"{'KLAUSS Progress Monitor':^80}")
        print("=" * 80)
        print()
        print(f"{'Overall Statistics':^80}")
        print("-" * 80)

        if total > 0:
            completed_pct = (stats['completed'] / total) * 100
            print(f"  Total Tasks:       {total}")
            print(f"  Completed:         {stats['completed']:>4} ({completed_pct:>5.1f}%)")
            print(f"  In Progress:       {stats['in_progress']:>4}")
            print(f"  Pending:           {stats['pending']:>4}")
            print(f"  Failed:            {stats['failed']:>4}")
        else:
            print("  No tasks in queue")

        print()

    def display_active_workers(self):
        """Display active worker status"""
        progress = self.queue.get_active_progress()

        print(f"{'Active Workers':^80}")
        print("-" * 80)

        if not progress:
            print("  No active workers")
        else:
            for worker in progress:
                status_icon = "🟢" if worker['status'] == 'active' else "⚪"
                print(f"  {status_icon} {worker['worker_id']:<15}", end=" ")

                if worker['current_task_id']:
                    task_preview = worker['task_prompt'][:40] + "..." if worker['task_prompt'] and len(worker['task_prompt']) > 40 else (worker['task_prompt'] or "N/A")
                    print(f"Task {worker['current_task_id']}: {task_preview}")

                    if worker['recent_log']:
                        log_preview = worker['recent_log'][:50] + "..." if len(worker['recent_log']) > 50 else worker['recent_log']
                        print(f"  {'':>17} └─ {log_preview}")
                else:
                    print("Idle")

        print()

    def display_recent_logs(self, limit: int = 10):
        """Display recent log messages"""
        logs = self.queue.get_worker_logs(limit=limit)

        print(f"{'Recent Activity':^80}")
        print("-" * 80)

        if not logs:
            print("  No recent activity")
        else:
            for log in logs:
                timestamp = self.format_timestamp(log['timestamp'])
                level_icon = {
                    'info': 'ℹ️ ',
                    'warning': '⚠️ ',
                    'error': '❌'
                }.get(log['level'], '  ')

                message = log['message'][:60] + "..." if len(log['message']) > 60 else log['message']

                task_info = f"[Task {log['task_id']}]" if log['task_id'] else "[General]"
                print(f"  {level_icon} {timestamp:>10} | {log['worker_id']:<12} {task_info:>12} | {message}")

        print()

    def display_job_progress(self):
        """Display progress for specific job"""
        if not self.job_id:
            return

        try:
            progress = self.queue.get_job_progress(self.job_id)

            print(f"{'Job Progress':^80}")
            print("-" * 80)

            job_info = progress['job_info']
            stats = progress['stats']

            print(f"  Job ID:       {job_info['job_id']}")
            print(f"  Description:  {job_info['description']}")
            print(f"  Status:       {job_info['status']}")
            print()

            total = sum(stats.values())
            if total > 0:
                completed_pct = (stats['completed'] / total) * 100
                print(f"  Progress: [{stats['completed']}/{total}] ({completed_pct:.1f}%)")
                print(f"  ▰" * int(completed_pct / 2) + f"▱" * (50 - int(completed_pct / 2)))
                print()

            # Active tasks for this job
            if progress['active_tasks']:
                print(f"  Active Tasks:")
                for task in progress['active_tasks']:
                    task_preview = task['prompt'][:50] + "..." if len(task['prompt']) > 50 else task['prompt']
                    print(f"    • Task {task['id']} ({task['worker_id']}): {task_preview}")
                print()

            # Recent logs for this job
            if progress['recent_logs']:
                print(f"  Recent Logs:")
                for log in progress['recent_logs'][:5]:
                    timestamp = self.format_timestamp(log['timestamp'])
                    message = log['message'][:55] + "..." if len(log['message']) > 55 else log['message']
                    print(f"    {timestamp:>10} | {log['worker_id']}: {message}")
                print()

        except Exception as e:
            print(f"  Error displaying job progress: {e}")
            print()

    def watch(self, interval: float = 2.0):
        """
        Watch progress in real-time

        Args:
            interval: Refresh interval in seconds
        """
        print("KLAUSS Progress Monitor")
        print("Press Ctrl+C to exit")
        print()
        time.sleep(1)

        try:
            while True:
                self.clear_screen()
                self.display_overall_stats()

                if self.job_id:
                    self.display_job_progress()
                else:
                    self.display_active_workers()
                    self.display_recent_logs()

                print("-" * 80)
                print(f"Refreshing every {interval}s... (Ctrl+C to exit)")

                time.sleep(interval)

        except KeyboardInterrupt:
            print("\n\nStopped monitoring.")
            sys.exit(0)

    def show_current(self):
        """Show current status (one-time display, no watching)"""
        self.display_overall_stats()

        if self.job_id:
            self.display_job_progress()
        else:
            self.display_active_workers()
            self.display_recent_logs()


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Watch KLAUSS worker progress in real-time',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Watch all worker progress
  python3 watch_progress.py

  # Watch progress for a specific job
  python3 watch_progress.py --job job_abc123

  # One-time status display (no live updates)
  python3 watch_progress.py --once

  # Custom refresh interval
  python3 watch_progress.py --interval 5

  # Custom database path
  python3 watch_progress.py --db /path/to/tasks.db
        '''
    )

    parser.add_argument(
        '--db', '--db-path',
        dest='db_path',
        help='Path to task database'
    )
    parser.add_argument(
        '--job',
        help='Show progress for specific job ID'
    )
    parser.add_argument(
        '--interval',
        type=float,
        default=2.0,
        help='Refresh interval in seconds (default: 2.0)'
    )
    parser.add_argument(
        '--once',
        action='store_true',
        help='Show status once and exit (no live updates)'
    )

    args = parser.parse_args()

    watcher = ProgressWatcher(db_path=args.db_path, job_id=args.job)

    if args.once:
        watcher.show_current()
    else:
        watcher.watch(interval=args.interval)


if __name__ == '__main__':
    main()
