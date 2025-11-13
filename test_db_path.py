#!/usr/bin/env python3
"""
Test script to verify database path resolution works correctly
Tests the fix for Issue #1: Database path inconsistency
"""

import os
import sys
import tempfile
from pathlib import Path

from config import Config
from orchestrator import ClaudeOrchestrator
from claude_worker import ClaudeWorker
from claude_coordinator import ClaudeCoordinator

# Test 1: Default behavior (auto-detected from project root)
print("=" * 60)
print("Test 1: Default database path (auto-detected)")
print("=" * 60)

config1 = Config.load()
print(f"Database path: {config1.database.path}")
print(f"Project name: {config1.project.name}")
print(f"Project root: {config1.project_root}")
print(f"Expected pattern: {config1.project.name}_claude_tasks.db")
print()

# Test 2: With explicit path in config override
print("=" * 60)
print("Test 2: Config with explicit database path override")
print("=" * 60)

explicit_config_path = "/tmp/config_override_db.db"
config2 = Config.load(overrides={'database': {'path': explicit_config_path}})
print(f"Override path: {explicit_config_path}")
print(f"Database path: {config2.database.path}")
print(f"Match: {config2.database.path == explicit_config_path}")
print()

# Test 3: Orchestrator uses config
print("=" * 60)
print("Test 3: Orchestrator uses Config.load()")
print("=" * 60)

orch = ClaudeOrchestrator("test_orch")
print(f"Orchestrator database: {orch.queue.db_path}")
print(f"Matches config: {orch.queue.db_path == config1.database.path}")
print()

# Test 4: Explicit db_path overrides config
print("=" * 60)
print("Test 4: Explicit db_path overrides config")
print("=" * 60)

explicit_path = "/tmp/explicit_db.db"
orch2 = ClaudeOrchestrator("test_orch2", db_path=explicit_path)
print(f"Explicit path: {explicit_path}")
print(f"Orchestrator database: {orch2.queue.db_path}")
print(f"Match: {orch2.queue.db_path == explicit_path}")
print()

# Test 5: Worker uses Config.load()
print("=" * 60)
print("Test 5: Worker uses Config.load()")
print("=" * 60)

worker = ClaudeWorker("test_worker")
print(f"Worker database: {worker.queue.db_path}")
print(f"Matches config: {worker.queue.db_path == config1.database.path}")
print()

# Test 6: Coordinator uses Config.load()
print("=" * 60)
print("Test 6: Coordinator uses Config.load()")
print("=" * 60)

coordinator = ClaudeCoordinator(num_workers=2)
print(f"Coordinator database: {coordinator.db_path}")
print(f"Matches config: {coordinator.db_path == config1.database.path}")
print()

# Test 7: All components use same database path
print("=" * 60)
print("Test 7: Consistency across all components")
print("=" * 60)

print(f"Config:       {config1.database.path}")
print(f"Orchestrator: {orch.queue.db_path}")
print(f"Worker:       {worker.queue.db_path}")
print(f"Coordinator:  {coordinator.db_path}")
print(f"All match: {config1.database.path == orch.queue.db_path == worker.queue.db_path == coordinator.db_path}")
print()

print("=" * 60)
print("✅ All tests completed!")
print("=" * 60)
