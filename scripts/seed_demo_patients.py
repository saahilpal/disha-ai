#!/usr/bin/env python3
"""Seed synthetic demo patients for Disha AI show-readiness demonstrations.

Wrapper around scripts/demo_seed.py for backwards compatibility.
"""

from __future__ import annotations

import sys
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from scripts.demo_seed import main

if __name__ == "__main__":
    raise SystemExit(main())
