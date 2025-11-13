#!/usr/bin/env python3
"""
Test script for list_tasks() and list_workers() methods
Tests the fix for Issue #3: Missing list_tasks() method in TaskQueue API
"""

import os
import tempfile
from pathlib import Path

from claude_queue import TaskQueue
from orchestrator import ClaudeOrchestrator

# Create a temporary database for testing
test_db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
test_db_path = test_db.name
test_db.close()

print("=" * 60)
print("Test 1: list_tasks() method exists")
print("=" * 60)

queue = TaskQueue(test_db_path)
print(f"✅ TaskQueue has list_tasks: {hasattr(queue, 'list_tasks')}")
print(f"✅ TaskQueue has list_workers: {hasattr(queue, 'list_workers')}")
print()

# Test 2: Add some tasks
print("=" * 60)
print("Test 2: Add tasks and list them")
print("=" * 60)

task1_id = queue.add_task("Task 1", priority=10, metadata={'test': True})
task2_id = queue.add_task("Task 2", priority=5, metadata={'test': True})
task3_id = queue.add_task("Task 3", priority=1, metadata={'test': True})

print(f"Added tasks: {task1_id}, {task2_id}, {task3_id}")

# List all tasks
all_tasks = queue.list_tasks()
print(f"Total tasks: {len(all_tasks)}")
print(f"✅ list_tasks() works without arguments")
print()

# Test 3: Filter by status
print("=" * 60)
print("Test 3: Filter tasks by status")
print("=" * 60)

pending_tasks = queue.list_tasks(status='pending')
print(f"Pending tasks: {len(pending_tasks)}")
for task in pending_tasks:
    print(f"  - Task {task['id']}: {task['prompt']} (priority: {task['priority']})")

completed_tasks = queue.list_tasks(status='completed')
print(f"Completed tasks: {len(completed_tasks)}")
print(f"✅ list_tasks(status='pending') works")
print()

# Test 4: List tasks for a job
print("=" * 60)
print("Test 4: List tasks for a specific job")
print("=" * 60)

job_id = "test_job_123"
queue.create_job(job_id, "Test job", "test_orchestrator")
queue.add_task("Job task 1", priority=10, job_id=job_id)
queue.add_task("Job task 2", priority=5, job_id=job_id)

job_tasks = queue.list_tasks(job_id=job_id)
print(f"Tasks for job '{job_id}': {len(job_tasks)}")
for task in job_tasks:
    print(f"  - Task {task['id']}: {task['prompt']}")

print(f"✅ list_tasks(job_id='{job_id}') works")
print()

# Test 5: Combine filters
print("=" * 60)
print("Test 5: Combine status and job_id filters")
print("=" * 60)

filtered_tasks = queue.list_tasks(status='pending', job_id=job_id)
print(f"Pending tasks for job '{job_id}': {len(filtered_tasks)}")
print(f"✅ list_tasks(status='pending', job_id='{job_id}') works")
print()

# Test 6: list_workers()
print("=" * 60)
print("Test 6: list_workers() method")
print("=" * 60)

queue.register_worker("worker_1")
queue.register_worker("worker_2")

workers = queue.list_workers()
print(f"Registered workers: {len(workers)}")
for worker in workers:
    print(f"  - {worker['worker_id']}: {worker['status']}")

print(f"✅ list_workers() works")
print()

# Test 7: Use with Orchestrator
print("=" * 60)
print("Test 7: Use list_tasks() via Orchestrator")
print("=" * 60)

orch = ClaudeOrchestrator("test_orch", db_path=test_db_path)
job = orch.create_job("Orchestrator test job")
orch.add_subtask(job, "Orch task 1", priority=10)
orch.add_subtask(job, "Orch task 2", priority=5)

# This is the exact usage from the issue report
tasks = orch.queue.list_tasks(status='pending')
print(f"✅ orch.queue.list_tasks(status='pending') works!")
print(f"   Found {len(tasks)} pending tasks")
print()

# Cleanup
os.unlink(test_db_path)

print("=" * 60)
print("✅ All tests passed!")
print("=" * 60)
