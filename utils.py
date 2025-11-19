#!/usr/bin/env python3
"""
KLAUSS Utility Functions
Common utilities for interactive detection, environment variables, etc.
"""

import sys
import os
from typing import Optional


def is_interactive() -> bool:
    """
    Detect if running in an interactive context (terminal with TTY)

    Returns:
        True if both stdin and stdout are connected to a TTY, False otherwise

    Examples:
        - Running in terminal: True
        - Running in background (python script.py &): False
        - Running in CI/CD: False
        - Running in Docker without TTY: False
    """
    return sys.stdin.isatty() and sys.stdout.isatty()


def get_env_int(var_name: str, default: Optional[int] = None) -> Optional[int]:
    """
    Get an integer value from environment variable

    Args:
        var_name: Environment variable name
        default: Default value if not set or invalid

    Returns:
        Integer value from environment or default
    """
    value = os.getenv(var_name)
    if value is None:
        return default

    try:
        return int(value)
    except ValueError:
        print(f"Warning: Invalid value for {var_name}='{value}', using default: {default}")
        return default


def get_env_bool(var_name: str, default: bool = False) -> bool:
    """
    Get a boolean value from environment variable

    Args:
        var_name: Environment variable name
        default: Default value if not set

    Returns:
        Boolean value from environment or default

    Accepts: true/false, yes/no, 1/0 (case insensitive)
    """
    value = os.getenv(var_name)
    if value is None:
        return default

    value_lower = value.lower()
    if value_lower in ('true', 'yes', '1'):
        return True
    elif value_lower in ('false', 'no', '0'):
        return False
    else:
        print(f"Warning: Invalid boolean value for {var_name}='{value}', using default: {default}")
        return default


def get_env_str(var_name: str, default: Optional[str] = None) -> Optional[str]:
    """
    Get a string value from environment variable

    Args:
        var_name: Environment variable name
        default: Default value if not set

    Returns:
        String value from environment or default
    """
    return os.getenv(var_name, default)
