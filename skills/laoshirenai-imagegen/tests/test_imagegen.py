from __future__ import annotations

import base64
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_DIR / "scripts"
PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="


class ImageAPIHandler(BaseHTTPRequestHandler):
    requests: list[dict[str, str]] = []

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _record(self, body: bytes = b"") -> None:
        self.__class__.requests.append(
            {
                "method": self.command,
                "path": self.path,
                "authorization": self.headers.get("Authorization", ""),
                "content_type": self.headers.get("Content-Type", ""),
                "body_prefix": body[:256].decode("utf-8", errors="replace"),
            }
        )

    def _json(self, payload: dict[str, object]) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:
        self._record()
        if self.path != "/v1/models":
            self.send_error(404)
            return
        self._json({"object": "list", "data": [{"id": "gpt-image-2", "object": "model"}]})

    def do_POST(self) -> None:
        size = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(size)
        self._record(body)
        if self.path not in {"/v1/images/generations", "/v1/images/edits"}:
            self.send_error(404)
            return
        self._json(
            {
                "created": 1710000000,
                "data": [{"b64_json": PNG_B64}],
                "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
            }
        )


class RedirectAPIHandler(ImageAPIHandler):
    def do_GET(self) -> None:
        self._record()
        self.send_response(302)
        self.send_header("Location", "/unexpected-target")
        self.end_headers()


@contextmanager
def image_api_server(handler=ImageAPIHandler):
    handler.requests = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


class ImagegenSkillTests(unittest.TestCase):
    def test_file_configuration_is_private_and_does_not_echo_secret(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            env = os.environ.copy()
            env["LAOSHIRENAI_IMAGEGEN_CONFIG_DIR"] = str(Path(raw_tmp) / "config")
            secret = "unit-image-key"
            result = subprocess.run(
                [sys.executable, str(SCRIPTS_DIR / "configure.py"), "--stdin", "--storage", "file"],
                input=secret + "\n",
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn(secret, result.stdout + result.stderr)
            secret_path = Path(env["LAOSHIRENAI_IMAGEGEN_CONFIG_DIR"]) / "secret.key"
            if os.name != "nt":
                self.assertEqual(secret_path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(secret_path.read_text(encoding="utf-8").strip(), secret)

    def test_agent_switch_storage_uses_stdin_and_inherited_fd(self) -> None:
        if os.name == "nt":
            self.skipTest("Agent Switch fd transport is POSIX-only")
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = Path(raw_tmp)
            bin_dir = tmp / "bin"
            bin_dir.mkdir()
            secret_store = tmp / "agent-switch-secret"
            mock = bin_dir / "agent-switch"
            mock.write_text(
                "#!/usr/bin/env python3\n"
                "import os, pathlib, sys\n"
                f"store=pathlib.Path({str(secret_store)!r})\n"
                "args=sys.argv[1:]\n"
                "if args[:3] == ['secret','set','--stdin']:\n"
                "    store.write_bytes(sys.stdin.buffer.read())\n"
                "    raise SystemExit(0)\n"
                "if args[:3] == ['secret','get','--fd']:\n"
                "    os.write(int(args[3]), store.read_bytes())\n"
                "    raise SystemExit(0)\n"
                "raise SystemExit(2)\n",
                encoding="utf-8",
            )
            mock.chmod(0o700)
            env = os.environ.copy()
            env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
            env["LAOSHIRENAI_IMAGEGEN_CONFIG_DIR"] = str(tmp / "config")
            secret = "unit-agent-switch-key"
            configure = subprocess.run(
                [sys.executable, str(SCRIPTS_DIR / "configure.py"), "--stdin", "--storage", "agent-switch"],
                input=secret + "\n",
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(configure.returncode, 0, configure.stderr)
            self.assertNotIn(secret, configure.stdout + configure.stderr)
            doctor = subprocess.run(
                [sys.executable, str(SCRIPTS_DIR / "doctor.py"), "--offline"],
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(doctor.returncode, 0, doctor.stderr)
            self.assertIn("Credential storage: agent-switch", doctor.stdout)
            self.assertNotIn(secret, doctor.stdout + doctor.stderr)

    def test_doctor_checks_model_without_exposing_key(self) -> None:
        with image_api_server() as base_url:
            env = self.runtime_env(base_url)
            result = subprocess.run(
                [sys.executable, str(SCRIPTS_DIR / "doctor.py")],
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Status: ready", result.stdout)
            self.assertNotIn(env["LAOSHIRENAI_IMAGE_API_KEY"], result.stdout + result.stderr)
            self.assertEqual(ImageAPIHandler.requests[-1]["path"], "/v1/models")
            self.assertEqual(ImageAPIHandler.requests[-1]["authorization"], "Bearer unit-image-key")

    def test_one_command_setup_configures_and_checks_access(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp, image_api_server() as base_url:
            env = self.runtime_env(base_url)
            env.pop("LAOSHIRENAI_IMAGE_API_KEY", None)
            env["LAOSHIRENAI_IMAGEGEN_CONFIG_DIR"] = str(Path(raw_tmp) / "config")
            secret = "unit-setup-key"
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "setup.py"),
                    "--stdin",
                    "--storage",
                    "file",
                    "--skip-runtime",
                ],
                input=secret + "\n",
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Setup complete", result.stdout)
            self.assertIn("Status: ready", result.stdout)
            self.assertNotIn(secret, result.stdout + result.stderr)

    def test_doctor_rejects_redirect_without_forwarding_key(self) -> None:
        with image_api_server(RedirectAPIHandler) as base_url:
            result = subprocess.run(
                [sys.executable, str(SCRIPTS_DIR / "doctor.py")],
                env=self.runtime_env(base_url),
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("unexpected redirect", result.stderr)
            self.assertEqual(len(RedirectAPIHandler.requests), 1)
            self.assertEqual(RedirectAPIHandler.requests[0]["path"], "/v1/models")

    def test_model_override_is_rejected(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS_DIR / "imagegen.py"),
                "generate",
                "--prompt",
                "test",
                "--model=gpt-image-other",
                "--dry-run",
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("model is fixed to gpt-image-2", result.stderr)

    def test_generate_and_edit_use_dedicated_images_endpoints(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp, image_api_server() as base_url:
            tmp = Path(raw_tmp)
            env = self.runtime_env(base_url)
            output_dir = tmp / "space 目录"
            output_dir.mkdir()
            generated = output_dir / "generated.png"
            generate = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "imagegen.py"),
                    "generate",
                    "--prompt",
                    "A red cube",
                    "--size",
                    "1024x1024",
                    "--quality",
                    "low",
                    "--out",
                    str(generated),
                ],
                env=env,
                text=True,
                capture_output=True,
                check=False,
                timeout=180,
            )
            self.assertEqual(generate.returncode, 0, generate.stderr)
            self.assertEqual(generated.read_bytes(), base64.b64decode(PNG_B64))

            edited = output_dir / "edited.png"
            edit = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "imagegen.py"),
                    "edit",
                    "--image",
                    str(generated),
                    "--prompt",
                    "Change only the background",
                    "--quality",
                    "low",
                    "--out",
                    str(edited),
                ],
                env=env,
                text=True,
                capture_output=True,
                check=False,
                timeout=180,
            )
            self.assertEqual(edit.returncode, 0, edit.stderr)
            self.assertEqual(edited.read_bytes(), base64.b64decode(PNG_B64))
            paths = [item["path"] for item in ImageAPIHandler.requests]
            self.assertIn("/v1/images/generations", paths)
            self.assertIn("/v1/images/edits", paths)
            for item in ImageAPIHandler.requests:
                self.assertEqual(item["authorization"], "Bearer unit-image-key")
            combined = generate.stdout + generate.stderr + edit.stdout + edit.stderr
            self.assertNotIn(env["LAOSHIRENAI_IMAGE_API_KEY"], combined)

    @staticmethod
    def runtime_env(base_url: str) -> dict[str, str]:
        env = os.environ.copy()
        env.update(
            {
                "LAOSHIRENAI_IMAGE_API_KEY": "unit-image-key",
                "LAOSHIRENAI_IMAGEGEN_TESTING": "1",
                "LAOSHIRENAI_IMAGEGEN_TEST_BASE_URL": base_url,
                "NO_PROXY": "127.0.0.1,localhost",
                "no_proxy": "127.0.0.1,localhost",
            }
        )
        return env


if __name__ == "__main__":
    unittest.main()
