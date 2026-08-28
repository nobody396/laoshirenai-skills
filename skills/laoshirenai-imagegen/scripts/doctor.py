#!/usr/bin/env python3
"""Verify credential, network, group access, and model visibility without generating an image."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

from _runtime import MODEL, ImagegenConfigError, configured_storage, effective_base_url, load_secret


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, _req, _fp, _code, _msg, _headers, _newurl):
        return None


def check_access(secret: str) -> None:
    request = urllib.request.Request(
        f"{effective_base_url()}/models",
        headers={"Authorization": f"Bearer {secret}", "Accept": "application/json"},
        method="GET",
    )
    try:
        opener = urllib.request.build_opener(NoRedirectHandler())
        with opener.open(request, timeout=20) as response:
            body = response.read(4 * 1024 * 1024 + 1)
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise ImagegenConfigError("the image key is invalid or is not assigned to the image group") from exc
        if 300 <= exc.code < 400:
            raise ImagegenConfigError("the image API returned an unexpected redirect") from exc
        raise ImagegenConfigError(f"model check failed with HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise ImagegenConfigError(f"cannot reach the image API: {exc.reason}") from exc
    if len(body) > 4 * 1024 * 1024:
        raise ImagegenConfigError("model response is unexpectedly large")
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ImagegenConfigError("model response is not valid JSON") from exc
    models = {
        str(item.get("id", "")).strip()
        for item in payload.get("data", [])
        if isinstance(item, dict)
    }
    if MODEL not in models:
        raise ImagegenConfigError(f"this key cannot access {MODEL}; create it from the dedicated image group")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check 老实人AI image skill configuration")
    parser.add_argument("--offline", action="store_true", help="check credentials without a network request")
    args = parser.parse_args()
    try:
        secret = load_secret()
        print(f"Credential storage: {configured_storage()}")
        print(f"Base URL: {effective_base_url()}")
        print(f"Model: {MODEL}")
        if args.offline:
            print("Status: configured (network check skipped)")
            return 0
        check_access(secret)
        print("Status: ready")
        return 0
    except ImagegenConfigError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
