import sys
from pathlib import Path
import os


# Ensure the repository root is importable as a package root (so `import app` works).
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Tests should not require auth env vars.
os.environ.setdefault("SKIP_AUTH", "true")
