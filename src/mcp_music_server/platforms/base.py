"""Base platform interface for music providers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SongInfo:
    """Unified song information across all platforms."""

    song_id: str
    title: str
    artist: str
    album: str = ""
    duration: int = 0
    cover_url: str = ""
    play_url: str = ""
    lyric: str = ""
    platform: str = ""
    mv_id: str = ""

    def to_dict(self) -> dict:
        return {
            "song_id": self.song_id,
            "title": self.title,
            "artist": self.artist,
            "album": self.album,
            "duration": self.duration,
            "cover_url": self.cover_url,
            "play_url": self.play_url,
            "lyric": self.lyric[:500] + "..." if len(self.lyric) > 500 else self.lyric,
            "platform": self.platform,
            "mv_id": self.mv_id,
        }


@dataclass
class PlaylistInfo:
    """Unified playlist information across all platforms."""

    playlist_id: str
    title: str
    description: str = ""
    cover_url: str = ""
    song_count: int = 0
    songs: list[SongInfo] = field(default_factory=list)
    platform: str = ""

    def to_dict(self) -> dict:
        return {
            "playlist_id": self.playlist_id,
            "title": self.title,
            "description": self.description,
            "cover_url": self.cover_url,
            "song_count": self.song_count,
            "songs": [s.to_dict() for s in self.songs[:20]],
            "platform": self.platform,
        }


@dataclass
class SearchResult:
    """Search result wrapper."""

    keyword: str
    total: int
    songs: list[SongInfo] = field(default_factory=list)
    platform: str = ""

    def to_dict(self) -> dict:
        return {
            "keyword": self.keyword,
            "total": self.total,
            "songs": [s.to_dict() for s in self.songs],
            "platform": self.platform,
        }


class BasePlatform(ABC):
    """Abstract base for all music platform implementations."""

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Human-readable platform name."""
        ...

    @abstractmethod
    async def search(self, keyword: str, page: int = 1, limit: int = 20) -> SearchResult:
        """Search for songs by keyword."""
        ...

    @abstractmethod
    async def get_song(self, song_id: str) -> Optional[SongInfo]:
        """Get detailed song information."""
        ...

    @abstractmethod
    async def get_play_url(self, song_id: str, quality: str = "standard") -> Optional[str]:
        """Get playable audio URL. Quality: 'low', 'standard', 'high', 'lossless'."""
        ...

    @abstractmethod
    async def get_lyric(self, song_id: str) -> Optional[str]:
        """Get song lyrics."""
        ...

    @abstractmethod
    async def get_playlist(self, playlist_id: str) -> Optional[PlaylistInfo]:
        """Get playlist details and song list."""
        ...

    @abstractmethod
    async def get_hot_playlists(self, limit: int = 20) -> list[PlaylistInfo]:
        """Get hot/popular playlists."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the platform is currently available."""
        ...


class PlatformError(Exception):
    """Raised when a platform operation fails."""

    def __init__(self, platform: str, message: str):
        self.platform = platform
        self.message = message
        super().__init__(f"[{platform}] {message}")
