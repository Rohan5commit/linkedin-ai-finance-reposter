#!/usr/bin/env python3
"""Delete LinkedIn share/ugc posts by URN."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from urllib.parse import quote

import requests

REQUEST_TIMEOUT = 20
LINKEDIN_POSTS_API_URL = "https://api.linkedin.com/rest/posts/{encoded_urn}"
LINKEDIN_API_VERSION = "202510"


def log(level: str, message: str) -> None:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    print(f"[{timestamp}] [{level}] {message}")


def parse_urns(raw_text: str) -> list[str]:
    normalized = raw_text.replace(",", "\n")
    urns = [item.strip() for item in normalized.splitlines() if item.strip()]
    return list(dict.fromkeys(urns))


def delete_post(urn: str, token: str) -> requests.Response:
    encoded_urn = quote(urn, safe="")
    url = LINKEDIN_POSTS_API_URL.format(encoded_urn=encoded_urn)
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Restli-Protocol-Version": "2.0.0",
        "Linkedin-Version": LINKEDIN_API_VERSION,
    }
    return requests.delete(url, headers=headers, timeout=REQUEST_TIMEOUT)


def main() -> int:
    token = os.getenv("LINKEDIN_TOKEN", "").strip()
    raw_urns = os.getenv("DELETE_SHARE_URNS", "").strip()

    if not token:
        log("ERROR", "Missing LINKEDIN_TOKEN.")
        return 1
    if not raw_urns:
        log("ERROR", "Missing DELETE_SHARE_URNS.")
        return 1

    urns = parse_urns(raw_urns)
    if not urns:
        log("ERROR", "No valid URNs found in DELETE_SHARE_URNS.")
        return 1

    failures: list[str] = []
    for urn in urns:
        try:
            response = delete_post(urn, token)
        except requests.RequestException as error:
            log("ERROR", f"DELETE failed for {urn}: {error}")
            failures.append(urn)
            continue

        if response.status_code in (200, 202, 204):
            log("INFO", f"Deleted {urn} (HTTP {response.status_code}).")
            continue

        log("ERROR", f"Failed to delete {urn} (HTTP {response.status_code}).")
        if response.text:
            print(response.text)
        failures.append(urn)

    if failures:
        log("ERROR", f"Deletion failed for {len(failures)} URN(s).")
        return 1

    log("INFO", f"Successfully deleted {len(urns)} post(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
