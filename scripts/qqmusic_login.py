#!/usr/bin/env python3
"""QQ Music QR code login — scan with QQ mobile app to get a persistent credential.

Usage:
    python scripts/qqmusic_login.py
    python scripts/qqmusic_login.py --output /path/to/credential.json

The credential is automatically refreshed by the server when needed.
"""

import argparse
import asyncio
import sys
import time
from pathlib import Path

from qqmusic_api import Client
from qqmusic_api.models.login import QRCodeLoginEvents, QRLoginType

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from mcp_music_server.utils.qqmusic_auth import DEFAULT_CREDENTIAL_PATH, QQMusicAuth


async def main():
    parser = argparse.ArgumentParser(description="QQ Music QR code login")
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=str(DEFAULT_CREDENTIAL_PATH),
        help=f"Credential output path (default: {DEFAULT_CREDENTIAL_PATH})",
    )
    args = parser.parse_args()

    auth = QQMusicAuth(args.output)
    client = Client()

    print("Fetching QR code...")
    qr = await client.login.get_qrcode(QRLoginType.QQ)

    qr_path = qr.save()
    if not qr_path:
        print("ERROR: Failed to generate QR code image.")
        return 1

    print(f"\nQR code saved to: {qr_path}")
    print("Open the image and scan it with your QQ mobile app.")
    print("Waiting for scan", end="", flush=True)

    deadline = time.time() + 300  # 5 minute timeout

    while time.time() < deadline:
        result = await client.login.check_qrcode(qr)

        match result.event:
            case QRCodeLoginEvents.SCAN:
                print("\n  -> Scanned! Confirm login on your phone...", end="", flush=True)
            case QRCodeLoginEvents.CONF:
                print("\n  -> Confirmed! Authorizing...", end="", flush=True)
            case QRCodeLoginEvents.DONE:
                cred = result.credential
                auth.save_credential(cred)
                print(f"\n\nLogin successful!")
                print(f"  musicid: {cred.musicid}")
                print(f"  musickey: {cred.musickey[:24]}...")
                print(f"  saved to: {auth.path}")
                return 0
            case QRCodeLoginEvents.TIMEOUT:
                print("\n\nQR code expired. Please run the script again.")
                return 1
            case QRCodeLoginEvents.REFUSE:
                print("\n\nLogin refused on phone.")
                return 1

        await asyncio.sleep(2)
        print(".", end="", flush=True)

    print("\n\nTimeout: no scan detected within 5 minutes.")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
