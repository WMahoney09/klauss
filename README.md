# Meet Klauss 🐙
**Claude's friend who orchestrates multi-agent workflows.**

Klauss lets Claude Code break down complex tasks and execute them across multiple Claude instances simultaneously. Think of it as Claude's helpful assistant that coordinates parallel work.

> 🤖 **This was built with Claude for Claude to use**

## 🎯 Quick Start

### 1. Add Klauss to Your Project
#### Add as submodule
```bash
git submodule add https://github.com/WMahoney09/klauss.git klauss
git submodule update --init --recursive
```
#### Install dependencies
```bash
pip3 install -r klauss/requirements.txt
```

That's it! The requirements.txt includes tomli (TOML parser) for Python <3.11, or uses the built-in parser for Python 3.11+.

### 2. Talk to Claude Code

**That's it!** Now just talk to Claude Code normally. Claude will automatically handle workers:

```
You: "Build a REST API with authentication, including endpoints for
     login, registration, JWT middleware, and comprehensive tests."

Claude Code: "I'll break this down into 6 parallel tasks..."

             📊 Job Analysis:
                - 6 tasks can run in parallel
                - Suggesting 6 workers for optimal execution

             💡 I'd like to start 6 workers for parallel execution.
                This will spawn 6 Claude Code instances to work simultaneously.
                Start workers? (y/n):

You: "y"

Claude Code: 🚀 Starting 6 workers...
             ✅ 6 workers started successfully!

             [Workers execute tasks in parallel]
             [Shows real-time progress]

             "Done! Here's what I built..."
```

**Workers start automatically when needed!** Claude detects the optimal number based on your task.

## 💡 How It Works

```
┌─────────────────────────────────────────────────┐
│  You: Give Claude Code a complex task           │
└────────────────┬────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────┐
│  Claude Code: Uses Klauss orchestrator          │
│  - Breaks down into sub-tasks                   │
│  - Submits to parallel queue                    │
│  - Monitors progress                            │
│  - Synthesizes results                          │
└────────────────┬────────────────────────────────┘
                 │
                 ▼
         ┌───────────────┐
         │  Task Queue   │
         └───────┬───────┘
                 │
     ┌───────────┼───────────┬───────────┐
     ▼           ▼           ▼           ▼
┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐
│Worker 1 │ │Worker 2 │ │Worker 3 │ │Worker 4 │
│ Claude  │ │ Claude  │ │ Claude  │ │ Claude  │
└────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘
     │           │           │           │
     └───────────┴───────────┴───────────┘
                 │
                 ▼
         Results back to Claude Code
                 │
                 ▼
┌─────────────────────────────────────────────────┐
│  You: Receive complete, synthesized solution    │
└─────────────────────────────────────────────────┘
```

**You interact with Claude Code. Claude Code uses Klauss under the hood.**

## ✨ What This Gives You

- **🚀 Faster execution** - Complex tasks complete in parallel
- **🧠 Better decomposition** - Claude breaks work into optimal sub-tasks
- **👀 Visibility** - Real-time dashboard shows parallel progress
- **🐙 Automatic coordination** - Workers sync through shared queue and conventions
- **🎯 Consistent output** - Shared context ensures workers follow same patterns
- **📊 Task dependencies** - Define execution order with automatic dependency resolution
- **🔁 Auto-retry** - Tasks retry on failure with error context for learning
- **💾 Checkpoints** - Save progress and resume after interruptions
- **↩️ Rollback** - Track changes and undo if needed
- **🛡️ Safety** - Project boundaries enforced by default, circular dependency detection
- **✅ Quality verification** - Tasks auto-verified before marked complete
- **📦 Portable** - Add to any project via git submodule

## ✅ Task Verification & Quality Gates

Klauss automatically verifies task outputs before marking them complete, preventing false successes when code contains errors.

### Auto-Detection

Workers automatically detect your project type and run appropriate verification checks:

**TypeScript/JavaScript Projects:**
- TypeScript compilation (`npx tsc --noEmit`)
- ESLint checks (if configured)
- Test suite execution (if `npm test` script exists)

**Python Projects:**
- Type checking with mypy (if configured)
- Code formatting with black (if configured)
- pytest test suite (if pytest.ini exists)

**Go Projects:**
- Build verification (`go build ./...`)
- Test execution (`go test ./...`)

**Rust Projects:**
- Cargo check (`cargo check`)
- Test execution (`cargo test`)

### How It Works

```
Task Execution Flow:
1. Worker executes task with Claude CLI
2. Checks expected output files exist
3. Auto-detects project type
4. Runs verification hooks
5. Only marks complete if ALL checks pass
```

If verification fails, the task is marked as failed with detailed error messages, allowing for retry with context.

### Custom Verification Hooks

You can also specify custom verification commands for specific tasks:

```python
from orchestrator import ClaudeOrchestrator
from verification import VerificationHook

orch = ClaudeOrchestrator("my_orch")
job = orch.create_job("Build authentication system")

# Add task with custom verification
orch.add_subtask(
    job,
    "Implement JWT authentication",
    expected_outputs=["src/auth/jwt.ts"],
    verification_hooks=[
        VerificationHook(
            command="npx tsc --noEmit",
            description="TypeScript compilation"
        ),
        VerificationHook(
            command="npm run test:auth",
            description="Run auth tests"
        )
    ]
)
```

### Disabling Auto-Verification

For tasks that don't need verification:

```python
orch.add_subtask(
    job,
    "Update documentation",
    auto_verify=False  # Skip verification
)
```

### Benefits

- **No false positives** - Tasks only marked complete when actually working
- **Immediate feedback** - Catch errors during execution, not manual testing
- **Retry with context** - Failed verifications include error details for fixes
- **Zero configuration** - Auto-detects and enables appropriate checks

## 📖 Example Workflow

### Simple Task
```
You: "Add input validation to all API endpoints"

Claude: Breaking this down...
        [Creates 8 sub-tasks for different endpoints]
        [Workers execute in parallel]
        [2 minutes later]
        Done! Added validation to 8 endpoints. Here's what I did...
```

### Complex Multi-Step Task
```
You: "Build a user authentication system with:
      - Login and registration endpoints
      - JWT token management
      - Password hashing
      - Email verification
      - Comprehensive tests
      - API documentation"

Claude: This is complex - I'll use parallel execution...
        [Breaks down into 15+ sub-tasks]
        [Sets shared context for consistent patterns]
        [Defines dependencies between tasks]
        [Shows real-time progress]
        [Workers complete tasks simultaneously in correct order]
        [10 minutes later]
        Complete! Built full auth system with all features...
```

### Coordinated Parallel Development
```
You: "Build a TypeScript library with multiple modules,
      all following the same import patterns and testing style"

Claude: I'll coordinate workers to ensure consistency...
        [Sets shared conventions:]
        - import_style: "Use 'import type' for TypeScript types"
        - export_style: "Use named exports"
        - testing: "Use Jest with .test.ts extension"

        [Creates dependency chain:]
        - Core modules build in parallel
        - Feature modules wait for core
        - Tests run after all modules complete

        [Workers execute with consistent patterns]
        Result: Well-structured, consistent codebase!
```

## 🎛️ Monitoring

### Real-Time Dashboard

While workers execute, monitor progress:

```bash
# In another terminal
cd klauss
./manage.sh dashboard
```

You'll see:
- Active workers and their current tasks
- Completed/pending/failed task counts
- Real-time progress updates
- Task execution status

### Check Status Anytime

```bash
./manage.sh stats    # Quick statistics
./manage.sh list     # List all tasks
```

## 🔄 Worker Management

### Worker Lifecycle

**Auto-Start:** Workers start automatically when Claude needs them (with your permission)

**Auto-Shutdown:** Workers automatically stop after **5 minutes** of inactivity

**Manual Control:** You can manage workers anytime

### Check Worker Status

See what's running and resource usage:

```bash
./manage.sh workers
```

Output:
```
Worker Status
============================================

Active Processes:
  Workers:     4
  Coordinator: 1

Worker Details:
----------------------------------------
PID      CPU%   MEM%   TIME       COMMAND
12345    5.2    2.1    0:15.23    python3 claude_worker.py
12346    4.8    2.0    0:14.56    python3 claude_worker.py
12347    6.1    2.2    0:16.02    python3 claude_worker.py
12348    5.5    2.1    0:15.78    python3 claude_worker.py

Queue Statistics
========================================
Pending:      0
In Progress:  2
Completed:    15
Failed:       0
```

### Manual Worker Control

```bash
# Stop all workers gracefully
./manage.sh stop

# Force kill if needed
./manage.sh kill

# Start workers manually (alternative to auto-start)
./manage.sh start 6

# Check all Claude processes
./manage.sh ps
```

### From Claude Code

Claude can also stop workers programmatically:

```python
from orchestrator import ClaudeOrchestrator

orch = ClaudeOrchestrator("main")

# Check workers
status = orch.get_worker_status()
print(f"{status['process_count']} workers running")

# Stop workers
orch.stop_workers()
```

## 🔧 Configuration (Optional)

Klauss works out-of-the-box with zero configuration. For advanced use:

```bash
# Generate project config
./manage.sh init-config

# Edit .klauss.toml in your project root
# - Customize worker count
# - Set project boundaries
# - Configure cross-project coordination
```

See [Configuration Guide](#configuration) for details.

## 🤖 Non-Interactive Mode & Environment Variables

Klauss supports running in non-interactive contexts like CI/CD, Docker containers, and background jobs without prompting for user input.

### Environment Variables

Configure Klauss behavior via environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `KLAUSS_WORKERS` | Number of workers to spawn | Auto-calculated based on tasks |
| `KLAUSS_DB_PATH` | Path to task database | Auto-detected from project |
| `KLAUSS_AUTO_START_WORKERS` | Auto-start workers without prompting (`true`/`false`) | `false` |

### Non-Interactive Detection

Klauss automatically detects non-interactive contexts (no TTY) and:
- Skips user prompts
- Uses environment variable defaults
- Auto-starts workers when `KLAUSS_AUTO_START_WORKERS=true`

### Usage Examples

#### CI/CD Pipeline
```bash
# .github/workflows/claude-tasks.yml
- name: Run KLAUSS tasks
  env:
    KLAUSS_WORKERS: 10
    KLAUSS_AUTO_START_WORKERS: true
  run: |
    python3 orchestrator_script.py
```

#### Docker Container
```dockerfile
# Dockerfile
ENV KLAUSS_WORKERS=8
ENV KLAUSS_AUTO_START_WORKERS=true
ENV KLAUSS_DB_PATH=/app/tasks.db

CMD ["python3", "orchestrator_script.py"]
```

#### Background Job
```bash
# Run in background without prompts
KLAUSS_AUTO_START_WORKERS=true KLAUSS_WORKERS=5 python3 build_project.py &
```

#### Coordinator CLI

The coordinator supports both positional arguments and flags:

```bash
# Using environment variables
export KLAUSS_WORKERS=10
export KLAUSS_DB_PATH=tasks.db
python3 klauss/claude_coordinator.py

# Using CLI flags
python3 klauss/claude_coordinator.py --workers 10 --db tasks.db

# Using positional arguments (legacy)
python3 klauss/claude_coordinator.py 10 tasks.db

# Get help
python3 klauss/claude_coordinator.py --help
```

### Interactive Mode (Default)

When running in a terminal (TTY), Klauss will:
- Prompt for confirmation before starting workers
- Display interactive progress
- Allow manual control

To force auto-start even in interactive mode:
```bash
KLAUSS_AUTO_START_WORKERS=true python3 orchestrator_script.py
```

## 📚 Documentation

- **[ORCHESTRATOR_GUIDE.md](ORCHESTRATOR_GUIDE.md)** - For Claude Code: How to use Klauss internally
- **[Configuration](#configuration)** - Customize settings
- **[Advanced Usage](#advanced-usage)** - Manual mode, cross-project coordination

---

## Advanced Usage

### Manual Task Submission

While Claude Code uses Klauss automatically, you can also submit tasks manually:

```bash
./manage.sh submit "Your task description"
./manage.sh submit-file tasks.json
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

**Recommended: Use .klauss.toml configuration file**

```bash
# Create config file in your project root
./manage.sh init-config

# Edit .klauss.toml
cat > .klauss.toml << 'EOF'
[database]
path = "./my_custom_tasks.db"  # Relative to project root
EOF

# Now all Klauss commands will use this database
./manage.sh start 4
./manage.sh stats
python orchestrator.py  # All components read the same config
```

**Alternative: Pass database path explicitly to each script**

```bash
python claude_coordinator.py 4 /tmp/my_queue.db
python submit_task.py --db /tmp/my_queue.db submit "Task"
python claude_dashboard.py /tmp/my_queue.db
```

**Path Resolution Priority:**
1. Explicit path argument (highest priority)
2. Database path in `.klauss.toml` config file
3. Auto-detected: `{project_name}_claude_tasks.db` in project root
4. Default fallback: `claude_tasks.db`

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
- **Check database path consistency** - This is the most common issue!
  ```bash
  # Find all database files
  find . -name "*.db" -ls

  # Check what database workers are using (look in worker logs)
  cat logs/worker_1.log | grep "Database:"

  # Create .klauss.toml to ensure all components use same database
  cat > .klauss.toml << 'EOF'
[database]
path = "./claude_tasks.db"
EOF
  ```
- Check that workers are running: `ps aux | grep claude_worker`
- Check worker logs in `logs/worker_*.log`
- Verify database exists and is accessible
- All components (orchestrator, workers, coordinator) now use `Config.load()` for consistency

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
