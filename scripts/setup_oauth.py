#!/usr/bin/env python3
"""Obtain and cache OAuth2 user credentials for the GA4 AI agent.

Usage:
    uv run python scripts/setup_oauth.py
    uv run python scripts/setup_oauth.py --credentials path/to/credentials.json --output path/to/oauth_token.json

On first run opens a browser for Google OAuth2 consent. Subsequent runs
silently refresh the saved token without opening a browser.

After running, set GOOGLE_APPLICATION_CREDENTIALS in your .env to the output path.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import google.auth.transport.requests
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/analytics.readonly"]
TOKEN_URI = "https://oauth2.googleapis.com/token"
PROJECT_ROOT = Path(__file__).parent.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Authenticate with Google OAuth2 for GA4 access.")
    parser.add_argument(
        "--credentials",
        default=str(PROJECT_ROOT / "credentials.json"),
        help="Path to OAuth client secrets JSON from Google Cloud Console (default: credentials.json)",
    )
    parser.add_argument(
        "--output",
        default=str(PROJECT_ROOT / "oauth_token.json"),
        help="Path to save the OAuth token in ADC authorized_user format (default: oauth_token.json)",
    )
    return parser.parse_args()


def load_existing_token(token_path: Path) -> Credentials | None:
    if not token_path.exists():
        return None
    try:
        data = json.loads(token_path.read_text(encoding="utf-8"))
        return Credentials(
            token=data.get("token"),
            refresh_token=data.get("refresh_token"),
            token_uri=data.get("token_uri", TOKEN_URI),
            client_id=data["client_id"],
            client_secret=data["client_secret"],
            scopes=data.get("scopes"),
        )
    except (KeyError, json.JSONDecodeError, OSError) as exc:
        print(f"Warning: could not load existing token ({exc}). Starting fresh OAuth flow.")
        return None


def save_token(creds: Credentials, token_path: Path) -> None:
    # Build ADC authorized_user format manually — Credentials.to_json() omits the "type" field
    # which google.auth.default() requires to dispatch correctly.
    token_data = {
        "type": "authorized_user",
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri or TOKEN_URI,
    }
    token_path.write_text(json.dumps(token_data, indent=2), encoding="utf-8")


def main() -> None:
    args = parse_args()
    credentials_path = Path(args.credentials)
    token_path = Path(args.output)

    if not credentials_path.exists():
        print(f"Error: credentials file not found: {credentials_path}")
        print(
            "Download it from Google Cloud Console:\n"
            "  APIs & Services -> Credentials -> OAuth 2.0 Client IDs -> Download JSON"
        )
        sys.exit(1)

    creds = load_existing_token(token_path)

    if creds is not None and creds.refresh_token:
        if not creds.valid:
            print("Refreshing existing token...")
            try:
                creds.refresh(google.auth.transport.requests.Request())
                save_token(creds, token_path)
                print("Token refreshed and saved.")
            except Exception as exc:
                print(f"Token refresh failed ({exc}). Starting fresh OAuth flow.")
                creds = None
        else:
            print("Existing token is still valid — no browser flow needed.")
    else:
        creds = None

    if creds is None:
        print("Starting OAuth2 browser flow...")
        flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
        creds = flow.run_local_server(port=0)
        save_token(creds, token_path)
        print("OAuth2 flow complete. Token saved.")

    token_path_abs = token_path.resolve()
    print()
    print("=" * 60)
    print("Authentication successful!")
    print()
    print("Set this in your .env file:")
    print(f"  GOOGLE_APPLICATION_CREDENTIALS={token_path_abs}")
    print()
    print("Then verify GA4 connectivity with:")
    print("  uv run python scripts/verify_ga4.py")
    print("=" * 60)


if __name__ == "__main__":
    main()
