#!/usr/bin/env python3
"""
Claude Code Real-time Dashboard
Monitor task queue and workers in real-time
"""

import curses
import time
import json
from datetime import datetime
from typing import List, Dict
import sys

from claude_queue import TaskQueue

class Dashboard:
    def __init__(self, db_path: str = "claude_tasks.db"):
        self.queue = TaskQueue(db_path)
        self.running = True

    def format_timestamp(self, ts: str) -> str:
        """Format timestamp for display"""
        if not ts:
            return "-"
        try:
            dt = datetime.fromisoformat(ts)
            return dt.strftime("%H:%M:%S")
        except:
            return ts[:8] if ts else "-"

    def draw_header(self, stdscr, y: int) -> int:
        """Draw header section"""
        height, width = stdscr.getmaxyx()

        title = "Claude Code Parallel Execution Dashboard"
        stdscr.attron(curses.color_pair(1) | curses.A_BOLD)
        stdscr.addstr(y, (width - len(title)) // 2, title)
        stdscr.attroff(curses.color_pair(1) | curses.A_BOLD)

        y += 1
        stdscr.addstr(y, 0, "=" * width)
        y += 2

        return y

    def draw_stats(self, stdscr, y: int, stats: Dict) -> int:
        """Draw statistics section"""
        height, width = stdscr.getmaxyx()

        stdscr.attron(curses.A_BOLD)
        stdscr.addstr(y, 0, "Queue Statistics:")
        stdscr.attroff(curses.A_BOLD)
        y += 1

        # Task stats
        col1_x = 2
        col2_x = 25
        col3_x = 50

        stdscr.addstr(y, col1_x, f"Pending: {stats['pending']}")
        stdscr.addstr(y, col2_x, f"Claimed: {stats['claimed']}")
        stdscr.addstr(y, col3_x, f"In Progress: {stats['in_progress']}")
        y += 1

        stdscr.addstr(y, col1_x, f"Completed: {stats['completed']}")
        stdscr.addstr(y, col2_x, f"Failed: {stats['failed']}")
        stdscr.addstr(y, col3_x, f"Cancelled: {stats['cancelled']}")
        y += 1

        stdscr.attron(curses.color_pair(2))
        stdscr.addstr(y, col1_x, f"Active Workers: {stats['active_workers']}/{stats['total_workers']}")
        stdscr.attroff(curses.color_pair(2))

        y += 2
        return y

    def draw_workers(self, stdscr, y: int, workers: List[Dict]) -> int:
        """Draw workers section"""
        height, width = stdscr.getmaxyx()

        stdscr.attron(curses.A_BOLD)
        stdscr.addstr(y, 0, "Workers:")
        stdscr.attroff(curses.A_BOLD)
        y += 1

        if not workers:
            stdscr.addstr(y, 2, "No workers registered")
            y += 2
            return y

        # Header
        header = f"{'Worker ID':<15} {'Status':<10} {'Task':<8} {'Last Heartbeat':<15}"
        stdscr.addstr(y, 2, header)
        y += 1
        stdscr.addstr(y, 2, "-" * len(header))
        y += 1

        # Workers
        for worker in workers[:10]:  # Limit to 10 workers
            worker_id = worker['worker_id'][:14]
            status = worker['status'][:9]
            task_id = str(worker['current_task_id']) if worker['current_task_id'] else "-"
            heartbeat = self.format_timestamp(worker['last_heartbeat'])

            # Color code status
            if status == 'active':
                stdscr.attron(curses.color_pair(2))
            elif status == 'idle':
                stdscr.attron(curses.color_pair(3))

            line = f"{worker_id:<15} {status:<10} {task_id:<8} {heartbeat:<15}"
            stdscr.addstr(y, 2, line)

            stdscr.attroff(curses.color_pair(2))
            stdscr.attroff(curses.color_pair(3))

            y += 1

        y += 1
        return y

    def draw_tasks(self, stdscr, y: int, tasks: List[Dict]) -> int:
        """Draw recent tasks section"""
        height, width = stdscr.getmaxyx()

        stdscr.attron(curses.A_BOLD)
        stdscr.addstr(y, 0, "Recent Tasks:")
        stdscr.attroff(curses.A_BOLD)
        y += 1

        if not tasks:
            stdscr.addstr(y, 2, "No tasks")
            y += 2
            return y

        # Header
        header = f"{'ID':<6} {'Status':<12} {'Pri':<4} {'Worker':<12} {'Prompt':<40}"
        if y < height - 1:
            stdscr.addstr(y, 2, header[:width-3])
        y += 1

        if y < height - 1:
            stdscr.addstr(y, 2, "-" * min(len(header), width-3))
        y += 1

        # Tasks (most recent first, limit to available space)
        max_tasks = min(height - y - 2, 15)
        for task in tasks[:max_tasks]:
            if y >= height - 1:
                break

            task_id = str(task['id'])
            status = task['status'][:11]
            priority = str(task['priority'])
            worker = (task['worker_id'] or "-")[:11]
            prompt = task['prompt'][:37] + "..." if len(task['prompt']) > 40 else task['prompt']

            # Color code status
            color = 0
            if status == 'completed':
                color = 2  # Green
            elif status == 'failed':
                color = 4  # Red
            elif status == 'in_progress':
                color = 5  # Yellow
            elif status == 'pending':
                color = 3  # Cyan

            if color:
                stdscr.attron(curses.color_pair(color))

            line = f"{task_id:<6} {status:<12} {priority:<4} {worker:<12} {prompt:<40}"
            try:
                stdscr.addstr(y, 2, line[:width-3])
            except curses.error:
                pass

            if color:
                stdscr.attroff(curses.color_pair(color))

            y += 1

        return y

    def draw_footer(self, stdscr):
        """Draw footer"""
        height, width = stdscr.getmaxyx()
        footer = "Press 'q' to quit | Refreshes every 2 seconds"

        try:
            stdscr.attron(curses.A_DIM)
            stdscr.addstr(height - 1, 0, footer[:width-1])
            stdscr.attroff(curses.A_DIM)
        except curses.error:
            pass

    def run(self, stdscr):
        """Main dashboard loop"""
        # Setup colors
        curses.init_pair(1, curses.COLOR_CYAN, curses.COLOR_BLACK)
        curses.init_pair(2, curses.COLOR_GREEN, curses.COLOR_BLACK)
        curses.init_pair(3, curses.COLOR_CYAN, curses.COLOR_BLACK)
        curses.init_pair(4, curses.COLOR_RED, curses.COLOR_BLACK)
        curses.init_pair(5, curses.COLOR_YELLOW, curses.COLOR_BLACK)

        # Setup screen
        curses.curs_set(0)  # Hide cursor
        stdscr.timeout(2000)  # 2 second timeout for getch()
        stdscr.clear()

        while self.running:
            try:
                stdscr.clear()
                height, width = stdscr.getmaxyx()

                # Get data
                stats = self.queue.get_stats()
                workers = self.queue.get_all_workers()
                tasks = self.queue.get_all_tasks()

                # Sort tasks by ID descending (most recent first)
                tasks.sort(key=lambda t: t['id'], reverse=True)

                # Draw sections
                y = 1
                y = self.draw_header(stdscr, y)
                y = self.draw_stats(stdscr, y, stats)
                y = self.draw_workers(stdscr, y, workers)
                y = self.draw_tasks(stdscr, y, tasks)
                self.draw_footer(stdscr)

                stdscr.refresh()

                # Check for quit
                try:
                    key = stdscr.getch()
                    if key == ord('q') or key == ord('Q'):
                        self.running = False
                except:
                    pass

            except KeyboardInterrupt:
                self.running = False
            except Exception as e:
                stdscr.clear()
                stdscr.addstr(0, 0, f"Error: {e}")
                stdscr.refresh()
                time.sleep(2)


def main():
    db_path = sys.argv[1] if len(sys.argv) > 1 else "claude_tasks.db"
    dashboard = Dashboard(db_path)

    try:
        curses.wrapper(dashboard.run)
    except KeyboardInterrupt:
        pass

if __name__ == '__main__':
    main()
