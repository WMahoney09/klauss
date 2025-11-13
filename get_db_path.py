#!/usr/bin/env python3
"""
Helper script to get the database path from config
Used by manage.sh to ensure consistency with Python scripts
"""

import sys
from config import Config

def main():
    """Load config and print database path"""
    try:
        config = Config.load()
        print(config.database.path)
        return 0
    except Exception as e:
        print(f"Error loading config: {e}", file=sys.stderr)
        return 1

if __name__ == '__main__':
    sys.exit(main())
