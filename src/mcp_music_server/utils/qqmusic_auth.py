"""QQ Music credential management with automatic refresh."""

import json
import logging
from pathlib import Path

from qqmusic_api import Client, Credential

logger = logging.getLogger(__name__)

DEFAULT_CREDENTIAL_PATH = Path.home() / ".config" / "mcp-music-server" / "qqmusic_credential.json"


class QQMusicAuth:
    """Manages QQ Music credentials with automatic refresh using qqmusic-api."""

    def __init__(self, credential_path: str | Path | None = None):
        self._credential_path = Path(credential_path) if credential_path else DEFAULT_CREDENTIAL_PATH
        self._credential: Credential | None = None

    @property
    def is_loaded(self) -> bool:
        return self._credential is not None

    @property
    def path(self) -> Path:
        return self._credential_path

    @property
    def musicid(self) -> int:
        if self._credential:
            return self._credential.musicid
        return 0

    def load(self) -> bool:
        """Load credential from file. Returns True if loaded successfully."""
        if not self._credential_path.exists():
            logger.debug("Credential file not found: %s", self._credential_path)
            return False
        try:
            data = json.loads(self._credential_path.read_text())
            self._credential = Credential.model_validate(data)
            logger.debug("Credential loaded for musicid=%s", self._credential.musicid)
            return True
        except Exception as e:
            logger.warning("Failed to load credential: %s", e)
            return False

    async def ensure_valid(self) -> bool:
        """Ensure credential is valid. Refreshes if expired."""
        if self._credential is None:
            if not self.load():
                return False

        client = Client(credential=self._credential)
        try:
            is_expired = await client.login.check_expired()
        except Exception as e:
            logger.warning("Credential expiry check failed: %s", e)
            return False

        if is_expired:
            logger.info("Credential expired, refreshing...")
            try:
                self._credential = await client.login.refresh_credential()
                self._save()
                logger.info("Credential refreshed successfully")
            except Exception as e:
                logger.warning("Failed to refresh credential: %s", e)
                return False

        return True

    def get_cookies(self) -> dict[str, str]:
        """Build cookie dict from credential (matching library's cookie construction)."""
        if self._credential is None:
            return {}
        cred = self._credential
        uin = cred.str_musicid or str(cred.musicid)
        return {
            "uin": uin,
            "qqmusic_uin": uin,
            "qm_keyst": cred.musickey,
            "qqmusic_key": cred.musickey,
        }

    def save_credential(self, credential: Credential):
        """Save new credential to file."""
        self._credential = credential
        self._save()

    def _save(self):
        if self._credential is None:
            return
        self._credential_path.parent.mkdir(parents=True, exist_ok=True)
        self._credential_path.write_text(self._credential.model_dump_json(indent=2))
