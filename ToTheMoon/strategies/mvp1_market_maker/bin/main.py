from __future__ import annotations

import json

from .runner import run_demo_cycle


if __name__ == "__main__":
    summary = run_demo_cycle()
    print(json.dumps(summary, indent=2))
