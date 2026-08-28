#!/usr/bin/env python3
"""Configure the dedicated 老实人AI image API key without exposing it in argv."""

from __future__ import annotations

import argparse
import getpass
import os
import sys

from _runtime import (
    ImagegenConfigError,
    agent_switch_path,
    config_dir,
    store_secret_agent_switch,
    store_secret_file,
)


def read_secret(from_stdin: bool) -> str:
    if from_stdin:
        secret = sys.stdin.readline().strip()
    else:
        if not sys.stdin.isatty():
            raise ImagegenConfigError("use --stdin for non-interactive configuration")
        secret = getpass.getpass("老实人AI 独立生图 API Key: ").strip()
    if not secret:
        raise ImagegenConfigError("API Key cannot be empty")
    if any(ch.isspace() for ch in secret):
        raise ImagegenConfigError("API Key cannot contain whitespace")
    return secret


def main() -> int:
    parser = argparse.ArgumentParser(description="Configure the dedicated 老实人AI image API key")
    parser.add_argument("--stdin", action="store_true", help="read the key from stdin instead of prompting")
    parser.add_argument("--storage", choices=("auto", "agent-switch", "file"), default="auto")
    args = parser.parse_args()
    try:
        secret = read_secret(args.stdin)
        storage = args.storage
        if storage == "auto":
            storage = "agent-switch" if agent_switch_path() and os.name != "nt" else "file"
        if storage == "agent-switch":
            store_secret_agent_switch(secret)
        else:
            store_secret_file(secret)
        print(f"Configured the dedicated image key using {storage} storage.")
        print(f"Configuration directory: {config_dir()}")
        return 0
    except ImagegenConfigError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
