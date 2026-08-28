#!/usr/bin/env python3
"""Shared runtime and credential helpers for the 老实人AI image skill."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any


BASE_URL = "https://api.laoshirenai.com/v1"
MODEL = "gpt-image-2"
SECRET_NAME = "LAOSHIRENAI_IMAGE_API_KEY"
SDK_SPEC = "openai==3.5.0"


class ImagegenConfigError(RuntimeError):
    pass


def config_dir() -> Path:
    override = os.environ.get("LAOSHIRENAI_IMAGEGEN_CONFIG_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        root = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(root) / "LaoshirenAI" / "imagegen"
    root = os.environ.get("XDG_CONFIG_HOME", "").strip()
    if root:
        return Path(root) / "laoshirenai" / "imagegen"
    return Path.home() / ".config" / "laoshirenai" / "imagegen"


def metadata_path() -> Path:
    return config_dir() / "config.json"


def secret_file_path() -> Path:
    return config_dir() / "secret.key"


def runtime_dir() -> Path:
    return config_dir() / "runtime"


def runtime_python_path() -> Path:
    if os.name == "nt":
        return runtime_dir() / "Scripts" / "python.exe"
    return runtime_dir() / "bin" / "python"


def effective_base_url() -> str:
    if os.environ.get("LAOSHIRENAI_IMAGEGEN_TESTING") == "1":
        override = os.environ.get("LAOSHIRENAI_IMAGEGEN_TEST_BASE_URL", "").strip()
        if override:
            return override.rstrip("/")
    return BASE_URL


def _atomic_write(path: Path, data: bytes, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    tmp = Path(raw_tmp)
    try:
        with os.fdopen(fd, "wb") as handle:
            if os.name != "nt":
                os.fchmod(handle.fileno(), mode)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        if os.name != "nt":
            path.chmod(mode)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def _secure_windows_file(path: Path) -> None:
    if os.name != "nt":
        return
    username = os.environ.get("USERNAME", "").strip()
    if not username:
        raise ImagegenConfigError("USERNAME is unavailable; cannot restrict the credential file")
    result = subprocess.run(
        ["icacls", str(path), "/inheritance:r", "/grant:r", f"{username}:(F)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        path.unlink(missing_ok=True)
        raise ImagegenConfigError("failed to restrict the credential file with Windows ACLs")


def write_metadata(storage: str) -> None:
    payload = json.dumps(
        {"version": 1, "storage": storage, "base_url": BASE_URL, "model": MODEL},
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8") + b"\n"
    _atomic_write(metadata_path(), payload)


def read_metadata() -> dict[str, Any]:
    path = metadata_path()
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ImagegenConfigError(f"invalid configuration metadata: {exc}") from exc
    if not isinstance(value, dict):
        raise ImagegenConfigError("invalid configuration metadata")
    return value


def agent_switch_path() -> str | None:
    return shutil.which("agent-switch")


def store_secret_agent_switch(secret: str) -> None:
    command = agent_switch_path()
    if not command:
        raise ImagegenConfigError("agent-switch is not installed")
    result = subprocess.run(
        [command, "secret", "set", "--stdin", SECRET_NAME],
        input=secret.encode("utf-8"),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise ImagegenConfigError("agent-switch could not store the image key")
    write_metadata("agent-switch")


def load_secret_agent_switch() -> str:
    command = agent_switch_path()
    if not command or os.name == "nt":
        raise ImagegenConfigError("agent-switch credential storage is unavailable")
    read_fd, write_fd = os.pipe()
    try:
        result = subprocess.run(
            [command, "secret", "get", "--fd", str(write_fd), SECRET_NAME],
            pass_fds=(write_fd,),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=False,
        )
        os.close(write_fd)
        write_fd = -1
        chunks: list[bytes] = []
        while True:
            chunk = os.read(read_fd, 4096)
            if not chunk:
                break
            chunks.append(chunk)
        if result.returncode != 0:
            raise ImagegenConfigError("the image key is not available in Agent Switch")
        secret = b"".join(chunks).decode("utf-8").strip()
    finally:
        os.close(read_fd)
        if write_fd >= 0:
            os.close(write_fd)
    if not secret:
        raise ImagegenConfigError("the stored image key is empty")
    return secret


def store_secret_file(secret: str) -> None:
    path = secret_file_path()
    _atomic_write(path, secret.encode("utf-8") + b"\n")
    _secure_windows_file(path)
    write_metadata("file")


def load_secret_file() -> str:
    path = secret_file_path()
    if not path.exists():
        raise ImagegenConfigError("the local image credential has not been configured")
    if os.name != "nt" and path.stat().st_mode & 0o077:
        raise ImagegenConfigError("the local image credential permissions are too broad")
    secret = path.read_text(encoding="utf-8").strip()
    if not secret:
        raise ImagegenConfigError("the stored image key is empty")
    return secret


def load_secret() -> str:
    transient = os.environ.get(SECRET_NAME, "").strip()
    if transient:
        return transient
    storage = str(read_metadata().get("storage", "")).strip()
    if storage == "agent-switch":
        return load_secret_agent_switch()
    if storage == "file":
        return load_secret_file()
    if agent_switch_path() and os.name != "nt":
        try:
            return load_secret_agent_switch()
        except ImagegenConfigError:
            pass
    return load_secret_file()


def configured_storage() -> str:
    transient = os.environ.get(SECRET_NAME, "").strip()
    if transient:
        return "process environment"
    return str(read_metadata().get("storage", "unconfigured"))


def runtime_has_pinned_sdk(python: Path | str) -> bool:
    result = subprocess.run(
        [str(python), "-c", "import openai; raise SystemExit(0 if openai.__version__ == '3.5.0' else 1)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def ensure_runtime() -> Path:
    python = runtime_python_path()
    if python.is_file() and runtime_has_pinned_sdk(python):
        return python
    print("Preparing the one-time OpenAI image runtime. This does not send the API Key.")
    create = subprocess.run(
        [sys.executable, "-m", "venv", str(runtime_dir())],
        check=False,
    )
    if create.returncode != 0 or not python.is_file():
        raise ImagegenConfigError("failed to create the local Python runtime")
    install = subprocess.run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--only-binary=:all:",
            SDK_SPEC,
        ],
        check=False,
    )
    if install.returncode != 0 or not runtime_has_pinned_sdk(python):
        raise ImagegenConfigError("failed to install the pinned OpenAI Python SDK")
    return python
