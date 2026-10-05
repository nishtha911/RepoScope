# Root conftest.py — ensures the repo root is on sys.path so that
# 'backend.app.*' imports resolve correctly when running pytest from the root.
import sys
from pathlib import Path

# Add repo root to path (parent of this file)
sys.path.insert(0, str(Path(__file__).parent))
