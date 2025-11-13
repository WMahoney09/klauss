#!/usr/bin/env python3
"""
Configuration management for Claude Code Orchestrator
Loads and merges TOML configuration with proper precedence
"""

import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, field

# Try to import TOML parser (Python 3.11+ has tomllib built-in)
try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        try:
            import toml as tomllib_compat
            # Wrap toml.load to match tomllib interface
            class tomllib:
                @staticmethod
                def load(f):
                    return tomllib_compat.load(f)
        except ImportError:
            print("Error: No TOML library found. Please install: pip install tomli", file=sys.stderr)
            sys.exit(1)


class ProjectBoundaryError(Exception):
    """Raised when attempting to work outside project boundaries"""
    pass


@dataclass
class ProjectConfig:
    """Project configuration section"""
    name: str = "auto-detect"
    description: str = ""


@dataclass
class DatabaseConfig:
    """Database configuration section"""
    path: Optional[str] = None
    auto_cleanup_days: int = 0


@dataclass
class SafetyConfig:
    """Safety configuration section"""
    enforce_project_boundary: bool = True
    allow_external_dirs: bool = False
    confirm_destructive: bool = False


@dataclass
class WorkersConfig:
    """Workers configuration section"""
    default_count: int = 4
    log_directory: str = "logs"
    restart_on_failure: bool = True
    heartbeat_interval: int = 5
    stale_timeout: int = 3600


@dataclass
class DefaultsConfig:
    """Default task settings"""
    priority: int = 5
    timeout: int = 1800
    poll_interval: float = 2.0


@dataclass
class MonitoringConfig:
    """Monitoring configuration"""
    dashboard_enabled: bool = True
    progress_updates: bool = True
    detailed_logging: bool = False


@dataclass
class CoordinationConfig:
    """Cross-project coordination"""
    shared_db: Optional[str] = None
    enabled: bool = False


@dataclass
class Config:
    """
    Complete configuration for Claude Code Orchestrator

    Loads configuration with precedence:
    1. Explicit kwargs (highest priority)
    2. Project config (.klauss.toml in project root)
    3. Default config (config.defaults.toml in klauss/)
    4. Hardcoded fallbacks (lowest priority)
    """

    project: ProjectConfig = field(default_factory=ProjectConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    safety: SafetyConfig = field(default_factory=SafetyConfig)
    workers: WorkersConfig = field(default_factory=WorkersConfig)
    defaults: DefaultsConfig = field(default_factory=DefaultsConfig)
    monitoring: MonitoringConfig = field(default_factory=MonitoringConfig)
    coordination: CoordinationConfig = field(default_factory=CoordinationConfig)

    # Optional sections
    related_projects: Dict[str, str] = field(default_factory=dict)
    directories: Dict[str, str] = field(default_factory=dict)

    # Computed paths
    project_root: Optional[Path] = None
    klauss_dir: Optional[Path] = None

    @staticmethod
    def find_project_root(start_path: Optional[Path] = None) -> Optional[Path]:
        """
        Find project root by walking up to find .git directory

        Returns None if no .git found (not in a git repo)
        """
        current = start_path or Path.cwd()

        # Walk up directory tree
        while current != current.parent:
            if (current / ".git").exists():
                return current
            current = current.parent

        # Not in a git repo, use current directory
        return Path.cwd()

    @staticmethod
    def find_klauss_dir(project_root: Path) -> Optional[Path]:
        """Find klauss directory (submodule or standalone)"""
        # Check for klauss submodule in project
        klauss_submodule = project_root / "klauss"
        if klauss_submodule.exists() and (klauss_submodule / "orchestrator.py").exists():
            return klauss_submodule

        # Check if we're already in klauss directory
        if (project_root / "orchestrator.py").exists():
            return project_root

        # Check parent (for when klauss is standalone)
        if (project_root.parent / "klauss" / "orchestrator.py").exists():
            return project_root.parent / "klauss"

        return None

    @classmethod
    def load(cls, overrides: Optional[Dict[str, Any]] = None) -> 'Config':
        """
        Load configuration with proper precedence

        Args:
            overrides: Dictionary of explicit overrides from code

        Returns:
            Merged configuration
        """
        overrides = overrides or {}

        # Step 1: Find project root and klauss directory
        project_root = cls.find_project_root()
        klauss_dir = cls.find_klauss_dir(project_root)

        # Step 2: Load default config from klauss/config.defaults.toml
        default_config = {}
        if klauss_dir:
            default_config_path = klauss_dir / "config.defaults.toml"
            if default_config_path.exists():
                with open(default_config_path, 'rb') as f:
                    default_config = tomllib.load(f)

        # Step 3: Load project config from .klauss.toml
        project_config = {}
        if project_root:
            project_config_path = project_root / ".klauss.toml"
            if project_config_path.exists():
                with open(project_config_path, 'rb') as f:
                    project_config = tomllib.load(f)

        # Step 4: Merge configurations (defaults → project → overrides)
        merged = cls._deep_merge(default_config, project_config)
        merged = cls._deep_merge(merged, overrides)

        # Step 5: Build Config object
        config = cls()
        config.project_root = project_root
        config.klauss_dir = klauss_dir

        # Populate sections
        if 'project' in merged:
            config.project = ProjectConfig(**merged['project'])
        if 'database' in merged:
            # Handle missing path key (not specified in TOML)
            db_config = merged['database'].copy()
            if 'path' not in db_config:
                db_config['path'] = None
            config.database = DatabaseConfig(**db_config)
        if 'safety' in merged:
            config.safety = SafetyConfig(**merged['safety'])
        if 'workers' in merged:
            config.workers = WorkersConfig(**merged['workers'])
        if 'defaults' in merged:
            config.defaults = DefaultsConfig(**merged['defaults'])
        if 'monitoring' in merged:
            config.monitoring = MonitoringConfig(**merged['monitoring'])
        if 'coordination' in merged:
            config.coordination = CoordinationConfig(**merged['coordination'])

        config.related_projects = merged.get('related_projects', {})
        config.directories = merged.get('directories', {})

        # Auto-detect project name if needed
        if config.project.name == "auto-detect" and project_root:
            config.project.name = project_root.name

        # Resolve database path
        if config.database.path is None:
            # Auto-generate: {project_name}_claude_tasks.db in klauss/
            if klauss_dir:
                db_filename = f"{config.project.name}_claude_tasks.db"
                config.database.path = str(klauss_dir / db_filename)
            else:
                # Fallback if klauss not found
                config.database.path = "claude_tasks.db"

        return config

    @staticmethod
    def _deep_merge(base: Dict, override: Dict) -> Dict:
        """Deep merge two dictionaries"""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = Config._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def get_absolute_path(self, path: str) -> Path:
        """Convert relative path to absolute (relative to project root)"""
        p = Path(path)
        if p.is_absolute():
            return p
        if self.project_root:
            return (self.project_root / p).resolve()
        return p.resolve()

    def is_within_project(self, path: str) -> bool:
        """Check if path is within project boundaries"""
        if not self.project_root:
            return True  # Can't enforce if no project root

        try:
            abs_path = self.get_absolute_path(path)
            return abs_path.is_relative_to(self.project_root)
        except (ValueError, OSError):
            return False

    def validate_working_dir(self, working_dir: Optional[str], allow_external: bool = False):
        """
        Validate working directory against safety settings

        Raises:
            ProjectBoundaryError: If working_dir is outside project and not allowed
        """
        if not working_dir:
            return  # None/empty is OK (uses current dir)

        if not self.safety.enforce_project_boundary:
            return  # Enforcement disabled

        if allow_external or self.safety.allow_external_dirs:
            return  # External dirs explicitly allowed

        if not self.is_within_project(working_dir):
            raise ProjectBoundaryError(
                f"Working directory '{working_dir}' is outside project root '{self.project_root}'. "
                f"To allow external directories, either:\n"
                f"  1. Pass allow_external=True to the task\n"
                f"  2. Set allow_external_dirs=True in ClaudeOrchestrator\n"
                f"  3. Set safety.allow_external_dirs=true in .klauss.toml"
            )

    def __repr__(self) -> str:
        return (
            f"Config(project={self.project.name}, "
            f"database={Path(self.database.path).name if self.database.path else 'None'}, "
            f"project_root={self.project_root})"
        )


if __name__ == '__main__':
    # Test configuration loading
    print("Testing Configuration Loading")
    print("=" * 60)

    config = Config.load()
    print(f"\nProject Root: {config.project_root}")
    print(f"Klauss Dir: {config.klauss_dir}")
    print(f"Project Name: {config.project.name}")
    print(f"Database Path: {config.database.path}")
    print(f"Enforce Boundaries: {config.safety.enforce_project_boundary}")
    print(f"Workers: {config.workers.default_count}")
    print(f"\nFull Config: {config}")
