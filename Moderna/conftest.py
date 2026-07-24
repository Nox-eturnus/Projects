"""
pytest configuration — adds the project root to sys.path so that
test files in tests/ can import production modules directly.
"""

import sys
from pathlib import Path

# Add project root to sys.path for test discovery
project_root = str(Path(__file__).parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)
