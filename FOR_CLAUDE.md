# For Future Claude Agents

This document provides context for Claude Code instances working on Klauss.

## 🎯 Klauss Design Philosophy

**Primary Interface:** Users talk to Claude Code, which uses Klauss internally. The Python scripts are tools FOR Claude Code, not direct user commands.

**Key Principle:** Automatic with permission - Claude handles complexity, user retains control.

## 🏗️ Architecture Overview

### Core Components
```
orchestrator.py      ← Claude Code imports this to delegate work
├── config.py        ← Auto-loads .klauss.toml (optional)
├── claude_queue.py  ← SQLite task queue with atomic operations
├── claude_worker.py ← Wraps Claude CLI execution
└── claude_coordinator.py ← Spawns/monitors workers
```

### How It Works
1. **Claude analyzes request** → breaks into parallel tasks
2. **Checks workers** → `orchestrator.wait_and_collect()` auto-checks
3. **Prompts user** → "Start N workers? (y/n)"
4. **Spawns workers** → Dynamic count based on parallelism
5. **Executes tasks** → Workers claim from queue
6. **Auto-shutdown** → After 5 min idle (300s timeout)

## 🔑 Key Design Decisions

### Isolation Model
- **Default:** Each project gets isolated database (`{project}_claude_tasks.db`)
- **Cross-project:** Explicit `db_path` parameter when needed
- **Safety:** Project boundaries enforced unless `allow_external=True`

### Configuration Precedence
```
CLI kwargs > .klauss.toml > config.defaults.toml > hardcoded defaults
```

### Worker Lifecycle
- **Auto-start:** Via `ensure_workers_available()` in orchestrator
- **Smart sizing:** Match worker count to parallel tasks (capped at 10)
- **Auto-shutdown:** Coordinator monitors idle time
- **Manual control:** `./manage.sh stop|workers|kill`

## 📁 Important Files

### For Claude Code
- **`orchestrator.py`** - Main API, import and use `ClaudeOrchestrator`
- **`config.py`** - Loads config, enforces boundaries
- **`claude_queue.py`** - Queue operations (tasks, jobs, workers)

### For Users
- **`manage.sh`** - CLI commands (workers, stop, stats, etc.)
- **`README.md`** - User-facing documentation
- **`.klauss.toml.example`** - Config template

### Infrastructure
- **`claude_coordinator.py`** - Worker process manager
- **`claude_worker.py`** - Executes tasks via Claude CLI
- **`requirements.txt`** - Dependencies (tomli for Python <3.11)

## ⚠️ Important Notes

### What's NOT Tested Yet
- **Real Claude CLI execution** - Worker wrapper calls `claude --message` but hasn't been tested with actual parallel Claude instances
- **Database path in worker** - May need adjustment when spawned from different directories
- **Cross-platform** - Primarily tested on macOS

### Known Limitations
- **Worker detection** - Uses `ps aux | grep` (works on Unix-like, not Windows)
- **Process spawning** - Uses `subprocess.Popen` with `start_new_session` (Unix-specific)
- **Config requires TOML** - Fails without tomli/tomllib

### Configuration Gotchas
- **Database location** - Auto-generated in `klauss/` subdir of project
- **Worker logs** - Written to `klauss/logs/worker_*.log`
- **Idle timeout** - Default 300s, set in coordinator constructor

## 🚀 Future Enhancement Ideas

1. **Better worker output** - Currently logged to files, could stream to dashboard
2. **Task dependencies** - Parent/child exists but not used for execution order
3. **Result synthesis** - Basic helpers exist, could be enhanced
4. **Cross-platform** - Windows support for worker detection/spawning
5. **Dashboard enhancements** - More detailed worker metrics, real-time task output
6. **Cost tracking** - Monitor API usage across workers

## 💡 For Testing

```python
# Quick test of orchestrator (without actual workers)
from orchestrator import ClaudeOrchestrator

orch = ClaudeOrchestrator("test")
job = orch.create_job("Test job")
orch.add_subtask(job, "Task 1", priority=5)
orch.add_subtask(job, "Task 2", priority=5)

# Check worker detection
print(f"Workers running: {orch.check_workers_running()}")

# Check config
print(f"Project: {orch.config.project.name}")
print(f"Database: {orch.config.database.path}")
```

## 📝 Commit Message Style

Uses conventional commits with Claude attribution:
```
Brief summary

- Bullet points of changes
- Organized by category

🤖 Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>
```

## 🔄 Typical Development Workflow

### When User Asks Claude to Use Klauss

1. **Import orchestrator:**
   ```python
   from orchestrator import ClaudeOrchestrator
   ```

2. **Create orchestrator and job:**
   ```python
   orch = ClaudeOrchestrator("claude_main")
   job = orch.create_job("User's high-level goal")
   ```

3. **Break down and delegate:**
   ```python
   # Analyze complexity, break into sub-tasks
   orch.add_subtask(job, "Sub-task 1", priority=10)
   orch.add_subtask(job, "Sub-task 2", priority=10)
   orch.add_subtask(job, "Sub-task 3", priority=5)
   ```

4. **Execute and collect:**
   ```python
   # This auto-checks workers and prompts if needed
   results = orch.wait_and_collect(job)
   ```

5. **Synthesize and present:**
   ```python
   summary = orch.synthesize_results(results)
   # Present to user
   ```

### When Modifying Klauss Itself

1. **Read FOR_CLAUDE.md** (this file) to understand context
2. **Check existing architecture** before making changes
3. **Test with config.py standalone** to verify config loading
4. **Update documentation** - README.md for users, this file for Claude agents
5. **Follow commit message style** with Claude attribution

## 📚 Related Documentation

- **README.md** - User-facing guide (start here for user perspective)
- **ORCHESTRATOR_GUIDE.md** - Detailed orchestrator API reference
- **config.defaults.toml** - All available configuration options
- **.klauss.toml.example** - Example project configuration

## 🎯 Key Success Metrics

When Klauss is working well:
- ✅ Users don't need to manually manage workers
- ✅ Claude handles parallelism transparently
- ✅ Resources auto-cleanup when idle
- ✅ Clear visibility into what's running
- ✅ Safe by default (project boundaries)
- ✅ Explicit when needed (cross-project coordination)

---

**TL;DR:** Klauss is Claude's parallel execution tool. Users talk to Claude, Claude uses `orchestrator.py` to delegate work. Auto-manages workers with user permission. Config is optional. Everything's in the README.

Good luck! 🚀
