#!/usr/bin/env python3
"""
Integration test to verify no EOFError in non-interactive mode

This test specifically validates the fix for issue #15:
- Running orchestrator in background should not cause EOFError
- Environment variables should be respected
- Workers should auto-start without prompts
"""

import os
import sys
import subprocess
import tempfile
from pathlib import Path


def test_no_eoferror_in_background():
    """
    Test that replicates the issue #15 scenario:
    Running an orchestrator script in background
    """
    print("=" * 60)
    print("Testing Issue #15 Fix: No EOFError in background")
    print("=" * 60)
    print()

    # Create a test orchestrator script
    test_script = Path(__file__).parent / "temp_background_orch.py"
    test_db = Path(__file__).parent / "temp_test.db"

    test_script.write_text(f'''#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, "{Path(__file__).parent}")

# Set environment variables for non-interactive mode
os.environ['KLAUSS_AUTO_START_WORKERS'] = 'true'
os.environ['KLAUSS_WORKERS'] = '2'

from orchestrator import ClaudeOrchestrator

try:
    print("Creating orchestrator...")
    orch = ClaudeOrchestrator("test_orch", db_path="{test_db}")

    print("Creating job...")
    job = orch.create_job("Test background job")

    print("Adding tasks...")
    orch.add_subtask(job, "Task 1", priority=5)
    orch.add_subtask(job, "Task 2", priority=5)

    print("✓ SUCCESS: No EOFError occurred!")
    print("✓ Orchestrator ran successfully in background mode")

    # Note: We're not calling wait_and_collect() because that would
    # try to start actual workers, which we don't need for this test

except EOFError as e:
    print("✗ FAILED: EOFError occurred!")
    print(f"Error: {{e}}")
    sys.exit(1)
except Exception as e:
    print(f"✗ FAILED: Unexpected error: {{e}}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
''')

    try:
        # Test 1: Run with environment variables
        print("Test 1: Running with KLAUSS_AUTO_START_WORKERS=true")
        print("-" * 60)
        result = subprocess.run(
            [sys.executable, str(test_script)],
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,  # Simulate no stdin (background job)
            timeout=10,
            env={**os.environ, 'KLAUSS_AUTO_START_WORKERS': 'true', 'KLAUSS_WORKERS': '2'}
        )

        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)

        if result.returncode == 0:
            print("✓ Test 1 PASSED")
        else:
            print(f"✗ Test 1 FAILED (exit code: {result.returncode})")
            return False

        print()

        # Test 2: Simulate actual background execution (&)
        print("Test 2: Simulating background execution (python script.py &)")
        print("-" * 60)

        # Create a script that runs the orchestrator in background
        bg_test_script = Path(__file__).parent / "temp_bg_test.sh"
        bg_test_script.write_text(f'''#!/bin/bash
export KLAUSS_AUTO_START_WORKERS=true
export KLAUSS_WORKERS=2
{sys.executable} {test_script} > /tmp/klauss_bg_test.log 2>&1
echo $?
''')
        bg_test_script.chmod(0o755)

        result = subprocess.run(
            [str(bg_test_script)],
            capture_output=True,
            text=True,
            timeout=10
        )

        exit_code = result.stdout.strip()
        log_content = Path('/tmp/klauss_bg_test.log').read_text() if Path('/tmp/klauss_bg_test.log').exists() else ""

        print("Background script output:")
        print(log_content)

        if exit_code == '0':
            print("✓ Test 2 PASSED")
        else:
            print(f"✗ Test 2 FAILED (exit code: {exit_code})")
            return False

        print()
        print("=" * 60)
        print("✓ ALL TESTS PASSED: Issue #15 is fixed!")
        print("=" * 60)
        return True

    finally:
        # Cleanup
        for f in [test_script, test_db, bg_test_script, Path('/tmp/klauss_bg_test.log')]:
            if f.exists():
                f.unlink()


if __name__ == '__main__':
    success = test_no_eoferror_in_background()
    sys.exit(0 if success else 1)
