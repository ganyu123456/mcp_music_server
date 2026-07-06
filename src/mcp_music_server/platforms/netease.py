"""NetEase Cloud Music platform implementation."""

import hashlib
import json
import math
import random
import string
from typing import Optional

import httpx

from .base import (
    BasePlatform,
    PlatformError,
    PlaylistInfo,
    SearchResult,
    SongInfo,
)


def _random_user_agent() -> str:
    agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    ]
    return random.choice(agents)


class NeteasePlatform(BasePlatform):
    """NetEase Cloud Music (163 Music) implementation."""

    BASE_URL = "https://music.163.com"
    API_URL = f"{BASE_URL}/api"

    def __init__(self, cookie: str = ""):
        self._cookie = cookie
        self._available = True

    @property
    def platform_name(self) -> str:
        return "netease"

    def is_available(self) -> bool:
        return self._available

    def _headers(self) -> dict:
        return {
            "User-Agent": _random_user_agent(),
            "Referer": "https://music.163.com/",
            "Cookie": self._cookie or "os=pc; appver=2.0.0;",
        }

    @staticmethod
    def _create_csrf_token() -> str:
        return "".join(random.choices(string.ascii_lowercase + string.digits, k=32))

    async def search(
        self, keyword: str, page: int = 1, limit: int = 20
    ) -> SearchResult:
        """Search songs on NetEase Cloud Music."""
        url = f"{self.API_URL}/cloudsearch/pc"
        offset = (page - 1) * limit
        params = {
            "s": keyword,
            "type": 1,
            "offset": offset,
            "limit": limit,
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(url, params=params, headers=self._headers())
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as e:
            raise PlatformError(self.platform_name, f"Search failed: {e}")

        if data.get("code") != 200:
            raise PlatformError(
                self.platform_name,
                f"Search failed: code={data.get('code')}, msg={data.get('message')}",
            )

        result = data.get("result", {})
        songs_data = result.get("songs", [])

        songs = []
        for item in songs_data:
            duration_ms = item.get("dt", 0)
            artists = ", ".join(ar.get("name", "") for ar in item.get("ar", []))
            album_info = item.get("al", {})
            song = SongInfo(
                song_id=str(item.get("id", "")),
                title=item.get("name", ""),
                artist=artists,
                album=album_info.get("name", ""),
                duration=duration_ms // 1000,
                cover_url=album_info.get("picUrl", ""),
                platform=self.platform_name,
                mv_id=str(item.get("mv", 0)) if item.get("mv") else "",
            )
            songs.append(song)

        return SearchResult(
            keyword=keyword,
            total=result.get("songCount", len(songs)),
            songs=songs,
            platform=self.platform_name,
        )

    async def get_song(self, song_id: str) -> Optional[SongInfo]:
        """Get song detail from NetEase."""
        url = f"{self.API_URL}/song/detail"
        params = {"ids": f"[{song_id}]"}

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url, params=params, headers=self._headers())
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as e:
            raise PlatformError(self.platform_name, f"Get song failed: {e}")

        if data.get("code") != 200:
            raise PlatformError(
                self.platform_name,
                f"Get song failed: code={data.get('code')}",
            )

        songs_data = data.get("songs", [])
        if not songs_data:
            return None

        item = songs_data[0]
        duration_ms = item.get("dt", 0)
        artists = ", ".join(ar.get("name", "") for ar in item.get("ar", []))
        album_info = item.get("al", {})

        return SongInfo(
            song_id=str(item.get("id", "")),
            title=item.get("name", ""),
            artist=artists,
            album=album_info.get("name", ""),
            duration=duration_ms // 1000,
            cover_url=album_info.get("picUrl", ""),
            platform=self.platform_name,
            mv_id=str(item.get("mv", 0)) if item.get("mv") else "",
        )

    async def get_play_url(
        self, song_id: str, quality: str = "standard"
    ) -> Optional[str]:
        """Get playable URL from NetEase."""
        quality_map = {
            "low": 128000,
            "standard": 320000,
            "high": 999000,
            "lossless": 999000,
        }
        br = quality_map.get(quality, 320000)

        url = f"{self.API_URL}/song/enhance/player/url/v1"
        params = {
            "id": song_id,
            "ids": f"[{song_id}]",
            "level": "lossless" if quality == "lossless" else "exhigh",
            "encodeType": "aac",
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url, params=params, headers=self._headers())
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as e:
            raise PlatformError(self.platform_name, f"Get play URL failed: {e}")

        if data.get("code") != 200:
            return None

        songs = data.get("data", [])
        if not songs:
            return None

        song_data = songs[0]
        play_url = song_data.get("url")
        return play_url if play_url else None

    async def get_lyric(self, song_id: str) -> Optional[str]:
        """Get lyrics from NetEase."""
        url = f"{self.API_URL}/song/lyric"
        params = {"id": song_id, "lv": -1}

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url, params=params, headers=self._headers())
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as e:
            raise PlatformError(self.platform_name, f"Get lyric failed: {e}")

        if data.get("code") != 200:
            return None

        lrc = data.get("lrc", {})
        tlyric = data.get("tlyric", {})

        lyric_text = lrc.get("lyric", "")
        trans_text = tlyric.get("lyric", "")

        if trans_text:
            lyric_text += f"\n\n--- Translation ---\n{trans_text}"

        return lyric_text if lyric_text.strip() else None

    async def get_playlist(self, playlist_id: str) -> Optional[PlaylistInfo]:
        """Get playlist detail from NetEase."""
        url = f"{self.API_URL}/v6/playlist/detail"
        params = {"id": playlist_id}

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url, params=params, headers=self._headers())
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as e:
            raise PlatformError(self.platform_name, f"Get playlist failed: {e}")

        if data.get("code") != 200:
            raise PlatformError(
                self.platform_name,
                f"Get playlist failed: code={data.get('code')}",
            )

        playlist_data = data.get("playlist", {})
        tracks = playlist_data.get("tracks", [])

        songs = []
        for item in tracks:
            duration_ms = item.get("dt", 0)
            artists = ", ".join(ar.get("name", "") for ar in item.get("ar", []))
            album_info = item.get("al", {})
            song = SongInfo(
                song_id=str(item.get("id", "")),
                title=item.get("name", ""),
                artist=artists,
                album=album_info.get("name", ""),
                duration=duration_ms // 1000,
                cover_url=album_info.get("picUrl", ""),
                platform=self.platform_name,
            )
            songs.append(song)

        return PlaylistInfo(
            playlist_id=str(playlist_data.get("id", playlist_id)),
            title=playlist_data.get("name", ""),
            description=playlist_data.get("description", ""),
            cover_url=playlist_data.get("coverImgUrl", ""),
            song_count=playlist_data.get("trackCount", len(songs)),
            songs=songs,
            platform=self.platform_name,
        )

    async def get_hot_playlists(self, limit: int = 20) -> list[PlaylistInfo]:
        """Get hot playlists from NetEase."""
        url = f"{self.API_URL}/personalized"
        params = {"limit": limit}

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url, params=params, headers=self._headers())
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as e:
            raise PlatformError(self.platform_name, f"Get hot playlists failed: {e}")

        if data.get("code") != 200:
            raise PlatformError(
                self.platform_name,
                f"Get hot playlists failed: code={data.get('code')}",
            )

        playlists = []
        for item in data.get("result", []):
            playlist = PlaylistInfo(
                playlist_id=str(item.get("id", "")),
                title=item.get("name", ""),
                cover_url=item.get("picUrl", ""),
                song_count=item.get("trackCount", item.get("playCount", 0)),
                platform=self.platform_name,
            )
            playlists.append(playlist)

        return playlists
