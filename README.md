# Claude Code Parallel Task Orchestrator

A system to manage and execute multiple Claude Code instances in parallel, working from a shared task queue.

## Two Modes of Operation

### 1. Manual Mode
Submit tasks via CLI and let workers execute them in parallel.

### 2. Orchestrator Mode ⭐ NEW
**Claude Code instances can act as orchestrators**, delegating work to the worker pool:

```python
from orchestrator import ClaudeOrchestrator

# You (Claude Code) receive: "Build an authentication system"
orch = ClaudeOrchestrator("claude_main")
job = orch.create_job("Build authentication system")

# Decompose into parallel sub-tasks
orch.add_subtask(job, "Implement login endpoint", priority=10)
orch.add_subtask(job, "Implement registration endpoint", priority=10)
orch.add_subtask(job, "Create JWT middleware", priority=9)
orch.add_subtask(job, "Write auth tests", priority=5)

# Wait and synthesize
results = orch.wait_and_collect(job)
```

See **[ORCHESTRATOR_GUIDE.md](ORCHESTRATOR_GUIDE.md)** for full details.

## Features

- **SQLite-based task queue** with atomic task claiming
- **Multiple concurrent Claude workers** executing tasks in parallel
- **Orchestrator interface** for Claude Code delegation
- **Hierarchical task relationships** (parent/child tasks)
- **Job/session tracking** to group related tasks
- **Structured task definitions** with context files and expected outputs
- **Real-time dashboard** to monitor workers and tasks
- **Automatic worker recovery** if a worker crashes
- **Task prioritization** support
- **Heartbeat monitoring** to detect stale workers
- **Result collection and synthesis** helpers

## Architecture

```
┌─────────────────┐
│  Submit Tasks   │
│   (CLI/API)     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  SQLite Queue   │◄───────┐
│  (claude_tasks  │        │
│      .db)       │        │
└────────┬────────┘        │
         │                 │
         │                 │ Heartbeat
         ├─────────┬───────┼─────────┬────────┐
         │         │       │         │        │
         ▼         ▼       ▼         ▼        ▼
    ┌────────┬────────┬────────┬────────┬────────┐
    │Worker 1│Worker 2│Worker 3│Worker 4│Worker N│
    │ Claude │ Claude │ Claude │ Claude │ Claude │
    └────────┴────────┴────────┴────────┴────────┘
                       │
                       ▼
              ┌────────────────┐
              │   Dashboard    │
              │  (Real-time    │
              │   Monitoring)  │
              └────────────────┘
```

## Installation

All scripts are pure Python with no external dependencies (except Claude Code itself).

```bash
# Ensure Claude Code is installed and in your PATH
which claude

# Make scripts executable
chmod +x *.py
```

## Usage

### 1. Submit Tasks

**Submit a single task:**
```bash
python submit_task.py submit "Fix all ESLint errors in the codebase" \
  --dir /path/to/project \
  --context src/**/*.js \
  --priority 5
```

**Submit tasks from a JSON file:**
```bash
python submit_task.py submit-file tasks.json
```

Example `tasks.json`:
```json
[
  {
    "prompt": "Add unit tests for the authentication module",
    "working_dir": "/path/to/project",
    "context_files": ["src/auth/login.js", "src/auth/register.js"],
    "expected_outputs": ["tests/auth/login.test.js", "tests/auth/register.test.js"],
    "priority": 5
  },
  {
    "prompt": "Refactor the database connection pooling to use async/await",
    "working_dir": "/path/to/project",
    "context_files": ["src/db/pool.js"],
    "expected_outputs": ["src/db/pool.js"],
    "priority": 3
  },
  {
    "prompt": "Update documentation for the API endpoints",
    "working_dir": "/path/to/project",
    "context_files": ["src/routes/*.js"],
    "expected_outputs": ["docs/api.md"],
    "priority": 1
  }
]
```

**List all tasks:**
```bash
python submit_task.py list
python submit_task.py list --status pending
```

**Show task details:**
```bash
python submit_task.py show 1
```

**Show queue statistics:**
```bash
python submit_task.py stats
```

### 2. Start the Coordinator (Spawn Workers)

Start 4 workers (default):
```bash
python claude_coordinator.py
```

Start a specific number of workers:
```bash
python claude_coordinator.py 8
```

The coordinator will:
- Spawn N worker processes
- Monitor them and restart if they crash
- Log output to `logs/worker_*.log`
- Handle graceful shutdown on Ctrl+C

### 3. Monitor with the Dashboard

Launch the real-time dashboard:
```bash
python claude_dashboard.py
```

The dashboard shows:
- Queue statistics (pending, in progress, completed, failed)
- Active workers and their status
- Recent tasks with color-coded status
- Auto-refreshes every 2 seconds

Press `q` to quit.

### 4. Run Everything

**Terminal 1 - Start Workers:**
```bash
python claude_coordinator.py 4
```

**Terminal 2 - Monitor Dashboard:**
```bash
python claude_dashboard.py
```

**Terminal 3 - Submit Tasks:**
```bash
python submit_task.py submit "Your task here"
```

## Task Structure

Tasks support the following fields:

- **prompt** (required): The instruction for Claude
- **working_dir** (optional): Directory where Claude should execute
- **context_files** (optional): Files Claude should read for context
- **expected_outputs** (optional): Files that should exist after task completion
- **metadata** (optional): Custom JSON metadata
- **priority** (optional): Higher priority tasks are executed first (default: 0)

## Worker Behavior

Each worker:
1. Claims a task atomically from the queue
2. Marks it as "in_progress"
3. Builds a comprehensive prompt with context
4. Executes `claude` CLI with the prompt
5. Marks task as "completed" or "failed" based on result
6. Moves to next task

Workers send heartbeats every 5 seconds. Stale tasks (from dead workers) are automatically reset to "pending".

## Advanced Usage

### Custom Database Location

All scripts accept a database path:
```bash
python claude_coordinator.py 4 /tmp/my_queue.db
python submit_task.py --db /tmp/my_queue.db submit "Task"
python claude_dashboard.py /tmp/my_queue.db
```

### Running a Single Worker

For debugging:
```bash
python claude_worker.py worker_1
```

### Task Priorities

Higher priority tasks are executed first:
```bash
# Urgent bug fix
python submit_task.py submit "Fix production bug in payment processor" --priority 10

# Nice to have
python submit_task.py submit "Update code comments" --priority 1
```

### Programmatic Task Submission

```python
from claude_queue import TaskQueue

queue = TaskQueue("claude_tasks.db")

task_id = queue.add_task(
    prompt="Implement feature X",
    working_dir="/path/to/project",
    context_files=["src/main.py", "src/utils.py"],
    expected_outputs=["src/feature_x.py", "tests/test_feature_x.py"],
    priority=5
)

print(f"Task {task_id} submitted")
```

## Monitoring and Debugging

**Check worker logs:**
```bash
tail -f logs/worker_1.log
```

**Check queue stats:**
```bash
python submit_task.py stats
```

**View specific task:**
```bash
python submit_task.py show <task_id>
```

**Monitor all Claude processes:**
```bash
watch -n 1 'ps aux | grep claude | grep -v grep'
```

## Cleanup

**Stop all workers:**
Press `Ctrl+C` in the coordinator terminal

**Clear completed tasks:**
```bash
# The database keeps historical records
# To start fresh, delete the database:
rm claude_tasks.db
```

## Tips

1. **Start small**: Test with 2-3 workers before scaling up
2. **Monitor resources**: Each Claude instance uses significant memory
3. **Use priorities**: Important tasks should have higher priority
4. **Check logs**: Worker logs contain detailed execution information
5. **Graceful shutdown**: Always use Ctrl+C to stop workers cleanly

## Troubleshooting

**Workers not claiming tasks:**
- Check that workers are running: `ps aux | grep claude_worker`
- Check worker logs in `logs/worker_*.log`
- Verify database exists and is accessible

**Tasks stuck in "claimed" state:**
- Workers may have crashed without updating status
- The coordinator runs cleanup on start
- Or manually: restart the coordinator

**Dashboard not updating:**
- Ensure database path is correct
- Check terminal size (dashboard needs minimum dimensions)

**Claude Code errors:**
- Check worker logs for full error output
- Verify Claude Code is installed: `which claude`
- Test Claude manually: `claude --message "test"`

## License

MIT
