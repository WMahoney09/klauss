#!/usr/bin/env python3
"""
Example: How a Claude Code instance would use the orchestrator

This demonstrates the full workflow of a Claude Code orchestrator
delegating work to the worker pool and synthesizing results.
"""

from orchestrator import ClaudeOrchestrator
import json

def example_1_simple_parallel():
    """
    Example 1: Simple parallel task execution
    Break down a high-level goal into independent sub-tasks
    """
    print("=" * 70)
    print("EXAMPLE 1: Simple Parallel Execution")
    print("=" * 70)
    print("\nHigh-level goal: Create utility functions for a Python project")
    print()

    orch = ClaudeOrchestrator("claude_main")

    # Create job
    job = orch.create_job("Create utility functions for Python project")

    # Decompose into parallel sub-tasks
    orch.add_subtask(
        job,
        "Create a Python function to calculate factorial with type hints and docstring",
        priority=5
    )

    orch.add_subtask(
        job,
        "Create a Python function to check if a number is prime with type hints and docstring",
        priority=5
    )

    orch.add_subtask(
        job,
        "Create a Python function to generate Fibonacci sequence with type hints and docstring",
        priority=5
    )

    orch.add_subtask(
        job,
        "Create a Python function for binary search with type hints and docstring",
        priority=5
    )

    print("\n✓ All tasks submitted to queue")
    print("\nNow waiting for workers to complete tasks...")
    print("(Make sure workers are running: python3 claude_coordinator.py 4)")

    # Wait and collect results
    results = orch.wait_and_collect(job, show_progress=True)

    # Synthesize
    print("\n" + "=" * 70)
    print("SYNTHESIS")
    print("=" * 70)

    synthesis = orch.synthesize_results(
        results,
        synthesis_prompt="Please review the implementation of these utility functions and suggest improvements."
    )

    print(synthesis)

    return results


def example_2_hierarchical():
    """
    Example 2: Hierarchical task decomposition
    Main task spawns sub-tasks based on results
    """
    print("\n\n" + "=" * 70)
    print("EXAMPLE 2: Hierarchical Task Decomposition")
    print("=" * 70)
    print("\nHigh-level goal: Build a REST API with authentication")
    print()

    orch = ClaudeOrchestrator("claude_hierarchical")

    # Create job
    job = orch.create_job("Build REST API with authentication")

    # Phase 1: Core implementation tasks
    print("\nPhase 1: Core Implementation")
    task1 = orch.add_subtask(
        job,
        "Create Express.js server setup with basic middleware",
        priority=10
    )

    task2 = orch.add_subtask(
        job,
        "Implement user authentication endpoints (login, register, logout)",
        priority=10
    )

    task3 = orch.add_subtask(
        job,
        "Create JWT token generation and validation middleware",
        priority=10
    )

    # Phase 2: Testing (depends on phase 1)
    print("\nPhase 2: Testing")
    orch.add_subtask(
        job,
        "Write integration tests for authentication endpoints",
        priority=5,
        parent_task_id=task2  # This is a child of the auth endpoints task
    )

    orch.add_subtask(
        job,
        "Write unit tests for JWT middleware",
        priority=5,
        parent_task_id=task3  # This is a child of the JWT task
    )

    # Phase 3: Documentation
    print("\nPhase 3: Documentation")
    orch.add_subtask(
        job,
        "Generate API documentation with examples",
        priority=3
    )

    print("\n✓ All tasks submitted with hierarchical structure")
    print("\nWaiting for completion...")

    results = orch.wait_and_collect(job, show_progress=True)

    # Check for failures and retry
    failed_tasks = orch.get_failed_tasks(job)
    if failed_tasks:
        print(f"\n⚠ {len(failed_tasks)} tasks failed, retrying...")
        orch.retry_failed_tasks(job)
        results = orch.wait_and_collect(job, show_progress=True)

    synthesis = orch.synthesize_results(
        results,
        synthesis_prompt="Evaluate the completeness of the REST API implementation."
    )

    print(synthesis)

    return results


def example_3_adaptive():
    """
    Example 3: Adaptive workflow
    Orchestrator adapts based on intermediate results
    """
    print("\n\n" + "=" * 70)
    print("EXAMPLE 3: Adaptive Workflow")
    print("=" * 70)
    print("\nHigh-level goal: Refactor codebase based on analysis")
    print()

    orch = ClaudeOrchestrator("claude_adaptive")

    # Create job
    job = orch.create_job("Analyze and refactor codebase")

    # Step 1: Analysis
    print("\nStep 1: Analysis Phase")
    analysis_task = orch.add_subtask(
        job,
        "Analyze the codebase structure and identify areas for improvement",
        priority=10
    )

    # Submit analysis task and wait for it specifically
    print("Waiting for analysis to complete...")

    # In a real scenario, you'd poll for this specific task
    # For now, we'll just show the pattern

    # Step 2: Based on analysis, create refactoring tasks
    # (In real usage, Claude would read the analysis results and decide)
    print("\nStep 2: Creating refactoring tasks based on analysis...")

    orch.add_subtask(
        job,
        "Refactor authentication module to use async/await",
        priority=8,
        parent_task_id=analysis_task
    )

    orch.add_subtask(
        job,
        "Extract database queries into separate repository layer",
        priority=8,
        parent_task_id=analysis_task
    )

    orch.add_subtask(
        job,
        "Add error handling to API endpoints",
        priority=7,
        parent_task_id=analysis_task
    )

    # Step 3: Validation
    print("\nStep 3: Validation")
    orch.add_subtask(
        job,
        "Run full test suite and verify all tests pass",
        priority=5
    )

    results = orch.wait_and_collect(job, show_progress=True)

    synthesis = orch.synthesize_results(
        results,
        synthesis_prompt="Summarize the refactoring changes and their impact."
    )

    print(synthesis)

    return results


def example_4_quick_delegate():
    """
    Example 4: Quick delegation for simple tasks
    """
    print("\n\n" + "=" * 70)
    print("EXAMPLE 4: Quick Delegation")
    print("=" * 70)

    from orchestrator import quick_delegate

    results = quick_delegate([
        "Explain the difference between async/await and promises in JavaScript",
        "Write a Python script to parse CSV files",
        "Create a Dockerfile for a Node.js application",
    ])

    print(f"\n✓ {len(results)} tasks completed")

    return results


if __name__ == '__main__':
    import sys

    print("""
╔════════════════════════════════════════════════════════════════════╗
║   Claude Code Orchestrator - Example Workflows                    ║
║   Demonstrates how Claude Code instances delegate work             ║
╚════════════════════════════════════════════════════════════════════╝

Before running these examples, make sure workers are running:
    python3 claude_coordinator.py 4

Then run one of these examples:
    python3 example_orchestrator_workflow.py 1   # Simple parallel
    python3 example_orchestrator_workflow.py 2   # Hierarchical
    python3 example_orchestrator_workflow.py 3   # Adaptive
    python3 example_orchestrator_workflow.py 4   # Quick delegate
    """)

    if len(sys.argv) < 2:
        print("Please specify example number (1-4)")
        sys.exit(0)

    example_num = sys.argv[1]

    if example_num == "1":
        example_1_simple_parallel()
    elif example_num == "2":
        example_2_hierarchical()
    elif example_num == "3":
        example_3_adaptive()
    elif example_num == "4":
        example_4_quick_delegate()
    else:
        print(f"Unknown example: {example_num}")
        print("Valid options: 1, 2, 3, 4")
