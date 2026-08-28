#!/usr/bin/env python3
"""One-command credential, runtime, and model-access setup."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

from _runtime import ImagegenConfigError, ensure_runtime


HERE = Path(__file__).resolve().parent


def main() -> int:
    parser = argparse.ArgumentParser(description="Set up the 老实人AI image Skill")
    parser.add_argument("--stdin", action="store_true", help="read the image Key from stdin")
    parser.add_argument("--storage", choices=("auto", "agent-switch", "file"), default="auto")
    parser.add_argument("--skip-runtime", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    configure = [sys.executable, str(HERE / "configure.py"), "--storage", args.storage]
    if args.stdin:
        configure.append("--stdin")
    configured = subprocess.run(configure, check=False)
    if configured.returncode != 0:
        return configured.returncode
    try:
        if not args.skip_runtime:
            ensure_runtime()
    except ImagegenConfigError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    doctor = subprocess.run([sys.executable, str(HERE / "doctor.py")], check=False)
    if doctor.returncode == 0:
        print("Setup complete. Codex can now generate images through the dedicated image Skill.")
    return doctor.returncode


if __name__ == "__main__":
    raise SystemExit(main())
