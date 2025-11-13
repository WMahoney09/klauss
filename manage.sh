#!/bin/bash
# Management script for Claude Code Parallel Orchestrator

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Get database path from config using Python helper
# This ensures consistency with orchestrator, workers, and coordinator
DB_PATH=$(python3 "$SCRIPT_DIR/get_db_path.py" 2>/dev/null)

# Check if we got a valid path
if [ -z "$DB_PATH" ] || [ $? -ne 0 ]; then
    echo "⚠️  Warning: Could not load database path from config" >&2
    echo "   Using fallback: $SCRIPT_DIR/claude_tasks.db" >&2
    DB_PATH="$SCRIPT_DIR/claude_tasks.db"
fi

show_help() {
    cat << EOF
Claude Code Parallel Task Orchestrator - Management Script

Usage: ./manage.sh <command> [options]

Commands:
    init-config         Create .klauss.toml config in current directory
    start [N]           Start coordinator with N workers (default: 4)
    stop                Stop all running workers gracefully
    workers             Show detailed worker status and resource usage
    dashboard           Launch the real-time dashboard
    submit <prompt>     Submit a single task
    submit-file <file>  Submit tasks from JSON file
    list [status]       List all tasks (optionally filter by status)
    stats               Show queue statistics
    show <id>           Show detailed task information
    logs <worker>       Tail logs for a specific worker (e.g., worker_1)
    clean               Remove database and logs
    ps                  Show all Claude processes
    kill                Force kill all Claude worker processes
    help                Show this help message

Examples:
    ./manage.sh start 8                                    # Start 8 workers
    ./manage.sh submit "Add tests for auth module"         # Submit task
    ./manage.sh submit-file my_tasks.json                  # Batch submit
    ./manage.sh list pending                               # Show pending tasks
    ./manage.sh logs worker_1                              # View worker logs
    ./manage.sh dashboard                                  # Open dashboard

EOF
}

case "$1" in
    init-config)
        CONFIG_FILE=".klauss.toml"
        TEMPLATE="$SCRIPT_DIR/.klauss.toml.example"

        if [ -f "$CONFIG_FILE" ]; then
            echo "❌ $CONFIG_FILE already exists in current directory"
            read -p "Overwrite? (y/N): " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                echo "Cancelled"
                exit 0
            fi
        fi

        if [ ! -f "$TEMPLATE" ]; then
            echo "❌ Template file not found: $TEMPLATE"
            exit 1
        fi

        cp "$TEMPLATE" "$CONFIG_FILE"
        echo "✓ Created $CONFIG_FILE"
        echo ""
        echo "Configuration file created! Edit $CONFIG_FILE to customize:"
        echo "  - Project name and description"
        echo "  - Database location"
        echo "  - Safety settings"
        echo "  - Worker defaults"
        echo "  - Cross-project coordination (if needed)"
        echo ""
        echo "For most projects, the defaults work fine without any changes."
        ;;

    start)
        WORKERS=${2:-4}
        echo "Starting coordinator with $WORKERS workers..."
        python3 "$SCRIPT_DIR/claude_coordinator.py" "$WORKERS" "$DB_PATH"
        ;;

    stop)
        echo "Stopping all workers..."
        pkill -f "claude_worker.py"
        pkill -f "claude_coordinator.py"
        sleep 1
        REMAINING=$(ps aux | grep -E "(claude_worker|claude_coordinator)" | grep -v grep | wc -l)
        if [ "$REMAINING" -eq 0 ]; then
            echo "✅ All workers stopped"
        else
            echo "⚠️  $REMAINING processes still running"
            echo "   Use './manage.sh kill' to force stop"
        fi
        ;;

    workers)
        echo "Worker Status"
        echo "============================================"
        echo ""

        # Count workers
        WORKER_COUNT=$(ps aux | grep "claude_worker.py" | grep -v grep | wc -l)
        COORD_COUNT=$(ps aux | grep "claude_coordinator.py" | grep -v grep | wc -l)

        echo "Active Processes:"
        echo "  Workers:     $WORKER_COUNT"
        echo "  Coordinator: $COORD_COUNT"
        echo ""

        if [ "$WORKER_COUNT" -gt 0 ]; then
            echo "Worker Details:"
            echo "----------------------------------------"
            printf "%-8s %-6s %-6s %-10s %s\n" "PID" "CPU%" "MEM%" "TIME" "COMMAND"
            ps aux | grep "claude_worker.py" | grep -v grep | awk '{printf "%-8s %-6s %-6s %-10s %s\n", $2, $3, $4, $10, $11 " " $12 " " $13}'
            echo ""
        else
            echo "No workers currently running"
            echo ""
        fi

        # Show queue stats if available
        if command -v python3 &> /dev/null; then
            python3 "$SCRIPT_DIR/submit_task.py" --db "$DB_PATH" stats 2>/dev/null || true
        fi
        ;;

    dashboard)
        python3 "$SCRIPT_DIR/claude_dashboard.py" "$DB_PATH"
        ;;

    submit)
        if [ -z "$2" ]; then
            echo "Error: Please provide a task prompt"
            echo "Usage: ./manage.sh submit <prompt>"
            exit 1
        fi
        python3 "$SCRIPT_DIR/submit_task.py" --db "$DB_PATH" submit "$2"
        ;;

    submit-file)
        if [ -z "$2" ]; then
            echo "Error: Please provide a JSON file"
            echo "Usage: ./manage.sh submit-file <file>"
            exit 1
        fi
        python3 "$SCRIPT_DIR/submit_task.py" --db "$DB_PATH" submit-file "$2"
        ;;

    list)
        if [ -z "$2" ]; then
            python3 "$SCRIPT_DIR/submit_task.py" --db "$DB_PATH" list
        else
            python3 "$SCRIPT_DIR/submit_task.py" --db "$DB_PATH" list --status "$2"
        fi
        ;;

    stats)
        python3 "$SCRIPT_DIR/submit_task.py" --db "$DB_PATH" stats
        ;;

    show)
        if [ -z "$2" ]; then
            echo "Error: Please provide a task ID"
            echo "Usage: ./manage.sh show <id>"
            exit 1
        fi
        python3 "$SCRIPT_DIR/submit_task.py" --db "$DB_PATH" show "$2"
        ;;

    logs)
        if [ -z "$2" ]; then
            echo "Error: Please provide a worker ID"
            echo "Usage: ./manage.sh logs <worker_id>"
            echo "Example: ./manage.sh logs worker_1"
            exit 1
        fi
        LOG_FILE="$SCRIPT_DIR/logs/${2}.log"
        if [ -f "$LOG_FILE" ]; then
            tail -f "$LOG_FILE"
        else
            echo "Error: Log file not found: $LOG_FILE"
            echo "Available logs:"
            ls -1 "$SCRIPT_DIR/logs/" 2>/dev/null || echo "No logs found"
        fi
        ;;

    clean)
        read -p "This will delete the database and all logs. Continue? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            rm -f "$DB_PATH"
            rm -rf "$SCRIPT_DIR/logs"
            echo "✓ Database and logs deleted"
        else
            echo "Cancelled"
        fi
        ;;

    ps)
        echo "Claude processes:"
        ps aux | grep -E "(claude|claude_worker|claude_coordinator)" | grep -v grep
        ;;

    kill)
        echo "Killing all Claude worker processes..."
        pkill -f "claude_worker.py"
        pkill -f "claude_coordinator.py"
        echo "✓ Done"
        ;;

    help|--help|-h)
        show_help
        ;;

    *)
        echo "Error: Unknown command '$1'"
        echo ""
        show_help
        exit 1
        ;;
esac
