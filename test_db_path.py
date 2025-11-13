#!/usr/bin/env python3
"""
Test script to verify database path resolution works correctly
Tests the fix for Issue #1: Database path inconsistency
"""

import os
import sys
from pathlib import Path

# Test 1: Default behavior (no env var, no explicit path)
print("=" * 60)
print("Test 1: Default database path (no KLAUSS_DB_PATH)")
print("=" * 60)

# Clear any existing env var
if 'KLAUSS_DB_PATH' in os.environ:
    del os.environ['KLAUSS_DB_PATH']

from config import Config
config1 = Config.load()
print(f"Database path: {config1.database.path}")
print(f"Project name: {config1.project.name}")
print(f"Project root: {config1.project_root}")
print()

# Test 2: With KLAUSS_DB_PATH environment variable
print("=" * 60)
print("Test 2: With KLAUSS_DB_PATH environment variable")
print("=" * 60)

test_db_path = "/tmp/test_klauss_db.db"
os.environ['KLAUSS_DB_PATH'] = test_db_path

# Need to reload the config module to pick up new env var
import importlib
import config as config_module
importlib.reload(config_module)
from config import Config

config2 = Config.load()
print(f"KLAUSS_DB_PATH set to: {test_db_path}")
print(f"Database path: {config2.database.path}")
print(f"Match: {config2.database.path == test_db_path}")
print()

# Test 3: Orchestrator with env var
print("=" * 60)
print("Test 3: Orchestrator with KLAUSS_DB_PATH")
print("=" * 60)

from orchestrator import ClaudeOrchestrator
orch = ClaudeOrchestrator("test_orch")
print(f"Orchestrator database: {orch.queue.db_path}")
print(f"Match with env var: {orch.queue.db_path == test_db_path}")
print()

# Test 4: Explicit db_path overrides env var
print("=" * 60)
print("Test 4: Explicit db_path overrides KLAUSS_DB_PATH")
print("=" * 60)

explicit_path = "/tmp/explicit_db.db"
orch2 = ClaudeOrchestrator("test_orch2", db_path=explicit_path)
print(f"Explicit path: {explicit_path}")
print(f"Orchestrator database: {orch2.queue.db_path}")
print(f"Match: {orch2.queue.db_path == explicit_path}")
print()

print("=" * 60)
print("✅ All tests completed!")
print("=" * 60)
