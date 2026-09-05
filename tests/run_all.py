"""Run every offline suite. No Telegram connection required."""
from __future__ import annotations

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SUITES = ["test_engine.py", "test_handlers.py", "test_world.py", "test_pvp.py",
          "test_migration.py"]


def main() -> int:
    failed = []
    for s in SUITES:
        print(f"\n── {s} " + "─" * (46 - len(s)))
        r = subprocess.run([sys.executable, os.path.join(HERE, s)])
        if r.returncode != 0:
            failed.append(s)
    print("\n" + "═" * 50)
    if failed:
        print("❌ FAILED: " + ", ".join(failed))
        return 1
    print(f"✅ all {len(SUITES)} suites passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
