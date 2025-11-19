# Claude Code Orchestrator Guide

## Overview

This system allows Claude Code instances to act as **orchestrators**, delegating work to a pool of worker Claude instances running in parallel.

```
You (User)
    ↓
    ↓ Give high-level goal
    ↓
Claude Code (Orchestrator)
    ↓
    ├─ Breaks down into sub-tasks
    ├─ Submits to queue
    ├─ Monitors progress
    └─ Synthesizes results
    ↓
Task Queue (SQLite)
    ↓
    ├───────┬───────┬───────┐
    ▼       ▼       ▼       ▼
Worker1 Worker2 Worker3 Worker4 (Parallel execution)
    └───────┴───────┴───────┘
    ↓
Results → Back to Orchestrator
    ↓
Final synthesis → Back to You
```

## For Claude Code: How to Use This System

### Step 1: Import the Orchestrator

```python
from orchestrator import ClaudeOrchestrator

# Create orchestrator instance
orch = ClaudeOrchestrator("my_orchestrator_id")
```

### Step 2: Create a Job

```python
# Create a job for a high-level goal
job_id = orch.create_job("Build authentication system for web app")
```

### Step 3: Decompose into Sub-tasks

```python
# Break down the goal into parallel sub-tasks
orch.add_subtask(
    job_id,
    "Implement user login endpoint with JWT",
    priority=10,
    context_files=["src/routes/auth.js"],
    expected_outputs=["src/routes/auth.js"]
)

orch.add_subtask(
    job_id,
    "Implement user registration endpoint",
    priority=10,
    expected_outputs=["src/routes/register.js"]
)

orch.add_subtask(
    job_id,
    "Create authentication middleware",
    priority=9,
    expected_outputs=["src/middleware/auth.js"]
)

orch.add_subtask(
    job_id,
    "Write unit tests for auth endpoints",
    priority=5,
    expected_outputs=["tests/auth.test.js"]
)
```

### Step 3.5: Add Verification (Optional but Recommended)

Tasks automatically verify outputs using auto-detection, but you can also specify custom verification hooks:

```python
from verification import VerificationHook

# Task with custom verification
orch.add_subtask(
    job_id,
    "Implement payment processing",
    expected_outputs=["src/payment/processor.ts"],
    verification_hooks=[
        VerificationHook(
            command="npx tsc --noEmit",
            description="TypeScript compilation"
        ),
        VerificationHook(
            command="npm run test:payment",
            description="Payment tests"
        )
    ]
)

# Disable auto-verification for documentation tasks
orch.add_subtask(
    job_id,
    "Update API documentation",
    auto_verify=False  # Skip verification
)
```

**Auto-Verification (Default):**
- Workers automatically detect project type (TypeScript, Python, Go, etc.)
- Run appropriate checks (compilation, linting, tests)
- Only mark tasks complete if ALL checks pass
- Provides detailed error messages on failure

This prevents false successes when code contains errors!

### Step 4: Wait for Completion

```python
# Wait for all tasks to complete and collect results
results = orch.wait_and_collect(job_id, show_progress=True)

# Results is a dictionary: {task_id: {result_data}}
```

### Step 5: Synthesize Results

```python
# Format results for synthesis
synthesis = orch.synthesize_results(
    results,
    synthesis_prompt="Review the authentication implementation and suggest improvements"
)

# Now you can analyze the synthesis and provide final response to user
print(synthesis)
```

## Worker Coordination Features

### Shared Context

Workers executing tasks in parallel can produce inconsistent outputs (e.g., different import styles, naming conventions). Use **shared context** to ensure all workers follow the same conventions:

```python
orch = ClaudeOrchestrator("coordinator")
job = orch.create_job("Build user dashboard with multiple components")

# Set shared conventions that all workers will receive
orch.set_shared_context("import_style", "Use ES6 imports with destructuring")
orch.set_shared_context("css_pattern", "Use CSS modules with .module.css extension")
orch.set_shared_context("naming_convention", "Use camelCase for functions, PascalCase for components")

# Add tasks - workers will automatically receive these conventions
orch.add_subtask(job, "Create UserProfile component")
orch.add_subtask(job, "Create UserSettings component")
orch.add_subtask(job, "Create UserActivity component")

results = orch.wait_and_collect(job)
```

**How it works:**
- Context is automatically injected into worker prompts as "Project Conventions (follow these):"
- Workers see these conventions before receiving their task instructions
- Ensures consistent styling, naming, and patterns across parallel work

**Context Scope:**
```python
# Global context (applies to all jobs)
orch.set_shared_context("code_style", "Follow PEP 8")

# Job-specific context (only for this job)
orch.set_shared_context("api_version", "v2", job_id=job)
```

### Task Dependencies

When tasks must execute in a specific order, use **dependencies** to ensure workers respect execution sequences:

```python
orch = ClaudeOrchestrator("coordinator")
job = orch.create_job("Build and test authentication module")

# Define execution order
task1 = orch.add_subtask(job, "Implement authentication module", priority=10)
task2 = orch.add_subtask(job, "Write unit tests", priority=8, depends_on=[task1])
task3 = orch.add_subtask(job, "Write integration tests", priority=8, depends_on=[task1])
task4 = orch.add_subtask(job, "Generate API docs", priority=5, depends_on=[task1, task2, task3])

# Task 1 executes first
# Tasks 2 and 3 execute in parallel after Task 1 completes
# Task 4 executes only after all previous tasks complete
```

**Benefits:**
- Workers automatically respect dependencies (won't claim tasks with unmet dependencies)
- Circular dependencies are detected and rejected
- Enables sequential workflows within parallel execution

**Complex Dependency Graph:**
```python
# Build a pipeline with multiple stages
job = orch.create_job("Multi-stage deployment pipeline")

# Stage 1: Parallel builds
backend = orch.add_subtask(job, "Build backend service")
frontend = orch.add_subtask(job, "Build frontend app")
worker = orch.add_subtask(job, "Build worker service")

# Stage 2: Tests (depend on builds)
backend_tests = orch.add_subtask(job, "Run backend tests", depends_on=[backend])
frontend_tests = orch.add_subtask(job, "Run frontend tests", depends_on=[frontend])
worker_tests = orch.add_subtask(job, "Run worker tests", depends_on=[worker])

# Stage 3: Integration tests (depend on all component tests)
integration = orch.add_subtask(
    job,
    "Run integration tests",
    depends_on=[backend_tests, frontend_tests, worker_tests]
)

# Stage 4: Deployment (depends on all tests passing)
deploy = orch.add_subtask(job, "Deploy to staging", depends_on=[integration])
```

## Common Patterns

### Pattern 1: Simple Parallel Execution

When tasks are independent and can run in any order:

```python
orch = ClaudeOrchestrator("parallel_tasks")
job = orch.create_job("Generate utility functions")

orch.add_subtask(job, "Create factorial function", priority=5)
orch.add_subtask(job, "Create fibonacci function", priority=5)
orch.add_subtask(job, "Create prime checker function", priority=5)

results = orch.wait_and_collect(job)
```

### Pattern 2: Hierarchical Decomposition

When some tasks depend on others, use **dependencies** or **parent_task_id** (or both):

```python
orch = ClaudeOrchestrator("hierarchical")
job = orch.create_job("Build and test API")

# Parent task
api_task = orch.add_subtask(job, "Implement REST API", priority=10)

# Child tasks using dependencies (workers respect execution order)
orch.add_subtask(
    job,
    "Write API tests",
    priority=5,
    depends_on=[api_task]  # Won't execute until api_task completes
)

orch.add_subtask(
    job,
    "Generate API documentation",
    priority=3,
    depends_on=[api_task]  # Won't execute until api_task completes
)

# Or use parent_task_id for logical grouping (doesn't enforce order)
orch.add_subtask(
    job,
    "Create API monitoring dashboard",
    priority=2,
    parent_task_id=api_task  # Logical grouping only
)

results = orch.wait_and_collect(job)
```

**Note:** `parent_task_id` is for logical grouping and metadata only. Use `depends_on` to enforce execution order.

### Pattern 3: Adaptive Workflow

Orchestrator adapts based on intermediate results:

```python
orch = ClaudeOrchestrator("adaptive")
job = orch.create_job("Refactor codebase")

# Step 1: Analysis
analysis_task = orch.add_subtask(
    job,
    "Analyze codebase and identify issues",
    priority=10
)

# Wait for just the analysis
while True:
    task = orch.queue.get_task(analysis_task)
    if task['status'] == 'completed':
        # Read analysis results
        analysis = json.loads(task['result'])
        break
    time.sleep(2)

# Step 2: Based on analysis, create targeted refactoring tasks
# (Claude reads analysis and decides what to do)
if "performance issues" in analysis:
    orch.add_subtask(job, "Optimize database queries", priority=8)

if "security vulnerabilities" in analysis:
    orch.add_subtask(job, "Fix security issues", priority=10)

results = orch.wait_and_collect(job)
```

### Pattern 4: Quick Delegation

For quick, simple parallel tasks:

```python
from orchestrator import quick_delegate

results = quick_delegate([
    "Create Python factorial function",
    "Create Python fibonacci function",
    "Create Python prime checker"
])

# That's it! Results collected automatically
```

### Pattern 5: Coordinated Parallel Development

Combine **shared context** and **dependencies** for consistent, ordered parallel work:

```python
orch = ClaudeOrchestrator("coordinated")
job = orch.create_job("Build multi-module TypeScript library")

# Set shared conventions for all workers
orch.set_shared_context("import_style", "Use 'import type' for TypeScript types")
orch.set_shared_context("export_style", "Use named exports, not default exports")
orch.set_shared_context("testing", "Use Jest with .test.ts extension")
orch.set_shared_context("docs", "Include JSDoc comments for all public functions")

# Stage 1: Core modules (parallel)
core_auth = orch.add_subtask(job, "Create auth module with user validation")
core_data = orch.add_subtask(job, "Create data module with CRUD operations")
core_utils = orch.add_subtask(job, "Create utils module with helper functions")

# Stage 2: Feature modules (depend on core, parallel with each other)
feature_api = orch.add_subtask(
    job,
    "Create API client module",
    depends_on=[core_auth, core_data]
)
feature_ui = orch.add_subtask(
    job,
    "Create UI helpers module",
    depends_on=[core_utils]
)

# Stage 3: Integration (depends on all features)
integration = orch.add_subtask(
    job,
    "Create integration tests for all modules",
    depends_on=[feature_api, feature_ui]
)

# All workers receive shared conventions automatically
# Dependencies ensure correct execution order
# Result: Consistent, well-tested codebase
results = orch.wait_and_collect(job)
```

## Advanced Features

### Retry Failed Tasks

```python
results = orch.wait_and_collect(job)

# Check for failures
failed = orch.get_failed_tasks(job)
if failed:
    print(f"Retrying {len(failed)} failed tasks...")
    orch.retry_failed_tasks(job)
    results = orch.wait_and_collect(job)
```

### Monitor Progress

```python
# Check status without blocking
status = orch.get_job_status(job)
print(f"Progress: {status['progress_pct']}%")
print(f"Completed: {status['completed']}/{status['total_tasks']}")
```

### Get Partial Results

```python
# Don't wait - just get what's completed so far
completed_tasks = orch.get_completed_tasks(job)

for task in completed_tasks:
    print(f"Task {task['id']}: {task['prompt']}")
    result = json.loads(task['result'])
    print(f"  Result: {result}")
```

## Example: Full Orchestrator Session

```python
#!/usr/bin/env python3
"""
Example: Claude Code acting as orchestrator
"""

from orchestrator import ClaudeOrchestrator

def main():
    # You are Claude Code, and the user asked:
    # "Build a task management API with CRUD operations"

    print("Breaking down your request into sub-tasks...")

    orch = ClaudeOrchestrator("claude_main")
    job = orch.create_job("Build task management API with CRUD")

    # Decompose
    orch.add_subtask(
        job,
        "Create Express.js server with basic setup",
        priority=10,
        expected_outputs=["server.js"]
    )

    orch.add_subtask(
        job,
        "Implement GET /tasks endpoint to list all tasks",
        priority=8,
        expected_outputs=["routes/tasks.js"]
    )

    orch.add_subtask(
        job,
        "Implement POST /tasks endpoint to create task",
        priority=8,
        expected_outputs=["routes/tasks.js"]
    )

    orch.add_subtask(
        job,
        "Implement PUT /tasks/:id endpoint to update task",
        priority=7,
        expected_outputs=["routes/tasks.js"]
    )

    orch.add_subtask(
        job,
        "Implement DELETE /tasks/:id endpoint",
        priority=7,
        expected_outputs=["routes/tasks.js"]
    )

    orch.add_subtask(
        job,
        "Write integration tests for all endpoints",
        priority=5,
        expected_outputs=["tests/tasks.test.js"]
    )

    print("\nDelegating to worker pool...")
    results = orch.wait_and_collect(job, show_progress=True)

    # Synthesize
    synthesis = orch.synthesize_results(
        results,
        synthesis_prompt="""
        Review the implementation and provide:
        1. Summary of what was built
        2. Any issues or improvements needed
        3. Next steps for the user
        """
    )

    print("\n" + "="*70)
    print("FINAL REPORT")
    print("="*70)
    print(synthesis)

if __name__ == '__main__':
    main()
```

## Tips for Claude Code Orchestrators

1. **Break down intelligently**: Decompose into tasks that are:
   - Independent (can run in parallel)
   - Specific (clear success criteria)
   - Reasonable in scope (not too large)

2. **Use priority effectively**:
   - Critical tasks: priority 10
   - Important tasks: priority 7-9
   - Nice-to-have: priority 1-3

3. **Leverage context**:
   - Pass relevant files via `context_files`
   - Specify expected outputs for verification
   - Use metadata for additional information

4. **Handle failures**:
   - Check for failed tasks
   - Retry with modifications if needed
   - Provide user with failure summary

5. **Synthesize well**:
   - Collect all results
   - Analyze for completeness
   - Provide actionable next steps

## Running the System

### Terminal 1: Start Workers
```bash
python3 claude_coordinator.py 4  # Start 4 workers
```

### Terminal 2: Monitor Dashboard
```bash
python3 claude_dashboard.py  # Watch real-time progress
```

### Terminal 3: Run Orchestrator (Claude Code)
```python
# In a Claude Code session, you can now use:
from orchestrator import ClaudeOrchestrator

orch = ClaudeOrchestrator("claude_code_main")
# ... delegate work ...
```

Or run example workflows:
```bash
python3 example_orchestrator_workflow.py 1
```

## Integration with Claude Code

When you (Claude Code) receive a complex request from the user:

1. **Assess**: Can this be parallelized?
2. **Decompose**: Break into sub-tasks
3. **Delegate**: Use the orchestrator to submit tasks
4. **Monitor**: Wait for completion
5. **Synthesize**: Analyze results and present to user

This allows you to:
- ✅ Handle complex, multi-step requests efficiently
- ✅ Parallelize independent tasks
- ✅ Scale to handle larger projects
- ✅ Provide better progress visibility to users

## See Also

- `README.md` - System overview and architecture
- `example_orchestrator_workflow.py` - Working examples
- `orchestrator.py` - Full API reference
