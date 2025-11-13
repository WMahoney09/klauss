#!/bin/bash
# Quick start script for Claude Code Parallel Orchestrator

echo "=========================================="
echo "Claude Code Parallel Task Orchestrator"
echo "=========================================="
echo ""

# Check if Claude is installed
if ! command -v claude &> /dev/null; then
    echo "Error: Claude Code CLI not found in PATH"
    echo "Please install Claude Code first"
    exit 1
fi

echo "✓ Claude Code found: $(which claude)"
echo ""

# Check for Python dependencies
echo "Checking dependencies..."
if python3 -c "import tomli" 2>/dev/null || python3 -c "import tomllib" 2>/dev/null; then
    echo "✓ TOML parser available"
else
    echo "⚠️  TOML parser not found, installing..."
    pip3 install -r requirements.txt
    if [ $? -eq 0 ]; then
        echo "✓ Dependencies installed"
    else
        echo "❌ Failed to install dependencies"
        echo "   Please run: pip3 install -r requirements.txt"
        exit 1
    fi
fi
echo ""

# Make scripts executable
chmod +x *.py 2>/dev/null

# Check if database exists
if [ -f "claude_tasks.db" ]; then
    echo "ℹ Database already exists (claude_tasks.db)"
    read -p "Do you want to start fresh? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm claude_tasks.db
        echo "✓ Database deleted"
    fi
else
    echo "✓ Will create new database"
fi

echo ""
echo "Loading example tasks..."
python3 submit_task.py submit-file example_tasks.json

echo ""
echo "=========================================="
echo "Setup complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo ""
echo "1. Start the coordinator (in this terminal):"
echo "   python3 claude_coordinator.py 4"
echo ""
echo "2. Monitor with dashboard (in another terminal):"
echo "   python3 claude_dashboard.py"
echo ""
echo "3. Submit more tasks (in another terminal):"
echo "   python3 submit_task.py submit 'Your task here'"
echo ""
echo "4. Check stats anytime:"
echo "   python3 submit_task.py stats"
echo ""
echo "Press Enter to start the coordinator with 4 workers..."
read

python3 claude_coordinator.py 4
