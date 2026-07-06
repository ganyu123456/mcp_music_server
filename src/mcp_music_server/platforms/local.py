"""Local/offline music file platform implementation."""

import os
from pathlib import Path
from typing import Optional

from mutagen import File as MutagenFile
from mutagen.easyid3 import EasyID3
from mutagen.flac import FLAC
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4

from .base import (
    BasePlatform,
    PlaylistInfo,
    SearchResult,
    SongInfo,
)


class LocalPlatform(BasePlatform):
    """Local file-based music playback platform."""

    SUPPORTED_EXTENSIONS = {".mp3", ".flac", ".m4a", ".wav", ".ogg", ".wma", ".ape"}

    def __init__(self, music_dir: str = ""):
        self._music_dir = music_dir or os.path.expanduser("~/Music")
        self._available = os.path.isdir(self._music_dir)

    @property
    def platform_name(self) -> str:
        return "local"

    def is_available(self) -> bool:
        return self._available

    def _scan_files(self) -> list[Path]:
        """Scan music directory for supported files."""
        if not self._available:
            return []

        files = []
        try:
            for root, _, filenames in os.walk(self._music_dir):
                for fname in filenames:
                    ext = Path(fname).suffix.lower()
                    if ext in self.SUPPORTED_EXTENSIONS:
                        files.append(Path(root) / fname)
        except PermissionError:
            pass

        return files

    def _parse_metadata(self, filepath: Path) -> Optional[SongInfo]:
        """Extract metadata from an audio file."""
        try:
            mf = MutagenFile(str(filepath))
            if mf is None:
                return None

            title = ""
            artist = ""
            album = ""
            duration = 0

            ext = filepath.suffix.lower()

            if ext == ".mp3":
                duration = int(mf.info.length) if hasattr(mf.info, "length") else 0
                try:
                    tags = EasyID3(str(filepath))
                    title = tags.get("title", [filepath.stem])[0]
                    artist = tags.get("artist", ["Unknown"])[0]
                    album = tags.get("album", [""])[0]
                except Exception:
                    title = filepath.stem
                    artist = "Unknown"
            elif ext == ".flac":
                flac = FLAC(str(filepath))
                duration = int(flac.info.length) if hasattr(flac.info, "length") else 0
                title = flac.get("title", [filepath.stem])[0]
                artist = flac.get("artist", ["Unknown"])[0]
                album = flac.get("album", [""])[0]
            elif ext == ".m4a":
                mp4 = MP4(str(filepath))
                duration = int(mp4.info.length) if hasattr(mp4.info, "length") else 0
                title = mp4.get("\xa9nam", [filepath.stem])[0]
                artist = mp4.get("\xa9ART", ["Unknown"])[0]
                album = mp4.get("\xa9alb", [""])[0]
            else:
                duration = int(mf.info.length) if hasattr(mf.info, "length") else 0
                title = filepath.stem

            return SongInfo(
                song_id=f"local:{filepath}",
                title=title,
                artist=artist,
                album=album,
                duration=duration,
                play_url=f"file://{filepath.absolute()}",
                platform=self.platform_name,
            )
        except Exception:
            return None

    async def search(
        self, keyword: str, page: int = 1, limit: int = 20
    ) -> SearchResult:
        """Search local music files by keyword."""
        all_files = self._scan_files()

        keyword_lower = keyword.lower()
        results = []
        for fp in all_files:
            fname = fp.stem.lower()
            if keyword_lower in fname:
                info = self._parse_metadata(fp)
                if info:
                    results.append(info)
            elif keyword_lower in str(fp.parent).lower():
                info = self._parse_metadata(fp)
                if info:
                    results.append(info)

        total = len(results)
        start = (page - 1) * limit
        end = start + limit
        paged = results[start:end]

        return SearchResult(
            keyword=keyword,
            total=total,
            songs=paged,
            platform=self.platform_name,
        )

    async def get_song(self, song_id: str) -> Optional[SongInfo]:
        """Get local song info by file path."""
        filepath = song_id
        if song_id.startswith("local:"):
            filepath = song_id[6:]

        fp = Path(filepath)
        if not fp.exists() or not fp.is_file():
            return None

        return self._parse_metadata(fp)

    async def get_play_url(
        self, song_id: str, quality: str = "standard"
    ) -> Optional[str]:
        """Get local file play URL."""
        filepath = song_id
        if song_id.startswith("local:"):
            filepath = song_id[6:]

        fp = Path(filepath)
        if not fp.exists():
            return None

        return f"file://{fp.absolute()}"

    async def get_lyric(self, song_id: str) -> Optional[str]:
        """Try to find local lyric file (.lrc) next to the audio file. Only searches localized lyrics, not external APIs."""
        filepath = song_id
        if song_id.startswith("local:"):
            filepath = song_id[6:]

        fp = Path(filepath)
        if not fp.exists():
            return None

        lrc_path = fp.with_suffix(".lrc")
        if lrc_path.exists():
            try:
                with open(lrc_path, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception:
                pass

        return None

    async def get_playlist(self, playlist_id: str) -> Optional[PlaylistInfo]:
        """Treat a directory as a playlist."""
        dirpath = playlist_id
        if playlist_id.startswith("local:"):
            dirpath = playlist_id[6:]

        dp = Path(dirpath)
        if not dp.exists() or not dp.is_dir():
            return None

        songs = []
        for ext in self.SUPPORTED_EXTENSIONS:
            for fp in dp.glob(f"*{ext}"):
                info = self._parse_metadata(fp)
                if info:
                    songs.append(info)

        return PlaylistInfo(
            playlist_id=playlist_id,
            title=dp.name,
            description=f"Local directory: {dp.absolute()}",
            cover_url="",
            song_count=len(songs),
            songs=songs,
            platform=self.platform_name,
        )

    async def get_hot_playlists(self, limit: int = 20) -> list[PlaylistInfo]:
        """List subdirectories as playlists."""
        if not self._available:
            return []

        playlists = []
        try:
            for entry in sorted(Path(self._music_dir).iterdir()):
                if entry.is_dir() and not entry.name.startswith("."):
                    songs = []
                    for ext in self.SUPPORTED_EXTENSIONS:
                        songs.extend(
                            [
                                s
                                for s in (self._parse_metadata(fp) for fp in entry.glob(f"*{ext}"))
                                if s
                            ]
                        )

                    playlist = PlaylistInfo(
                        playlist_id=f"local:{entry.absolute()}",
                        title=entry.name,
                        description=f"Local directory: {entry.absolute()}",
                        cover_url="",
                        song_count=len(songs),
                        songs=songs[:20],
                        platform=self.platform_name,
                    )
                    playlists.append(playlist)

                    if len(playlists) >= limit:
                        break
        except PermissionError:
            pass

        return playlists
