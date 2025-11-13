#!/bin/bash
# Test script for improved logging features
# Tests the improvements from Issue #5

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEST_DB="/tmp/klauss_logging_test_$(date +%s).db"

echo "🧪 Testing Logging Improvements (Issue #5)"
echo "=========================================="
echo ""

# Test 1: Worker startup health check
echo "📋 Test 1: Worker health check with non-existent database"
echo "   (Should show helpful error messages)"
echo ""

timeout 5 python3 "$SCRIPT_DIR/claude_worker.py" test_worker "/tmp/nonexistent_db.db" 2>&1 || true

echo ""
echo "=========================================="
echo ""

# Test 2: Create database and test health check with empty database
echo "📋 Test 2: Worker health check with empty database"
echo "   (Should warn about no pending tasks)"
echo ""

python3 - <<PYTHON
import sys
sys.path.insert(0, '$SCRIPT_DIR')
from claude_queue import TaskQueue
queue = TaskQueue("$TEST_DB")
print("✅ Created empty database")
PYTHON

echo ""
timeout 10 python3 "$SCRIPT_DIR/claude_worker.py" test_worker "$TEST_DB" 2>&1 &
WORKER_PID=$!
sleep 3
kill $WORKER_PID 2>/dev/null || true
wait $WORKER_PID 2>/dev/null || true

echo ""
echo "=========================================="
echo ""

# Test 3: Test with actual tasks (structured logging)
echo "📋 Test 3: Structured logging with actual task"
echo ""

python3 - <<PYTHON
import sys
sys.path.insert(0, '$SCRIPT_DIR')
from orchestrator import ClaudeOrchestrator

orch = ClaudeOrchestrator("logging_test", db_path="$TEST_DB", allow_external_dirs=True)
job = orch.create_job("Logging test job")
orch.add_subtask(job, "echo 'test'", working_dir="/tmp", priority=10)
print("✅ Added test task")
PYTHON

echo ""
echo "Starting worker to show structured logging..."
echo ""

timeout 15 python3 "$SCRIPT_DIR/claude_worker.py" test_worker "$TEST_DB" 2>&1 &
WORKER_PID=$!
sleep 5
kill $WORKER_PID 2>/dev/null || true
wait $WORKER_PID 2>/dev/null || true

echo ""
echo "=========================================="
echo ""

# Test 4: Test logs command
echo "📋 Test 4: Testing './manage.sh logs' command"
echo ""

# Create fake log files for testing
mkdir -p "$SCRIPT_DIR/logs"
echo "[test_worker] [STARTUP] Test log entry" > "$SCRIPT_DIR/logs/test_worker.log"
echo "[test_worker] [CLAIM] Claimed task 1" >> "$SCRIPT_DIR/logs/test_worker.log"

echo "Testing: ./manage.sh logs"
echo ""
"$SCRIPT_DIR/manage.sh" logs

echo ""
echo "Testing: ./manage.sh logs test_worker"
echo ""
"$SCRIPT_DIR/manage.sh" logs test_worker

# Cleanup
rm -f "$TEST_DB"
rm -f "$SCRIPT_DIR/logs/test_worker.log"

echo ""
echo "=========================================="
echo "✅ Logging improvements tested!"
echo ""
echo "New features demonstrated:"
echo "  ✅ Health check on worker startup"
echo "  ✅ Helpful error messages with suggestions"
echo "  ✅ Structured logging ([STARTUP], [CLAIM], [EXEC], etc.)"
echo "  ✅ Database validation"
echo "  ✅ Task visibility checking"
echo "  ✅ Enhanced ./manage.sh logs command"
echo ""
