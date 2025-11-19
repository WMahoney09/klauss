#!/usr/bin/env python3
"""
Rollback utility for Klauss tasks

Rolls back file changes made by a task, restoring the state to before task execution.
"""

import sys
import argparse
from pathlib import Path

from claude_queue import TaskQueue
from config import Config


def rollback_task_cli():
    """CLI for rolling back task changes"""
    parser = argparse.ArgumentParser(
        description="Rollback file changes made by a Klauss task"
    )
    parser.add_argument(
        "task_id",
        type=int,
        help="Task ID to rollback"
    )
    parser.add_argument(
        "--db",
        dest="db_path",
        help="Database path (uses config default if not specified)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be rolled back without actually doing it"
    )

    args = parser.parse_args()

    # Determine database path
    if args.db_path:
        db_path = args.db_path
    else:
        config = Config.load()
        db_path = config.database.path

    # Initialize queue
    queue = TaskQueue(db_path)

    # Get task info
    task = queue.get_task(args.task_id)
    if not task:
        print(f"❌ Task {args.task_id} not found")
        sys.exit(1)

    print(f"Task {args.task_id}: {task['prompt'][:60]}...")
    print(f"Status: {task['status']}")
    print()

    # Get changes
    changes = queue.get_task_changes(args.task_id)

    if not changes:
        print(f"⚠️  No tracked changes found for task {args.task_id}")
        print("This task did not track file changes during execution.")
        sys.exit(0)

    print(f"Found {len(changes)} file changes:")
    print()

    # Show changes
    for change in changes:
        operation = change['operation']
        file_path = change['file_path']

        if operation == 'create':
            print(f"  🗑️  DELETE: {file_path}")
        elif operation == 'modify':
            print(f"  ↩️  RESTORE: {file_path}")
        elif operation == 'delete':
            print(f"  ✨ RECREATE: {file_path}")

    print()

    if args.dry_run:
        print("🔍 DRY RUN - No changes were made")
        sys.exit(0)

    # Confirm rollback
    response = input("Proceed with rollback? (y/N): ").strip().lower()
    if response not in ['y', 'yes']:
        print("❌ Rollback cancelled")
        sys.exit(0)

    # Perform rollback
    print()
    print("Rolling back changes...")
    result = queue.rollback_task(args.task_id)

    # Show results
    print()
    if result['files_restored']:
        print(f"✅ Restored {len(result['files_restored'])} files:")
        for file_path in result['files_restored']:
            print(f"   - {file_path}")

    if result['files_deleted']:
        print(f"🗑️  Deleted {len(result['files_deleted'])} files:")
        for file_path in result['files_deleted']:
            print(f"   - {file_path}")

    if result['errors']:
        print(f"⚠️  {len(result['errors'])} errors:")
        for error in result['errors']:
            print(f"   - {error}")

    print()
    if result['errors']:
        print("⚠️  Rollback completed with errors")
        sys.exit(1)
    else:
        print("✅ Rollback completed successfully")
        sys.exit(0)


if __name__ == '__main__':
    rollback_task_cli()
