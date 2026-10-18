#!/usr/bin/env python3
"""Print the aggregated 45-technique source/runtime/learner release scoreboard."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kingdoms.wslpe45_closeout import main
if __name__ == "__main__":
    raise SystemExit(main())
