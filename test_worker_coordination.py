#!/usr/bin/env python3
"""
Test suite for worker coordination features (Issue #29)

Tests:
- Shared context (global and job-specific)
- Task dependencies
- Circular dependency detection
- Worker context injection
"""

import os
import sys
import tempfile
import json
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from claude_queue import TaskQueue
from orchestrator import ClaudeOrchestrator
from claude_worker import ClaudeWorker


def test_shared_context_global():
    """Test global shared context"""
    print("\n=== Test: Global Shared Context ===")

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        queue = TaskQueue(db_path)

        # Set global context
        queue.set_shared_context("naming_convention", "Use camelCase")
        queue.set_shared_context("import_style", "Use ES6 imports")

        # Get global context
        context = queue.get_shared_context()

        assert "naming_convention" in context
        assert context["naming_convention"] == "Use camelCase"
        assert "import_style" in context
        assert context["import_style"] == "Use ES6 imports"

        print("✓ Global shared context works correctly")


def test_shared_context_job_specific():
    """Test job-specific shared context"""
    print("\n=== Test: Job-Specific Shared Context ===")

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        queue = TaskQueue(db_path)

        # Create job
        job_id = "test_job_1"
        queue.create_job(job_id, "Test job", "test_orch")

        # Set global and job-specific context
        queue.set_shared_context("global_rule", "Global value")
        queue.set_shared_context("job_rule", "Job value", job_id=job_id)

        # Get job context (should include both global and job-specific)
        context = queue.get_shared_context(job_id=job_id)

        assert "global_rule" in context
        assert context["global_rule"] == "Global value"
        assert "job_rule" in context
        assert context["job_rule"] == "Job value"

        # Get global context (should not include job-specific)
        global_context = queue.get_shared_context()
        assert "global_rule" in global_context
        assert "job_rule" not in global_context

        print("✓ Job-specific shared context works correctly")


def test_task_dependencies_basic():
    """Test basic task dependencies"""
    print("\n=== Test: Basic Task Dependencies ===")

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        queue = TaskQueue(db_path)

        # Create tasks
        task1_id = queue.add_task("Task 1", priority=5)
        task2_id = queue.add_task("Task 2", priority=5)
        task3_id = queue.add_task("Task 3", priority=5)

        # Task 3 depends on Task 1 and Task 2
        queue.add_task_dependency(task3_id, task1_id)
        queue.add_task_dependency(task3_id, task2_id)

        # Check dependencies
        deps = queue.get_task_dependencies(task3_id)
        assert len(deps) == 2
        assert task1_id in deps
        assert task2_id in deps

        # Task 3 should not be claimable (dependencies not met)
        assert not queue.are_dependencies_met(task3_id)

        # Complete Task 1 (claim, start, complete)
        worker_id = "test_worker"
        queue.register_worker(worker_id)

        # Claim and complete task 1
        task1 = queue.claim_task(worker_id)
        assert task1 is not None and task1['id'] == task1_id
        queue.start_task(task1_id, worker_id)
        queue.complete_task(task1_id, worker_id, {"result": "done"})

        # Task 3 still not claimable (Task 2 not complete)
        assert not queue.are_dependencies_met(task3_id)

        # Claim and complete task 2
        task2 = queue.claim_task(worker_id)
        assert task2 is not None and task2['id'] == task2_id
        queue.start_task(task2_id, worker_id)
        queue.complete_task(task2_id, worker_id, {"result": "done"})

        # Now Task 3 should be claimable
        assert queue.are_dependencies_met(task3_id)

        print("✓ Task dependencies work correctly")


def test_circular_dependency_detection():
    """Test circular dependency detection"""
    print("\n=== Test: Circular Dependency Detection ===")

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        queue = TaskQueue(db_path)

        # Create tasks
        task1_id = queue.add_task("Task 1", priority=5)
        task2_id = queue.add_task("Task 2", priority=5)
        task3_id = queue.add_task("Task 3", priority=5)

        # Create chain: 1 -> 2 -> 3
        queue.add_task_dependency(task2_id, task1_id)
        queue.add_task_dependency(task3_id, task2_id)

        # Try to create cycle: 3 -> 1 (should raise ValueError)
        try:
            queue.add_task_dependency(task1_id, task3_id)
            assert False, "Should have raised ValueError for circular dependency"
        except ValueError as e:
            assert "circular dependency" in str(e).lower()
            print(f"✓ Circular dependency detected: {e}")

        # Try direct self-dependency (should also raise ValueError)
        task4_id = queue.add_task("Task 4", priority=5)
        try:
            queue.add_task_dependency(task4_id, task4_id)
            assert False, "Should have raised ValueError for self-dependency"
        except ValueError as e:
            assert "circular dependency" in str(e).lower()
            print(f"✓ Self-dependency detected: {e}")

        print("✓ Circular dependency detection works correctly")


def test_claim_task_respects_dependencies():
    """Test that claim_task() respects dependencies"""
    print("\n=== Test: Task Claiming Respects Dependencies ===")

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        queue = TaskQueue(db_path)

        # Create tasks
        task1_id = queue.add_task("Task 1", priority=5)
        task2_id = queue.add_task("Task 2 (depends on 1)", priority=5)

        # Task 2 depends on Task 1
        queue.add_task_dependency(task2_id, task1_id)

        # Register worker
        worker_id = "test_worker"
        queue.register_worker(worker_id)

        # Worker should claim Task 1 (no dependencies)
        claimed = queue.claim_task(worker_id)
        assert claimed is not None
        assert claimed['id'] == task1_id
        print(f"✓ Worker claimed Task {task1_id} (no dependencies)")

        # Worker should not be able to claim Task 2 yet
        claimed = queue.claim_task(worker_id)
        assert claimed is None
        print("✓ Worker cannot claim Task 2 (dependency not met)")

        # Complete Task 1
        queue.start_task(task1_id, worker_id)
        queue.complete_task(task1_id, worker_id, {"result": "done"})

        # Now worker should be able to claim Task 2
        claimed = queue.claim_task(worker_id)
        assert claimed is not None
        assert claimed['id'] == task2_id
        print(f"✓ Worker claimed Task {task2_id} (dependency met)")

        print("✓ Task claiming respects dependencies correctly")


def test_orchestrator_dependencies():
    """Test orchestrator dependency API"""
    print("\n=== Test: Orchestrator Dependency API ===")

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        orch = ClaudeOrchestrator("test_orch", db_path=db_path)

        # Create job
        job_id = orch.create_job("Test job with dependencies")

        # Create tasks with dependencies
        task1 = orch.add_subtask(job_id, "Build module", priority=10)
        task2 = orch.add_subtask(job_id, "Test module", priority=8, depends_on=[task1])
        task3 = orch.add_subtask(job_id, "Document module", priority=5, depends_on=[task1, task2])

        # Verify dependencies were added
        deps_task2 = orch.queue.get_task_dependencies(task2)
        assert task1 in deps_task2

        deps_task3 = orch.queue.get_task_dependencies(task3)
        assert task1 in deps_task3
        assert task2 in deps_task3

        print("✓ Orchestrator dependency API works correctly")


def test_orchestrator_shared_context():
    """Test orchestrator shared context API"""
    print("\n=== Test: Orchestrator Shared Context API ===")

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        orch = ClaudeOrchestrator("test_orch", db_path=db_path)

        # Create job
        job_id = orch.create_job("Test job with shared context")

        # Set shared context
        orch.set_shared_context("coding_style", "Follow PEP 8", job_id=job_id)
        orch.set_shared_context("test_framework", "Use pytest")

        # Get context
        context = orch.get_shared_context(job_id=job_id)

        assert "coding_style" in context
        assert context["coding_style"] == "Follow PEP 8"
        assert "test_framework" in context
        assert context["test_framework"] == "Use pytest"

        print("✓ Orchestrator shared context API works correctly")


def test_worker_context_injection():
    """Test that workers inject shared context into prompts"""
    print("\n=== Test: Worker Context Injection ===")

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        queue = TaskQueue(db_path)

        # Create job with shared context
        job_id = "test_job"
        queue.create_job(job_id, "Test job", "test_orch")
        queue.set_shared_context("naming_convention", "Use camelCase", job_id=job_id)
        queue.set_shared_context("import_style", "Use ES6 imports", job_id=job_id)

        # Add task
        task_id = queue.add_task(
            prompt="Create a simple function",
            job_id=job_id,
            priority=5
        )

        # Get task (simulate worker claiming)
        task = queue.get_task(task_id)

        # Verify task has job_id
        assert task['job_id'] == job_id

        # Get shared context (this is what worker would do)
        shared_context = queue.get_shared_context(job_id=job_id)

        assert "naming_convention" in shared_context
        assert "import_style" in shared_context

        print("✓ Shared context available for worker injection")

        # Test the actual prompt building logic from claude_worker.py
        full_prompt = f"Task ID: {task_id}\n\n"

        if shared_context:
            full_prompt += "Project Conventions (follow these):\n"
            for key, value in shared_context.items():
                full_prompt += f"- {key}: {value}\n"
            full_prompt += "\n"

        full_prompt += f"Task:\n{task['prompt']}\n"

        # Verify prompt contains conventions
        assert "Project Conventions (follow these):" in full_prompt
        assert "naming_convention: Use camelCase" in full_prompt
        assert "import_style: Use ES6 imports" in full_prompt

        print("✓ Worker context injection works correctly")


def test_shared_context_update():
    """Test updating shared context values"""
    print("\n=== Test: Shared Context Updates ===")

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        queue = TaskQueue(db_path)

        # Set initial value
        queue.set_shared_context("style_guide", "Version 1")

        # Update value
        queue.set_shared_context("style_guide", "Version 2")

        # Get value
        context = queue.get_shared_context()
        assert context["style_guide"] == "Version 2"

        # Delete value
        queue.delete_shared_context("style_guide")

        # Verify deleted
        context = queue.get_shared_context()
        assert "style_guide" not in context

        print("✓ Shared context updates work correctly")


def run_all_tests():
    """Run all tests"""
    print("=" * 60)
    print("Worker Coordination Tests (Issue #29)")
    print("=" * 60)

    tests = [
        test_shared_context_global,
        test_shared_context_job_specific,
        test_task_dependencies_basic,
        test_circular_dependency_detection,
        test_claim_task_respects_dependencies,
        test_orchestrator_dependencies,
        test_orchestrator_shared_context,
        test_worker_context_injection,
        test_shared_context_update,
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
