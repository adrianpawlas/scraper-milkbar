#!/usr/bin/env python3
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from scraper_orchestrator import main

if __name__ == "__main__":
    main()