#!/usr/bin/env python3
"""
Test suite for resilience and error recovery features (Issue #30)

Tests:
- Checkpoints (save/get/delete)
- Pause/resume functionality
- Retry logic with error context
- File change tracking
- Rollback functionality
- Auto-retry on failure
"""

import os
import sys
import tempfile
import json
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from claude_queue import TaskQueue, TaskStatus
from orchestrator import ClaudeOrchestrator


def test_checkpoint_save_and_get():
    """Test saving and retrieving checkpoints"""
    print("\n=== Test: Checkpoint Save and Get ===")

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        queue = TaskQueue(db_path)

        # Create task
        task_id = queue.add_task("Test task", priority=5)

        # Save checkpoint
        queue.save_checkpoint(
            task_id=task_id,
            checkpoint_data={"phase": "testing", "progress": 50},
            files_created=["src/component.tsx"],
            files_modified=["src/App.tsx"],
            last_step="Created component structure",
            completion_percentage=60
        )

        # Get checkpoint
        checkpoint = queue.get_checkpoint(task_id)

        assert checkpoint is not None
        assert checkpoint['task_id'] == task_id
        assert checkpoint['checkpoint_data']['phase'] == "testing"
        assert "src/component.tsx" in checkpoint['files_created']
        assert "src/App.tsx" in checkpoint['files_modified']
        assert checkpoint['last_step'] == "Created component structure"
        assert checkpoint['completion_percentage'] == 60

        print("✓ Checkpoint save and retrieval works correctly")


def test_pause_and_resume():
    """Test pausing and resuming tasks"""
    print("\n=== Test: Pause and Resume ===")

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        queue = TaskQueue(db_path)

        # Create and claim task
        task_id = queue.add_task("Long running task", priority=5)
        queue.register_worker("worker_1")
        task = queue.claim_task("worker_1")
        assert task is not None

        # Pause task with checkpoint
        queue.pause_task(
            task_id=task_id,
            worker_id="worker_1",
            checkpoint_data={
                "last_step": "Completed 50% of work",
                "next_step": "Continue with remaining work"
            }
        )

        # Verify task is paused
        task = queue.get_task(task_id)
        assert task['status'] == TaskStatus.PAUSED.value

        # Verify checkpoint was saved
        checkpoint = queue.get_checkpoint(task_id)
        assert checkpoint is not None
        assert checkpoint['checkpoint_data']['last_step'] == "Completed 50% of work"

        # Get paused tasks
        paused = queue.get_paused_tasks()
        assert len(paused) == 1
        assert paused[0]['id'] == task_id

        # Resume task (worker claims paused task)
        resumed = queue.claim_task("worker_1")
        assert resumed is not None
        assert resumed['id'] == task_id

        # Check status in database (claim_task returns old status from SELECT)
        task = queue.get_task(task_id)
        assert task['status'] == TaskStatus.RESUMING.value

        print("✓ Pause and resume functionality works correctly")


def test_retry_with_error_context():
    """Test retry logic with error context"""
    print("\n=== Test: Retry with Error Context ===")

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        queue = TaskQueue(db_path)

        # Create task with retries
        original_prompt = "Create TypeScript component"
        task_id = queue.add_task(
            prompt=original_prompt,
            priority=5,
            max_retries=2
        )

        # Register worker and claim task
        queue.register_worker("worker_1")
        task = queue.claim_task("worker_1")
        queue.start_task(task_id, "worker_1")

        # Fail task
        error_msg = "TypeScript error: Property 'foo' does not exist"
        queue.fail_task(task_id, "worker_1", error_msg, auto_retry=False)

        # Check if should retry
        assert queue.should_retry_task(task_id)

        # Manually retry
        retried_id = queue.retry_task(task_id, include_error_context=True)
        assert retried_id == task_id

        # Get task and check prompt includes error context
        task = queue.get_task(task_id)
        assert task['status'] == 'pending'
        assert error_msg in task['prompt']
        assert original_prompt in task['prompt']
        assert task['retry_count'] == 1

        print("✓ Retry with error context works correctly")


def test_auto_retry_on_failure():
    """Test automatic retry on failure"""
    print("\n=== Test: Auto-Retry on Failure ===")

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        queue = TaskQueue(db_path)

        # Create task with retries
        task_id = queue.add_task(
            prompt="Create component",
            priority=5,
            max_retries=2
        )

        # Register worker and execute
        queue.register_worker("worker_1")
        task = queue.claim_task("worker_1")
        queue.start_task(task_id, "worker_1")

        # Fail task with auto_retry=True (default)
        queue.fail_task(task_id, "worker_1", "Build error", auto_retry=True)

        # Task should automatically be reset to pending
        task = queue.get_task(task_id)
        assert task['status'] == 'pending'
        assert task['retry_count'] == 1

        print("✓ Auto-retry on failure works correctly")


def test_max_retries_exceeded():
    """Test that tasks stop retrying after max_retries"""
    print("\n=== Test: Max Retries Exceeded ===")

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        queue = TaskQueue(db_path)

        # Create task with 1 retry
        task_id = queue.add_task(
            prompt="Create component",
            priority=5,
            max_retries=1
        )

        # Register worker
        queue.register_worker("worker_1")

        # First attempt - fail and auto-retry
        task = queue.claim_task("worker_1")
        queue.start_task(task_id, "worker_1")
        queue.fail_task(task_id, "worker_1", "Error 1", auto_retry=True)

        # Should be retried (retry_count = 1)
        task = queue.get_task(task_id)
        assert task['status'] == 'pending'
        assert task['retry_count'] == 1

        # Second attempt - fail again
        task = queue.claim_task("worker_1")
        queue.start_task(task_id, "worker_1")
        queue.fail_task(task_id, "worker_1", "Error 2", auto_retry=True)

        # Should NOT be retried (max_retries exceeded)
        task = queue.get_task(task_id)
        assert task['status'] == 'failed'
        assert task['retry_count'] == 1  # Count doesn't increment past max

        print("✓ Max retries limit works correctly")


def test_file_change_tracking():
    """Test file change tracking for rollback"""
    print("\n=== Test: File Change Tracking ===")

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        queue = TaskQueue(db_path)

        # Create task
        task_id = queue.add_task("Create files", priority=5)

        # Track file changes
        queue.track_file_change(
            task_id=task_id,
            operation='create',
            file_path='src/NewComponent.tsx',
            after_content='const NewComponent = () => {}'
        )

        queue.track_file_change(
            task_id=task_id,
            operation='modify',
            file_path='src/App.tsx',
            before_content='old content',
            after_content='new content'
        )

        # Get changes
        changes = queue.get_task_changes(task_id)
        assert len(changes) == 2

        create_change = changes[0]
        assert create_change['operation'] == 'create'
        assert create_change['file_path'] == 'src/NewComponent.tsx'
        assert create_change['after_content'] == 'const NewComponent = () => {}'

        modify_change = changes[1]
        assert modify_change['operation'] == 'modify'
        assert modify_change['file_path'] == 'src/App.tsx'
        assert modify_change['before_content'] == 'old content'
        assert modify_change['after_content'] == 'new content'

        print("✓ File change tracking works correctly")


def test_rollback():
    """Test rollback functionality"""
    print("\n=== Test: Rollback ===")

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        queue = TaskQueue(db_path)

        # Create task
        task_id = queue.add_task("Modify files", priority=5)

        # Create a test file
        test_file = Path(tmpdir) / "test.txt"
        original_content = "original content"
        test_file.write_text(original_content)

        # Track modification
        modified_content = "modified content"
        queue.track_file_change(
            task_id=task_id,
            operation='modify',
            file_path=str(test_file),
            before_content=original_content,
            after_content=modified_content
        )

        # Actually modify the file
        test_file.write_text(modified_content)
        assert test_file.read_text() == modified_content

        # Rollback
        result = queue.rollback_task(task_id)

        # Verify rollback
        assert len(result['files_restored']) == 1
        assert str(test_file) in result['files_restored']
        assert len(result['errors']) == 0

        # File should be restored
        assert test_file.read_text() == original_content

        print("✓ Rollback functionality works correctly")


def test_orchestrator_retry_api():
    """Test orchestrator retry API"""
    print("\n=== Test: Orchestrator Retry API ===")

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        orch = ClaudeOrchestrator("test_orch", db_path=db_path)

        # Create job with task that has retries
        job_id = orch.create_job("Test job with retries")
        task_id = orch.add_subtask(
            job_id,
            "Create component",
            max_retries=2,
            retry_policy={"backoff": "exponential"}
        )

        # Verify task was created with retry config
        task = orch.queue.get_task(task_id)
        assert task['max_retries'] == 2
        assert json.loads(task['retry_policy'])['backoff'] == "exponential"

        print("✓ Orchestrator retry API works correctly")


def test_claim_task_priority():
    """Test that pending tasks have priority over paused tasks"""
    print("\n=== Test: Task Claim Priority ===")

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        queue = TaskQueue(db_path)

        # Create and pause a high-priority task
        paused_task_id = queue.add_task("Paused high priority", priority=10)
        queue.register_worker("worker_1")
        queue.pause_task(paused_task_id, "worker_1")

        # Create a pending lower-priority task
        pending_task_id = queue.add_task("Pending low priority", priority=5)

        # Worker should claim pending task first
        claimed = queue.claim_task("worker_1")
        assert claimed is not None
        assert claimed['id'] == pending_task_id

        print("✓ Task claim priority works correctly (pending before paused)")


def run_all_tests():
    """Run all tests"""
    print("=" * 60)
    print("Resilience & Error Recovery Tests (Issue #30)")
    print("=" * 60)

    tests = [
        test_checkpoint_save_and_get,
        test_pause_and_resume,
        test_retry_with_error_context,
        test_auto_retry_on_failure,
        test_max_retries_exceeded,
        test_file_change_tracking,
        test_rollback,
        test_orchestrator_retry_api,
        test_claim_task_priority,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"✗ Test {test.__name__} failed: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)

    return failed == 0


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
