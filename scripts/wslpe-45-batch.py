#!/usr/bin/env python3
"""Source-only WSLPE 45-technique catalog; never contacts a Windows guest."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kingdoms.wslpe_batch_catalog import main

if __name__ == "__main__":
    raise SystemExit(main())
