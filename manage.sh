#!/bin/bash
# Management script for Claude Code Parallel Orchestrator

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DB_PATH="$SCRIPT_DIR/claude_tasks.db"

show_help() {
    cat << EOF
Claude Code Parallel Task Orchestrator - Management Script

Usage: ./manage.sh <command> [options]

Commands:
    start [N]           Start coordinator with N workers (default: 4)
    dashboard           Launch the real-time dashboard
    submit <prompt>     Submit a single task
    submit-file <file>  Submit tasks from JSON file
    list [status]       List all tasks (optionally filter by status)
    stats               Show queue statistics
    show <id>           Show detailed task information
    logs <worker>       Tail logs for a specific worker (e.g., worker_1)
    clean               Remove database and logs
    ps                  Show all Claude processes
    kill                Kill all Claude worker processes
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
    start)
        WORKERS=${2:-4}
        echo "Starting coordinator with $WORKERS workers..."
        python3 "$SCRIPT_DIR/claude_coordinator.py" "$WORKERS" "$DB_PATH"
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
