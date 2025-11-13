#!/bin/bash
# Full end-to-end integration test for Klauss
# Tests the complete workflow from task creation through worker execution

set -e  # Exit on any error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEST_DB="/tmp/klauss_test_$(date +%s).db"
TEST_OUTPUT="/tmp/klauss_test_output_$(date +%s).txt"
WORKER_PID=""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "🧪 Starting Klauss Integration Test"
echo "=" * 60

# Cleanup function
cleanup() {
    echo ""
    echo "🧹 Cleaning up..."

    # Kill worker if running
    if [ -n "$WORKER_PID" ] && kill -0 "$WORKER_PID" 2>/dev/null; then
        echo "   Stopping worker (PID: $WORKER_PID)..."
        kill "$WORKER_PID" 2>/dev/null || true
        sleep 1
    fi

    # Remove test files
    rm -f "$TEST_DB" "$TEST_OUTPUT"

    echo "   Cleanup complete"
}

# Set trap to cleanup on exit
trap cleanup EXIT

# Test 1: Create test database and task
echo ""
echo "📝 Test 1: Creating test task..."
echo "   Database: $TEST_DB"

python3 - <<PYTHON
import sys
sys.path.insert(0, '$SCRIPT_DIR')
from orchestrator import ClaudeOrchestrator

orch = ClaudeOrchestrator("integration_test", db_path="$TEST_DB", allow_external_dirs=True)
job = orch.create_job("Integration test job")
orch.add_subtask(
    job,
    "echo 'Integration test successful' > $TEST_OUTPUT",
    working_dir="/tmp",
    priority=10
)
print(f"✅ Created job: {job}")
PYTHON

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Failed to create task${NC}"
    exit 1
fi

# Test 2: Verify task in database
echo ""
echo "🔍 Test 2: Verifying task in database..."

TASK_COUNT=$(python3 - <<PYTHON
import sys
sys.path.insert(0, '$SCRIPT_DIR')
from claude_queue import TaskQueue

queue = TaskQueue("$TEST_DB")
pending = queue.list_tasks(status='pending')
print(len(pending))
PYTHON
)

if [ "$TASK_COUNT" != "1" ]; then
    echo -e "${RED}❌ Expected 1 pending task, found $TASK_COUNT${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Task verified in database (1 pending task)${NC}"

# Test 3: Start a worker
echo ""
echo "🚀 Test 3: Starting worker..."

# Export variables for worker subprocess
export SCRIPT_DIR
export TEST_DB

# Create a simple test worker that executes the task
python3 - <<'PYTHON' &
import sys
import os
import subprocess
sys.path.insert(0, os.environ['SCRIPT_DIR'])
from claude_queue import TaskQueue
import time

queue = TaskQueue(os.environ['TEST_DB'])
queue.register_worker("test_worker")

# Try to claim and execute task
task = queue.claim_task("test_worker")
if task:
    print(f"[test_worker] Claimed task {task['id']}")
    queue.start_task(task['id'], "test_worker")

    # Execute the task (simple shell command)
    try:
        result = subprocess.run(
            task['prompt'],
            shell=True,
            cwd=task['working_dir'] or os.getcwd(),
            capture_output=True,
            text=True,
            timeout=30
        )

        output = {
            'stdout': result.stdout,
            'stderr': result.stderr,
            'return_code': result.returncode
        }

        if result.returncode == 0:
            queue.complete_task(task['id'], "test_worker", output)
            print(f"[test_worker] Completed task {task['id']}")
        else:
            queue.fail_task(task['id'], "test_worker", f"Exit code: {result.returncode}")
            print(f"[test_worker] Failed task {task['id']}")
    except Exception as e:
        queue.fail_task(task['id'], "test_worker", str(e))
        print(f"[test_worker] Error: {e}")
else:
    print("[test_worker] No task available")
PYTHON

WORKER_PID=$!
echo "   Worker started (PID: $WORKER_PID)"

# Test 4: Wait for task completion
echo ""
echo "⏳ Test 4: Waiting for task completion (max 30 seconds)..."

TIMEOUT=30
ELAPSED=0
COMPLETED=0

while [ $ELAPSED -lt $TIMEOUT ]; do
    COMPLETED=$(python3 - <<PYTHON
import sys
sys.path.insert(0, '$SCRIPT_DIR')
from claude_queue import TaskQueue

queue = TaskQueue("$TEST_DB")
completed = queue.list_tasks(status='completed')
print(len(completed))
PYTHON
    )

    if [ "$COMPLETED" = "1" ]; then
        echo -e "${GREEN}✅ Task completed successfully!${NC}"
        break
    fi

    sleep 1
    ELAPSED=$((ELAPSED + 1))
done

if [ $ELAPSED -eq $TIMEOUT ]; then
    echo -e "${RED}❌ Task did not complete within $TIMEOUT seconds${NC}"

    # Show task status for debugging
    echo ""
    echo "Task status:"
    python3 - <<PYTHON
import sys
sys.path.insert(0, '$SCRIPT_DIR')
from claude_queue import TaskQueue

queue = TaskQueue("$TEST_DB")
tasks = queue.list_tasks()
for task in tasks:
    print(f"  Task {task['id']}: {task['status']}")
    if task['error']:
        print(f"    Error: {task['error']}")
PYTHON

    exit 1
fi

# Test 5: Verify output file
echo ""
echo "📄 Test 5: Verifying output file..."

if [ -f "$TEST_OUTPUT" ]; then
    CONTENT=$(cat "$TEST_OUTPUT")
    if [[ "$CONTENT" == *"Integration test successful"* ]]; then
        echo -e "${GREEN}✅ Output file created with correct content${NC}"
    else
        echo -e "${RED}❌ Output file has wrong content: $CONTENT${NC}"
        exit 1
    fi
else
    echo -e "${RED}❌ Output file not found: $TEST_OUTPUT${NC}"
    exit 1
fi

# Test 6: Verify task status in database
echo ""
echo "📊 Test 6: Verifying final task status..."

python3 - <<PYTHON
import sys
sys.path.insert(0, '$SCRIPT_DIR')
from claude_queue import TaskQueue

queue = TaskQueue("$TEST_DB")
stats = queue.get_stats()

print(f"   Pending:    {stats['pending']}")
print(f"   Completed:  {stats['completed']}")
print(f"   Failed:     {stats['failed']}")

if stats['completed'] != 1:
    print("❌ Expected 1 completed task")
    sys.exit(1)
if stats['pending'] != 0:
    print("❌ Expected 0 pending tasks")
    sys.exit(1)
if stats['failed'] != 0:
    print("❌ Expected 0 failed tasks")
    sys.exit(1)

print("✅ Task status verified")
PYTHON

if [ $? -ne 0 ]; then
    exit 1
fi

echo ""
echo "=" * 60
echo -e "${GREEN}🎉 Integration test PASSED!${NC}"
echo "=" * 60
echo ""
echo "All systems working:"
echo "  ✅ Database creation"
echo "  ✅ Task insertion"
echo "  ✅ Worker startup"
echo "  ✅ Task claiming"
echo "  ✅ Task execution"
echo "  ✅ Status updates"
echo "  ✅ Output generation"
echo ""
