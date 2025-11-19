#!/usr/bin/env python3
"""
Test script for non-interactive mode support

This script tests that KLAUSS can run without user input prompts
in non-interactive contexts (background jobs, CI/CD, Docker, etc.)
"""

import os
import sys
import subprocess
import tempfile
import time
from pathlib import Path

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from orchestrator import ClaudeOrchestrator
from utils import is_interactive, get_env_int, get_env_bool


def test_is_interactive():
    """Test is_interactive() detection"""
    print("=" * 60)
    print("Testing is_interactive() detection")
    print("=" * 60)

    interactive = is_interactive()
    print(f"is_interactive(): {interactive}")
    print(f"sys.stdin.isatty(): {sys.stdin.isatty()}")
    print(f"sys.stdout.isatty(): {sys.stdout.isatty()}")
    print()


def test_env_vars():
    """Test environment variable handling"""
    print("=" * 60)
    print("Testing environment variable handling")
    print("=" * 60)

    # Test KLAUSS_WORKERS
    workers = get_env_int('KLAUSS_WORKERS', default=5)
    print(f"KLAUSS_WORKERS: {workers}")

    # Test KLAUSS_AUTO_START_WORKERS
    auto_start = get_env_bool('KLAUSS_AUTO_START_WORKERS', default=False)
    print(f"KLAUSS_AUTO_START_WORKERS: {auto_start}")

    # Test KLAUSS_DB_PATH
    db_path = os.getenv('KLAUSS_DB_PATH', 'default.db')
    print(f"KLAUSS_DB_PATH: {db_path}")
    print()


def test_orchestrator_no_prompt():
    """Test that orchestrator doesn't prompt in non-interactive mode"""
    print("=" * 60)
    print("Testing Orchestrator in non-interactive mode")
    print("=" * 60)

    # Create a temporary database
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tf:
        test_db = tf.name

    try:
        # Set environment variables
        os.environ['KLAUSS_AUTO_START_WORKERS'] = 'true'
        os.environ['KLAUSS_WORKERS'] = '2'

        print(f"Creating orchestrator with db: {test_db}")
        orch = ClaudeOrchestrator("test_orch", db_path=test_db)

        # Create a simple job
        job = orch.create_job("Test non-interactive job")

        # Add a task
        orch.add_subtask(job, "Echo test", priority=5)

        print("\n✓ Orchestrator created successfully without prompts!")
        print("✓ Job and task created successfully!")

        # Don't actually wait for completion since we're just testing the setup
        print("\nSkipping wait_and_collect (would start workers in real usage)")

    finally:
        # Cleanup
        if os.path.exists(test_db):
            os.remove(test_db)
        # Restore environment
        os.environ.pop('KLAUSS_AUTO_START_WORKERS', None)
        os.environ.pop('KLAUSS_WORKERS', None)

    print()


def test_background_execution():
    """Test running a script in background (simulates non-interactive context)"""
    print("=" * 60)
    print("Testing background execution simulation")
    print("=" * 60)

    # Create a simple test script
    test_script = Path(__file__).parent / "temp_test_script.py"
    test_script.write_text('''#!/usr/bin/env python3
import sys
sys.path.insert(0, ".")
from utils import is_interactive

print(f"is_interactive: {is_interactive()}")
print(f"stdin.isatty: {sys.stdin.isatty()}")
print(f"stdout.isatty: {sys.stdout.isatty()}")
''')

    try:
        # Run in background with redirected stdin/stdout
        result = subprocess.run(
            [sys.executable, str(test_script)],
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,  # No stdin
            timeout=5
        )

        print("Output from background script:")
        print(result.stdout)

        if "is_interactive: False" in result.stdout:
            print("✓ Background script correctly detected non-interactive mode!")
        else:
            print("✗ Background script failed to detect non-interactive mode")

    finally:
        # Cleanup
        test_script.unlink()

    print()


def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("KLAUSS Non-Interactive Mode Test Suite")
    print("=" * 60)
    print()

    test_is_interactive()
    test_env_vars()
    test_orchestrator_no_prompt()
    test_background_execution()

    print("=" * 60)
    print("All tests completed!")
    print("=" * 60)


if __name__ == '__main__':
    main()
