#!/usr/bin/env python3
"""One-command helper to obtain LinkedIn token + URN and save GitHub secrets."""

from __future__ import annotations

import argparse
import getpass
import html
import json
import os
import secrets
import subprocess
import threading
import urllib.parse
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional

import requests

TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
ME_URL = "https://api.linkedin.com/v2/me"
USERINFO_URL = "https://api.linkedin.com/v2/userinfo"
DEFAULT_REDIRECT_URI = "http://localhost:8080/callback"
DEFAULT_SCOPE = "openid profile w_member_social"


@dataclass
class OAuthCallback:
    code: str = ""
    state: str = ""
    error: str = ""
    error_description: str = ""
    path: str = ""


class OAuthCallbackServer(HTTPServer):
    callback: OAuthCallback
    done_event: threading.Event

    def __init__(self, address: tuple[str, int]):
        self.callback = OAuthCallback()
        self.done_event = threading.Event()
        super().__init__(address, OAuthCallbackHandler)


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler API)
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        callback = OAuthCallback(
            code=query.get("code", [""])[0],
            state=query.get("state", [""])[0],
            error=query.get("error", [""])[0],
            error_description=query.get("error_description", [""])[0],
            path=self.path,
        )
        self.server.callback = callback
        self.server.done_event.set()

        body = (
            "<html><body style='font-family:Arial,sans-serif;'>"
            "<h3>LinkedIn authorization received.</h3>"
            "<p>You can close this tab and return to terminal.</p>"
            "</body></html>"
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args) -> None:
        return


def parse_port(redirect_uri: str) -> int:
    parsed = urllib.parse.urlparse(redirect_uri)
    if parsed.hostname not in ("127.0.0.1", "localhost"):
        raise ValueError("redirect_uri host must be localhost or 127.0.0.1")
    if not parsed.port:
        raise ValueError("redirect_uri must include an explicit port")
    return int(parsed.port)


def build_auth_url(client_id: str, redirect_uri: str, scope: str, state: str) -> str:
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": scope,
        "state": state,
    }
    return "https://www.linkedin.com/oauth/v2/authorization?" + urllib.parse.urlencode(params)


def exchange_token(code: str, redirect_uri: str, client_id: str, client_secret: str) -> str:
    response = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "client_secret": client_secret,
        },
        timeout=20,
    )
    if response.status_code >= 400:
        raise RuntimeError(
            f"Token exchange failed ({response.status_code}): "
            f"{response.text[:500]}"
        )
    data = response.json()
    token = data.get("access_token", "")
    if not token:
        raise RuntimeError(f"Token exchange returned no access_token: {json.dumps(data)}")
    return token


def fetch_person_urn(access_token: str) -> str:
    headers = {"Authorization": f"Bearer {access_token}"}

    # Preferred path if token has legacy /v2/me permission.
    response = requests.get(ME_URL, headers=headers, timeout=20)
    if response.status_code < 400:
        data = response.json()
        member_id = data.get("id", "")
        if member_id:
            return f"urn:li:person:{member_id}"

    # Fallback for OIDC tokens where /v2/userinfo is available and /v2/me is denied.
    userinfo = requests.get(USERINFO_URL, headers=headers, timeout=20)
    if userinfo.status_code >= 400:
        raise RuntimeError(
            "Failed to fetch member identity from both /v2/me and /v2/userinfo. "
            f"/v2/me={response.status_code}, /v2/userinfo={userinfo.status_code}. "
            f"userinfo_body={userinfo.text[:500]}"
        )

    userinfo_data = userinfo.json()
    subject = userinfo_data.get("sub", "")
    if not subject:
        raise RuntimeError(f"/v2/userinfo response missing sub: {json.dumps(userinfo_data)}")
    return f"urn:li:person:{subject}"


def detect_repo() -> Optional[str]:
    try:
        remote = subprocess.check_output(
            ["git", "remote", "get-url", "origin"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except subprocess.CalledProcessError:
        return None

    remote = remote.replace(".git", "")
    if remote.startswith("https://github.com/"):
        return remote.removeprefix("https://github.com/")
    if remote.startswith("git@github.com:"):
        return remote.removeprefix("git@github.com:")
    return None


def set_gh_secret(name: str, value: str, repo: str) -> None:
    proc = subprocess.run(
        ["gh", "secret", "set", name, "-R", repo],
        input=(value + "\n").encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", errors="ignore").strip())


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Capture LinkedIn OAuth token and set GitHub Actions secrets."
    )
    parser.add_argument("--client-id", default=os.getenv("LINKEDIN_CLIENT_ID", "").strip())
    parser.add_argument("--client-secret", default=os.getenv("LINKEDIN_CLIENT_SECRET", "").strip())
    parser.add_argument("--redirect-uri", default=DEFAULT_REDIRECT_URI)
    parser.add_argument("--scope", default=DEFAULT_SCOPE)
    parser.add_argument("--repo", default="")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--no-set-secrets", action="store_true")
    args = parser.parse_args()

    client_id = args.client_id.strip()
    if not client_id:
        print("ERROR: missing client id. Pass --client-id or set LINKEDIN_CLIENT_ID.")
        return 1

    client_secret = args.client_secret.strip()
    if not client_secret:
        client_secret = getpass.getpass("LinkedIn Primary Client Secret: ").strip()
    if not client_secret:
        print("ERROR: missing client secret.")
        return 1

    try:
        port = parse_port(args.redirect_uri)
    except ValueError as error:
        print(f"ERROR: {error}")
        return 1

    state = secrets.token_urlsafe(24)
    auth_url = build_auth_url(client_id, args.redirect_uri, args.scope, state)

    server = OAuthCallbackServer(("127.0.0.1", port))
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()

    print("Opening LinkedIn authorization page...")
    webbrowser.open(auth_url)
    print("Waiting for callback...")
    if not server.done_event.wait(timeout=args.timeout):
        print("ERROR: timed out waiting for OAuth callback.")
        return 1

    callback = server.callback
    if callback.error:
        print(
            "ERROR: OAuth authorization failed: "
            f"{callback.error} | {html.unescape(callback.error_description)}"
        )
        return 1
    if callback.state != state:
        print("ERROR: state mismatch; refusing to continue.")
        return 1
    if not callback.code:
        print(f"ERROR: callback did not contain code. Path: {callback.path}")
        return 1

    try:
        access_token = exchange_token(
            callback.code,
            args.redirect_uri,
            client_id,
            client_secret,
        )
        person_urn = fetch_person_urn(access_token)
    except Exception as error:  # explicit surfaced failure with details
        print(f"ERROR: {error}")
        return 1

    print("LinkedIn token and person URN obtained.")
    print(f"LINKEDIN_PERSON_URN={person_urn}")
    print(f"LINKEDIN_TOKEN={access_token[:14]}...{access_token[-8:]}")

    if args.no_set_secrets:
        print("Skipped GitHub secret update (--no-set-secrets).")
        return 0

    repo = args.repo.strip() or detect_repo()
    if not repo:
        print("ERROR: unable to detect GitHub repo. Pass --repo owner/name.")
        return 1

    try:
        set_gh_secret("LINKEDIN_TOKEN", access_token, repo)
        set_gh_secret("LINKEDIN_PERSON_URN", person_urn, repo)
    except Exception as error:
        print(f"ERROR: failed to set GitHub secrets: {error}")
        return 1

    print(f"Secrets saved to GitHub repo: {repo}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
