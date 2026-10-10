"""Probe bank home pages once (robots.txt + home page). See backend/crawl/probe.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.crawl.probe import run  # noqa: E402

if __name__ == "__main__":
    run()
