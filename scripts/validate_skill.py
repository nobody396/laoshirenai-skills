#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sys

import yaml


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "laoshirenai-imagegen"


def fail(message: str) -> None:
    raise SystemExit(message)


def main() -> int:
    required = [
        "SKILL.md",
        "agents/openai.yaml",
        "scripts/configure.py",
        "scripts/doctor.py",
        "scripts/imagegen.py",
        "scripts/setup.py",
        "vendor/openai-imagegen/scripts/image_gen.py",
        "LICENSE.txt",
        "NOTICE",
        "UPSTREAM.json",
    ]
    for relative in required:
        if not (SKILL / relative).is_file():
            fail(f"missing required file: {relative}")

    skill_text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    match = re.match(r"\A---\n(.*?)\n---\n", skill_text, flags=re.DOTALL)
    if not match:
        fail("SKILL.md has invalid frontmatter")
    metadata = yaml.safe_load(match.group(1))
    if metadata.get("name") != "laoshirenai-imagegen":
        fail("unexpected skill name")
    if not str(metadata.get("description", "")).strip():
        fail("skill description is empty")
    if "TODO" in skill_text:
        fail("unfinished TODO in SKILL.md")

    upstream = json.loads((SKILL / "UPSTREAM.json").read_text(encoding="utf-8"))
    official = SKILL / "vendor" / "openai-imagegen" / "scripts" / "image_gen.py"
    actual_hash = hashlib.sha256(official.read_bytes()).hexdigest()
    if actual_hash != upstream.get("script_sha256"):
        fail("OpenAI upstream script hash changed")
    if upstream.get("modified") is not False:
        fail("upstream script must remain marked unmodified")

    fence = "-" * 5
    forbidden = [f"{fence}BEGIN PRIVATE KEY{fence}", f"{fence}BEGIN OPENSSH PRIVATE KEY{fence}"]
    for file_path in SKILL.rglob("*"):
        if not file_path.is_file() or file_path.name == "LICENSE.txt":
            continue
        try:
            text = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for marker in forbidden:
            if marker in text:
                fail(f"secret material marker in {file_path.relative_to(ROOT)}")

    print("skill validation passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
