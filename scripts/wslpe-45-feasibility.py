#!/usr/bin/env python3
"""One-shot read-only WSLPE #21–45 native capability sweep."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kingdoms.wslpe_batch_feasibility import main

if __name__ == "__main__":
    raise SystemExit(main())
