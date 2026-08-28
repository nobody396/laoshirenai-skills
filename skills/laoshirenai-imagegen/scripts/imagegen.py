#!/usr/bin/env python3
"""Thin launcher around the unmodified OpenAI official imagegen CLI."""

from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys

from _runtime import (
    MODEL,
    SDK_SPEC,
    ImagegenConfigError,
    effective_base_url,
    load_secret,
    runtime_has_pinned_sdk,
    runtime_python_path,
)


OFFICIAL_SCRIPT = Path(__file__).resolve().parent.parent / "vendor" / "openai-imagegen" / "scripts" / "image_gen.py"


def runtime_command(dry_run: bool) -> list[str]:
    if dry_run:
        return [sys.executable, str(OFFICIAL_SCRIPT)]
    configured_python = runtime_python_path()
    if configured_python.is_file() and runtime_has_pinned_sdk(configured_python):
        return [str(configured_python), str(OFFICIAL_SCRIPT)]
    if importlib.util.find_spec("openai") is not None:
        return [sys.executable, str(OFFICIAL_SCRIPT)]
    uv = shutil.which("uv")
    if uv:
        return [uv, "run", "--quiet", "--with", SDK_SPEC, "python", str(OFFICIAL_SCRIPT)]
    raise ImagegenConfigError(
        "the image runtime is unavailable; run scripts/setup.py once or install uv"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        add_help=False,
        description="Run the OpenAI official imagegen CLI through the dedicated 老实人AI image route",
    )
    parser.add_argument("args", nargs=argparse.REMAINDER)
    parsed = parser.parse_args()
    args = parsed.args
    if not args or args[0] not in {"generate", "edit", "generate-batch"}:
        print("Usage: imagegen.py {generate|edit|generate-batch} [official imagegen options]", file=sys.stderr)
        return 2
    if any(arg == "--model" or arg.startswith("--model=") for arg in args):
        print(f"Error: model is fixed to {MODEL}", file=sys.stderr)
        return 2
    dry_run = "--dry-run" in args
    try:
        env = os.environ.copy()
        env["OPENAI_BASE_URL"] = effective_base_url()
        env["OPENAI_API_KEY"] = "dry-run-placeholder" if dry_run else load_secret()
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        enforced = ["--model", MODEL]
        if args[0] == "generate-batch":
            enforced += ["--concurrency", "1", "--max-attempts", "1"]
        command = runtime_command(dry_run) + args + enforced
        result = subprocess.run(command, env=env, check=False)
        return result.returncode
    except ImagegenConfigError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
