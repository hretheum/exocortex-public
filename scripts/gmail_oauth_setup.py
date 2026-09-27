#!/usr/bin/env -S python3.12
# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

# scripts/gmail_oauth_setup.py — F6.2.2 OAuth bootstrap.
#
# Run ONCE manually to mint a refresh token. Saves to
# ~/.config/second-brain/gmail_token.json (chmod 600). Adapter
# (workers/sources/gmail.py) reads this token on every run.
#
# Prerequisites:
#   1. Google Cloud Console → enable Gmail API.
#   2. Create OAuth 2.0 Client ID (Desktop app).
#   3. Download credentials JSON to
#      ~/.config/second-brain/gmail_client_secret.json (chmod 600).
#   4. Run this script:
#         python3 scripts/gmail_oauth_setup.py
#      It will open your browser for consent. After consent, the refresh
#      token lands in gmail_token.json.
#
# Re-run only if the token is invalidated (revoked, scope changed, account
# password reset). Day-to-day fetches re-use the refresh token.

from __future__ import annotations
import os
import sys
from pathlib import Path

# Read-only Gmail scope is enough for thread aggregation. If we need to
# remove labels (mark threads "processed") we'll switch to gmail.modify.
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

DEFAULT_CONFIG_DIR = Path.home() / '.config' / 'second-brain'
CLIENT_SECRET = DEFAULT_CONFIG_DIR / 'gmail_client_secret.json'
TOKEN_PATH = DEFAULT_CONFIG_DIR / 'gmail_token.json'


def main() -> int:
    if not CLIENT_SECRET.exists():
        print(f'[gmail-oauth] missing {CLIENT_SECRET}', file=sys.stderr)
        print(
            '\nDownload the OAuth Client ID JSON from Google Cloud Console:\n'
            '  https://console.cloud.google.com/apis/credentials\n'
            'Pick "OAuth 2.0 Client ID → Desktop app", then save it as\n'
            f'  {CLIENT_SECRET}\n'
            'with chmod 600.',
            file=sys.stderr,
        )
        return 2

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as exc:
        print(f'[gmail-oauth] missing dep: {exc}', file=sys.stderr)
        print('  pip install google-auth-oauthlib', file=sys.stderr)
        return 2

    print('[gmail-oauth] launching browser consent flow…')
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
    creds = flow.run_local_server(port=0, open_browser=True)

    DEFAULT_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(creds.to_json(), encoding='utf-8')
    os.chmod(TOKEN_PATH, 0o600)
    print(f'[gmail-oauth] saved refresh token to {TOKEN_PATH}')
    print('[gmail-oauth] you can now run:  python3 -m workers.sources.gmail --once')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
