#!/usr/bin/env python3
"""
KLAUSS Task Verification System

Provides verification hooks to validate task outputs before marking them complete.
This prevents tasks from being marked successful when they contain errors like:
- TypeScript compilation errors
- Missing imports
- Lint errors
- Test failures
"""

import os
import subprocess
import json
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass


@dataclass
class VerificationHook:
    """Represents a verification command to run after task completion"""
    command: str
    description: str
    timeout: int = 300  # 5 minutes default
    fail_on_error: bool = True  # Whether to fail task if this hook fails

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        return {
            'command': self.command,
            'description': self.description,
            'timeout': self.timeout,
            'fail_on_error': self.fail_on_error
        }

    @staticmethod
    def from_dict(data: Dict) -> 'VerificationHook':
        """Create from dictionary"""
        return VerificationHook(
            command=data['command'],
            description=data['description'],
            timeout=data.get('timeout', 300),
            fail_on_error=data.get('fail_on_error', True)
        )


@dataclass
class VerificationResult:
    """Result of running a verification hook"""
    hook: VerificationHook
    passed: bool
    stdout: str
    stderr: str
    return_code: int
    error_message: Optional[str] = None

    def to_dict(self) -> Dict:
        """Convert to dictionary for logging"""
        return {
            'hook_description': self.hook.description,
            'passed': self.passed,
            'return_code': self.return_code,
            'error_message': self.error_message,
            'stdout_preview': self.stdout[:500] if self.stdout else None,
            'stderr_preview': self.stderr[:500] if self.stderr else None
        }


class ProjectTypeDetector:
    """Auto-detects project type and suggests appropriate verification hooks"""

    @staticmethod
    def detect_project_types(working_dir: str) -> List[str]:
        """
        Detect project types based on marker files

        Returns:
            List of detected project types (e.g., ['typescript', 'node', 'react'])
        """
        working_path = Path(working_dir)
        detected_types = []

        # TypeScript/JavaScript detection
        if (working_path / 'tsconfig.json').exists():
            detected_types.append('typescript')
        if (working_path / 'package.json').exists():
            detected_types.append('node')
            # Check for React
            try:
                package_json = json.loads((working_path / 'package.json').read_text())
                dependencies = {**package_json.get('dependencies', {}),
                               **package_json.get('devDependencies', {})}
                if 'react' in dependencies:
                    detected_types.append('react')
            except:
                pass

        # Python detection
        if (working_path / 'setup.py').exists() or (working_path / 'pyproject.toml').exists():
            detected_types.append('python')
        if (working_path / 'requirements.txt').exists():
            detected_types.append('python')
        if (working_path / 'pytest.ini').exists() or (working_path / 'tox.ini').exists():
            detected_types.append('python-test')

        # Go detection
        if (working_path / 'go.mod').exists():
            detected_types.append('go')

        # Rust detection
        if (working_path / 'Cargo.toml').exists():
            detected_types.append('rust')

        return detected_types

    @staticmethod
    def get_default_hooks(project_types: List[str], working_dir: str) -> List[VerificationHook]:
        """
        Get default verification hooks for detected project types

        Args:
            project_types: List of detected project types
            working_dir: Working directory to check for specific tools

        Returns:
            List of recommended verification hooks
        """
        hooks = []
        working_path = Path(working_dir)

        # TypeScript verification
        if 'typescript' in project_types:
            hooks.append(VerificationHook(
                command='npx tsc --noEmit',
                description='TypeScript compilation check'
            ))

        # ESLint verification
        if 'node' in project_types and (working_path / '.eslintrc.js').exists() or \
           (working_path / '.eslintrc.json').exists() or (working_path / '.eslintrc').exists():
            hooks.append(VerificationHook(
                command='npx eslint . --ext .js,.jsx,.ts,.tsx',
                description='ESLint check',
                fail_on_error=False  # Lint warnings shouldn't always fail tasks
            ))

        # Node tests
        if 'node' in project_types:
            try:
                package_json = json.loads((working_path / 'package.json').read_text())
                if 'test' in package_json.get('scripts', {}):
                    hooks.append(VerificationHook(
                        command='npm test',
                        description='Run test suite',
                        timeout=600  # Tests might take longer
                    ))
            except:
                pass

        # Python verification
        if 'python' in project_types:
            # Type checking with mypy
            if (working_path / 'mypy.ini').exists() or (working_path / 'setup.cfg').exists():
                hooks.append(VerificationHook(
                    command='python3 -m mypy .',
                    description='Python type checking (mypy)',
                    fail_on_error=False
                ))

            # Black formatting check
            if (working_path / 'pyproject.toml').exists():
                hooks.append(VerificationHook(
                    command='python3 -m black --check .',
                    description='Python formatting check (black)',
                    fail_on_error=False
                ))

        # Python tests
        if 'python-test' in project_types:
            hooks.append(VerificationHook(
                command='python3 -m pytest',
                description='Run Python tests (pytest)',
                timeout=600
            ))

        # Go verification
        if 'go' in project_types:
            hooks.append(VerificationHook(
                command='go build ./...',
                description='Go build check'
            ))
            hooks.append(VerificationHook(
                command='go test ./...',
                description='Run Go tests',
                timeout=600
            ))

        # Rust verification
        if 'rust' in project_types:
            hooks.append(VerificationHook(
                command='cargo check',
                description='Rust check'
            ))
            hooks.append(VerificationHook(
                command='cargo test',
                description='Run Rust tests',
                timeout=600
            ))

        return hooks


class TaskVerifier:
    """Runs verification hooks on completed tasks"""

    def __init__(self, working_dir: str):
        """
        Initialize verifier

        Args:
            working_dir: Directory to run verification commands in
        """
        self.working_dir = working_dir

    def run_hook(self, hook: VerificationHook) -> VerificationResult:
        """
        Run a single verification hook

        Args:
            hook: Verification hook to run

        Returns:
            VerificationResult with outcome
        """
        print(f"[VERIFY] Running: {hook.description}")
        print(f"[VERIFY] Command: {hook.command}")

        try:
            result = subprocess.run(
                hook.command,
                shell=True,
                cwd=self.working_dir,
                capture_output=True,
                text=True,
                timeout=hook.timeout
            )

            passed = result.returncode == 0
            error_message = None if passed else f"Command failed with exit code {result.returncode}"

            return VerificationResult(
                hook=hook,
                passed=passed,
                stdout=result.stdout,
                stderr=result.stderr,
                return_code=result.returncode,
                error_message=error_message
            )

        except subprocess.TimeoutExpired:
            return VerificationResult(
                hook=hook,
                passed=False,
                stdout='',
                stderr='',
                return_code=-1,
                error_message=f"Verification timeout after {hook.timeout}s"
            )
        except Exception as e:
            return VerificationResult(
                hook=hook,
                passed=False,
                stdout='',
                stderr='',
                return_code=-1,
                error_message=f"Verification error: {str(e)}"
            )

    def verify_task(self, verification_hooks: List[VerificationHook]) -> Tuple[bool, List[VerificationResult]]:
        """
        Run all verification hooks for a task

        Args:
            verification_hooks: List of hooks to run

        Returns:
            Tuple of (all_passed, results)
        """
        results = []
        all_passed = True

        for hook in verification_hooks:
            result = self.run_hook(hook)
            results.append(result)

            if not result.passed and hook.fail_on_error:
                all_passed = False
                print(f"[VERIFY] ❌ FAILED: {hook.description}")
                if result.stderr:
                    print(f"[VERIFY] Error output: {result.stderr[:500]}")
            elif not result.passed:
                print(f"[VERIFY] ⚠️  WARNING: {hook.description} failed (non-critical)")
            else:
                print(f"[VERIFY] ✅ PASSED: {hook.description}")

        return all_passed, results

    def check_expected_outputs(self, expected_outputs: List[str]) -> Tuple[bool, Dict[str, bool]]:
        """
        Verify that expected output files exist

        Args:
            expected_outputs: List of expected file paths (relative to working_dir)

        Returns:
            Tuple of (all_exist, file_status_dict)
        """
        file_status = {}
        all_exist = True

        for expected_file in expected_outputs:
            file_path = Path(self.working_dir) / expected_file
            exists = file_path.exists()
            file_status[expected_file] = exists

            if exists:
                print(f"[VERIFY] ✅ Output file exists: {expected_file}")
            else:
                print(f"[VERIFY] ❌ Missing output file: {expected_file}")
                all_exist = False

        return all_exist, file_status


def format_verification_error(results: List[VerificationResult], missing_files: Optional[List[str]] = None) -> str:
    """
    Format verification failures into a clear error message

    Args:
        results: List of verification results
        missing_files: Optional list of missing output files

    Returns:
        Formatted error message
    """
    errors = []

    # Missing files
    if missing_files:
        errors.append(f"Missing output files: {', '.join(missing_files)}")

    # Failed verification hooks
    failed_hooks = [r for r in results if not r.passed and r.hook.fail_on_error]
    if failed_hooks:
        errors.append("Verification checks failed:")
        for result in failed_hooks:
            errors.append(f"  - {result.hook.description}: {result.error_message}")
            if result.stderr:
                # Include first few lines of error output
                stderr_lines = result.stderr.split('\n')[:5]
                for line in stderr_lines:
                    if line.strip():
                        errors.append(f"    {line}")

    return '\n'.join(errors)
