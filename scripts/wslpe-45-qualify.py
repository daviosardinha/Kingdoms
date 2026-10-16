#!/usr/bin/env python3
"""One coordinated, fail-closed WSLPE-only 25-scenario lifecycle operator."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kingdoms.wslpe45_batch_operator import main

if __name__ == "__main__":
    raise SystemExit(main())
