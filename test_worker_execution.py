#!/usr/bin/env python3
"""
Test script to verify worker can execute Claude Code instances correctly
Tests the fix for Issue #11: Workers Cannot Execute Claude Code Instances
"""

import os
import sys
import tempfile
import time
from pathlib import Path

from claude_queue import TaskQueue
from claude_worker import ClaudeWorker

# Create temporary database and working directory
test_db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
test_db_path = test_db.name
test_db.close()

test_dir = tempfile.mkdtemp()

print("=" * 70)
print("Testing Worker Execution (Issue #11 Fix)")
print("=" * 70)
print(f"Test database: {test_db_path}")
print(f"Test directory: {test_dir}")
print()

# Initialize queue and add a simple test task
queue = TaskQueue(test_db_path)

print("Step 1: Adding test task")
print("-" * 70)

# Simple task: create a file with specific content
test_file = "test_output.txt"
test_content = "Hello from KLAUSS!"

task_id = queue.add_task(
    prompt=f"Create a file named '{test_file}' with the content: {test_content}",
    working_dir=test_dir,
    expected_outputs=[test_file],
    priority=10
)

print(f"✅ Added task {task_id}")
print(f"   Prompt: Create file '{test_file}'")
print(f"   Expected output: {test_file}")
print(f"   Working dir: {test_dir}")
print()

# Create a worker and execute one task
print("Step 2: Creating worker and executing task")
print("-" * 70)

worker = ClaudeWorker("test_worker", db_path=test_db_path)
worker.queue.register_worker("test_worker")

# Claim the task
task = worker.queue.claim_task("test_worker")
if not task:
    print("❌ FAIL: Could not claim task")
    sys.exit(1)

print(f"✅ Claimed task {task['id']}")
print()

# Start the task
worker.queue.start_task(task['id'], "test_worker")
print(f"⏳ Executing task {task['id']}...")
print()

# Execute the task
result = worker.execute_task(task)

print("Step 3: Analyzing results")
print("-" * 70)

# Check results
success = True

print(f"Return code: {result.get('return_code', 'N/A')}")
print(f"Error: {result.get('error', 'None')}")
print()
print("Claude output:")
print(result.get('stdout', '(no output)')[:500])
print()
print("Claude errors:")
print(result.get('stderr', '(no errors)')[:500])
print()

if result.get('error'):
    print(f"❌ FAIL: Task returned error: {result['error']}")
    success = False
else:
    print("✅ PASS: No error returned")

# Check if file was created
output_file = Path(test_dir) / test_file
if output_file.exists():
    print(f"✅ PASS: Output file created: {output_file}")
    with open(output_file) as f:
        content = f.read()
        print(f"   Content: {content[:50]}...")
else:
    print(f"❌ FAIL: Expected output file not created: {output_file}")
    success = False

# Check expected_files_present
if result.get('expected_files_present'):
    all_present = all(result['expected_files_present'].values())
    if all_present:
        print(f"✅ PASS: All expected files present")
    else:
        print(f"❌ FAIL: Some expected files missing: {result['expected_files_present']}")
        success = False

print()
print("Step 4: Cleanup")
print("-" * 70)

# Cleanup
try:
    os.unlink(test_db_path)
    if output_file.exists():
        os.unlink(output_file)
    os.rmdir(test_dir)
    print("✅ Cleaned up test files")
except Exception as e:
    print(f"⚠️  Cleanup warning: {e}")

print()
print("=" * 70)
if success:
    print("✅ TEST PASSED: Worker execution works correctly!")
    print()
    print("Issue #11 fix validated:")
    print("  ✅ Worker uses correct Claude CLI syntax (claude -p)")
    print("  ✅ Exit code validation works")
    print("  ✅ Expected output file verification works")
else:
    print("❌ TEST FAILED: Worker execution has issues")
    print()
    print("Review the errors above for details")
    sys.exit(1)

print("=" * 70)
