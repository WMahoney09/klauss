#!/usr/bin/env python3
"""
Test script for task verification system

Tests:
1. Auto-detection of project type
2. Running verification hooks
3. Failing tasks when verification fails
4. Passing tasks when verification succeeds
"""

import os
import sys
import tempfile
import json
from pathlib import Path

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from verification import (
    ProjectTypeDetector,
    TaskVerifier,
    VerificationHook,
    format_verification_error
)


def test_project_type_detection():
    """Test auto-detection of project types"""
    print("=" * 60)
    print("Test 1: Project Type Detection")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        # Test 1: TypeScript project
        (tmppath / "tsconfig.json").write_text("{}")
        (tmppath / "package.json").write_text(json.dumps({
            "dependencies": {"react": "^18.0.0"}
        }))

        types = ProjectTypeDetector.detect_project_types(tmpdir)
        print(f"TypeScript + React project detected: {types}")
        assert 'typescript' in types, "Should detect TypeScript"
        assert 'react' in types, "Should detect React"
        assert 'node' in types, "Should detect Node"

        # Clean up for next test
        (tmppath / "tsconfig.json").unlink()
        (tmppath / "package.json").unlink()

        # Test 2: Python project
        (tmppath / "setup.py").write_text("")
        (tmppath / "pytest.ini").write_text("")

        types = ProjectTypeDetector.detect_project_types(tmpdir)
        print(f"Python project detected: {types}")
        assert 'python' in types, "Should detect Python"
        assert 'python-test' in types, "Should detect Python tests"

    print("✓ Project type detection tests passed\n")


def test_verification_hook_success():
    """Test successful verification"""
    print("=" * 60)
    print("Test 2: Successful Verification")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        # Create a simple test file
        test_file = tmppath / "test.py"
        test_file.write_text("print('hello')")

        # Create a hook that should pass
        hook = VerificationHook(
            command="python3 -m py_compile test.py",
            description="Compile Python file"
        )

        verifier = TaskVerifier(tmpdir)
        result = verifier.run_hook(hook)

        print(f"Hook result: passed={result.passed}, return_code={result.return_code}")
        assert result.passed, "Python compilation should succeed"
        assert result.return_code == 0, "Return code should be 0"

    print("✓ Successful verification test passed\n")


def test_verification_hook_failure():
    """Test failing verification"""
    print("=" * 60)
    print("Test 3: Failing Verification")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        # Create a Python file with syntax error
        test_file = tmppath / "bad.py"
        test_file.write_text("this is not valid python syntax {{{")

        # Create a hook that should fail
        hook = VerificationHook(
            command="python3 -m py_compile bad.py",
            description="Compile invalid Python file"
        )

        verifier = TaskVerifier(tmpdir)
        result = verifier.run_hook(hook)

        print(f"Hook result: passed={result.passed}, return_code={result.return_code}")
        print(f"Error: {result.error_message}")
        assert not result.passed, "Invalid Python should fail compilation"
        assert result.return_code != 0, "Return code should be non-zero"

    print("✓ Failing verification test passed\n")


def test_expected_outputs_verification():
    """Test expected output file verification"""
    print("=" * 60)
    print("Test 4: Expected Outputs Verification")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        # Create some output files
        (tmppath / "output1.txt").write_text("content")
        (tmppath / "subdir").mkdir()
        (tmppath / "subdir" / "output2.txt").write_text("content")

        verifier = TaskVerifier(tmpdir)

        # Test 1: All files exist
        expected = ["output1.txt", "subdir/output2.txt"]
        all_exist, status = verifier.check_expected_outputs(expected)

        print(f"All files exist: {all_exist}")
        print(f"File status: {status}")
        assert all_exist, "All expected files should exist"
        assert status["output1.txt"], "output1.txt should exist"
        assert status["subdir/output2.txt"], "subdir/output2.txt should exist"

        # Test 2: Missing file
        expected_with_missing = ["output1.txt", "missing.txt"]
        all_exist, status = verifier.check_expected_outputs(expected_with_missing)

        print(f"All files exist (with missing): {all_exist}")
        print(f"File status: {status}")
        assert not all_exist, "Should detect missing file"
        assert status["output1.txt"], "output1.txt should exist"
        assert not status["missing.txt"], "missing.txt should not exist"

    print("✓ Expected outputs verification test passed\n")


def test_default_hooks_generation():
    """Test generation of default verification hooks"""
    print("=" * 60)
    print("Test 5: Default Hooks Generation")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        # Set up a TypeScript project
        (tmppath / "tsconfig.json").write_text("{}")
        (tmppath / "package.json").write_text(json.dumps({
            "scripts": {"test": "jest"},
            "dependencies": {}
        }))

        # Detect project types
        project_types = ProjectTypeDetector.detect_project_types(tmpdir)
        print(f"Detected types: {project_types}")

        # Get default hooks
        hooks = ProjectTypeDetector.get_default_hooks(project_types, tmpdir)

        print(f"Generated {len(hooks)} default hooks:")
        for hook in hooks:
            print(f"  - {hook.description}: {hook.command}")

        assert len(hooks) > 0, "Should generate at least one hook"
        assert any("TypeScript" in h.description for h in hooks), "Should include TypeScript check"
        assert any("test" in h.command for h in hooks), "Should include test command"

    print("✓ Default hooks generation test passed\n")


def test_error_formatting():
    """Test verification error message formatting"""
    print("=" * 60)
    print("Test 6: Error Message Formatting")
    print("=" * 60)

    # Create mock verification results
    from verification import VerificationResult

    hook1 = VerificationHook("npx tsc --noEmit", "TypeScript check")
    hook2 = VerificationHook("npm test", "Run tests")

    result1 = VerificationResult(
        hook=hook1,
        passed=False,
        stdout="",
        stderr="error TS2304: Cannot find name 'foo'.\nerror TS2307: Cannot find module 'bar'.",
        return_code=2,
        error_message="Command failed with exit code 2"
    )

    result2 = VerificationResult(
        hook=hook2,
        passed=False,
        stdout="",
        stderr="FAIL tests/app.test.ts\n  Test suite failed to run",
        return_code=1,
        error_message="Command failed with exit code 1"
    )

    missing_files = ["src/output.ts", "dist/bundle.js"]

    error_msg = format_verification_error([result1, result2], missing_files)

    print("Formatted error message:")
    print(error_msg)
    print()

    assert "Missing output files" in error_msg, "Should mention missing files"
    assert "TypeScript check" in error_msg, "Should mention failed TypeScript check"
    assert "Run tests" in error_msg, "Should mention failed tests"

    print("✓ Error formatting test passed\n")


def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("KLAUSS Verification System Test Suite")
    print("=" * 60)
    print()

    try:
        test_project_type_detection()
        test_verification_hook_success()
        test_verification_hook_failure()
        test_expected_outputs_verification()
        test_default_hooks_generation()
        test_error_formatting()

        print("=" * 60)
        print("✓ All tests passed!")
        print("=" * 60)
        return 0

    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
