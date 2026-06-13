"""One-time YouTube OAuth: produce the token the publisher uses to upload.

Run this ONCE on a machine with a browser. It opens a Google consent screen;
sign in with the channel's account, approve the upload permission, and the
refresh token is saved to YOUTUBE_TOKEN_FILE. After that, posting runs unattended.

    python -m posting.authorize
"""

from __future__ import annotations

from pathlib import Path

from config import get_settings
from posting.publisher import YOUTUBE_UPLOAD_SCOPE


def main() -> None:
    from google_auth_oauthlib.flow import InstalledAppFlow

    settings = get_settings()
    secrets = Path(settings.YOUTUBE_CLIENT_SECRETS)
    token = Path(settings.YOUTUBE_TOKEN_FILE)

    if not secrets.exists():
        raise SystemExit(
            f"OAuth client secrets not found at {secrets}.\n"
            "Download it from Google Cloud Console (OAuth client, type 'Desktop app')\n"
            "and save it there, or set YOUTUBE_CLIENT_SECRETS in .env."
        )

    flow = InstalledAppFlow.from_client_secrets_file(str(secrets), [YOUTUBE_UPLOAD_SCOPE])
    creds = flow.run_local_server(port=0)

    token.parent.mkdir(parents=True, exist_ok=True)
    token.write_text(creds.to_json())
    print(f"Authorized. Token saved to {token}")
    print("You can now post videos (set OFFLINE_MODE=false).")


if __name__ == "__main__":
    main()
