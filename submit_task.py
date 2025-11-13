#!/usr/bin/env python3
"""
Task Submission CLI
Add tasks to the Claude Code task queue
"""

import sys
import json
import argparse
from pathlib import Path
from typing import List, Optional

from claude_queue import TaskQueue

def submit_task(queue: TaskQueue, prompt: str, working_dir: Optional[str] = None,
                context_files: Optional[List[str]] = None,
                expected_outputs: Optional[List[str]] = None,
                metadata: Optional[dict] = None,
                priority: int = 0):
    """Submit a single task"""
    task_id = queue.add_task(
        prompt=prompt,
        working_dir=working_dir,
        context_files=context_files,
        expected_outputs=expected_outputs,
        metadata=metadata,
        priority=priority
    )
    print(f"Task {task_id} submitted successfully")
    return task_id

def submit_from_file(queue: TaskQueue, file_path: str):
    """Submit tasks from a JSON file"""
    with open(file_path) as f:
        data = json.load(f)

    if isinstance(data, dict):
        # Single task
        tasks = [data]
    elif isinstance(data, list):
        # Multiple tasks
        tasks = data
    else:
        raise ValueError("Invalid task file format")

    task_ids = []
    for task in tasks:
        task_id = queue.add_task(
            prompt=task['prompt'],
            working_dir=task.get('working_dir'),
            context_files=task.get('context_files'),
            expected_outputs=task.get('expected_outputs'),
            metadata=task.get('metadata'),
            priority=task.get('priority', 0)
        )
        task_ids.append(task_id)
        print(f"Task {task_id} submitted: {task['prompt'][:50]}...")

    print(f"\n{len(task_ids)} tasks submitted successfully")
    return task_ids

def list_tasks(queue: TaskQueue, status: Optional[str] = None):
    """List all tasks"""
    tasks = queue.get_all_tasks(status)

    if not tasks:
        print("No tasks found")
        return

    print(f"\n{'ID':<6} {'Status':<12} {'Priority':<8} {'Prompt':<50} {'Worker':<10}")
    print("-" * 100)

    for task in tasks:
        task_id = task['id']
        status = task['status']
        priority = task['priority']
        prompt = task['prompt'][:47] + "..." if len(task['prompt']) > 50 else task['prompt']
        worker = task['worker_id'] or "-"

        print(f"{task_id:<6} {status:<12} {priority:<8} {prompt:<50} {worker:<10}")

    print(f"\nTotal: {len(tasks)} tasks")

def show_stats(queue: TaskQueue):
    """Show queue statistics"""
    stats = queue.get_stats()

    print("\nQueue Statistics")
    print("=" * 40)
    print(f"Pending:      {stats['pending']}")
    print(f"Claimed:      {stats['claimed']}")
    print(f"In Progress:  {stats['in_progress']}")
    print(f"Completed:    {stats['completed']}")
    print(f"Failed:       {stats['failed']}")
    print(f"Cancelled:    {stats['cancelled']}")
    print("-" * 40)
    print(f"Total:        {sum(stats[k] for k in stats if k.endswith(('pending', 'claimed', 'in_progress', 'completed', 'failed', 'cancelled')))}")
    print()
    print(f"Active Workers: {stats['active_workers']}")
    print(f"Total Workers:  {stats['total_workers']}")

def show_task(queue: TaskQueue, task_id: int):
    """Show detailed task information"""
    task = queue.get_task(task_id)

    if not task:
        print(f"Task {task_id} not found")
        return

    print(f"\nTask {task_id}")
    print("=" * 60)
    print(f"Status:        {task['status']}")
    print(f"Priority:      {task['priority']}")
    print(f"Worker:        {task['worker_id'] or '-'}")
    print(f"Created:       {task['created_at']}")
    print(f"Claimed:       {task['claimed_at'] or '-'}")
    print(f"Started:       {task['started_at'] or '-'}")
    print(f"Completed:     {task['completed_at'] or '-'}")
    print(f"Working Dir:   {task['working_dir'] or '-'}")
    print()
    print("Prompt:")
    print("-" * 60)
    print(task['prompt'])
    print()

    if task['context_files']:
        print("Context Files:")
        for f in json.loads(task['context_files']):
            print(f"  - {f}")
        print()

    if task['expected_outputs']:
        print("Expected Outputs:")
        for f in json.loads(task['expected_outputs']):
            print(f"  - {f}")
        print()

    if task['result']:
        print("Result:")
        print("-" * 60)
        result = json.loads(task['result'])
        print(json.dumps(result, indent=2))
        print()

    if task['error']:
        print("Error:")
        print("-" * 60)
        print(task['error'])
        print()

def main():
    parser = argparse.ArgumentParser(description='Submit tasks to Claude Code queue')
    parser.add_argument('--db', default='claude_tasks.db', help='Database path')

    subparsers = parser.add_subparsers(dest='command', help='Command')

    # Submit command
    submit_parser = subparsers.add_parser('submit', help='Submit a task')
    submit_parser.add_argument('prompt', help='Task prompt')
    submit_parser.add_argument('--dir', help='Working directory')
    submit_parser.add_argument('--context', nargs='+', help='Context files')
    submit_parser.add_argument('--outputs', nargs='+', help='Expected output files')
    submit_parser.add_argument('--priority', type=int, default=0, help='Task priority')
    submit_parser.add_argument('--metadata', help='JSON metadata')

    # Submit from file
    file_parser = subparsers.add_parser('submit-file', help='Submit tasks from JSON file')
    file_parser.add_argument('file', help='JSON file with tasks')

    # List command
    list_parser = subparsers.add_parser('list', help='List tasks')
    list_parser.add_argument('--status', help='Filter by status')

    # Stats command
    subparsers.add_parser('stats', help='Show queue statistics')

    # Show command
    show_parser = subparsers.add_parser('show', help='Show task details')
    show_parser.add_argument('task_id', type=int, help='Task ID')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    queue = TaskQueue(args.db)

    if args.command == 'submit':
        metadata = json.loads(args.metadata) if args.metadata else None
        submit_task(
            queue,
            args.prompt,
            args.dir,
            args.context,
            args.outputs,
            metadata,
            args.priority
        )
    elif args.command == 'submit-file':
        submit_from_file(queue, args.file)
    elif args.command == 'list':
        list_tasks(queue, args.status)
    elif args.command == 'stats':
        show_stats(queue)
    elif args.command == 'show':
        show_task(queue, args.task_id)

if __name__ == '__main__':
    main()
