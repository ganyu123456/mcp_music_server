"""Kugou Music platform implementation."""

from typing import Optional

import httpx

from .base import (
    BasePlatform,
    PlatformError,
    PlaylistInfo,
    SearchResult,
    SongInfo,
)


class KugouPlatform(BasePlatform):
    """Kugou Music implementation."""

    SEARCH_URL = "http://mobilecdn.kugou.com/api/v3/search/song"
    SONG_URL = "http://m.kugou.com/app/i/getSongInfo.php"
    LYRIC_URL = "http://m.kugou.com/app/i/krc.php"
    PLAY_URL = "http://www.kugou.com/yy/index.php"
    PLAYLIST_URL = "http://mobilecdn.kugou.com/api/v3/special/info"
    RANK_URL = "http://mobilecdn.kugou.com/api/v3/rank/song"

    def __init__(self, cookie: str = ""):
        self._cookie = cookie
        self._available = True

    @property
    def platform_name(self) -> str:
        return "kugou"

    def is_available(self) -> bool:
        return self._available

    def _headers(self) -> dict:
        return {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 13_2_3 like Mac OS X) AppleWebKit/605.1.15",
            "Cookie": self._cookie or "",
        }

    async def search(
        self, keyword: str, page: int = 1, limit: int = 20
    ) -> SearchResult:
        """Search songs on Kugou."""
        params = {
            "keyword": keyword,
            "page": page,
            "pagesize": limit,
            "format": "json",
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    self.SEARCH_URL, params=params, headers=self._headers()
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as e:
            raise PlatformError(self.platform_name, f"Search failed: {e}")

        if data.get("status") != 1:
            error_msg = data.get("error", "unknown error")
            raise PlatformError(self.platform_name, f"Search failed: {error_msg}")

        info_list = data.get("data", {}).get("info", [])
        total = data.get("data", {}).get("total", 0)

        songs = []
        for item in info_list:
            song = SongInfo(
                song_id=item.get("hash", ""),
                title=item.get("songname", item.get("filename", "")),
                artist=item.get("singername", ""),
                album=item.get("album_name", ""),
                duration=item.get("duration", 0),
                cover_url=item.get("imgUrl", ""),
                platform=self.platform_name,
            )
            songs.append(song)

        return SearchResult(
            keyword=keyword,
            total=total,
            songs=songs,
            platform=self.platform_name,
        )

    async def get_song(self, song_id: str) -> Optional[SongInfo]:
        """Get song detail from Kugou."""
        params = {
            "cmd": "playInfo",
            "hash": song_id,
            "format": "json",
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    self.SONG_URL, params=params, headers=self._headers()
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as e:
            raise PlatformError(self.platform_name, f"Get song failed: {e}")

        if data.get("status") != 1:
            return None

        song_data = data.get("data", {})
        if not song_data:
            return None

        return SongInfo(
            song_id=song_id,
            title=song_data.get("songName", song_data.get("songname", "")),
            artist=song_data.get("author_name", song_data.get("singerName", "")),
            album=song_data.get("album_name", song_data.get("albumName", "")),
            duration=song_data.get("timelength", 0),
            cover_url=song_data.get("imgUrl", ""),
            platform=self.platform_name,
        )

    async def get_play_url(
        self, song_id: str, quality: str = "standard"
    ) -> Optional[str]:
        """Get playable URL from Kugou."""
        params = {
            "cmd": "playInfo",
            "hash": song_id,
            "format": "json",
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    self.SONG_URL, params=params, headers=self._headers()
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as e:
            raise PlatformError(self.platform_name, f"Get play URL failed: {e}")

        if data.get("status") != 1:
            return None

        song_data = data.get("data", {})
        play_url = song_data.get("url") or song_data.get("playUrl", "")
        return play_url if play_url else None

    async def get_lyric(self, song_id: str) -> Optional[str]:
        """Get lyrics from Kugou."""
        params = {
            "cmd": "100",
            "hash": song_id,
            "timelength": 0,
            "format": "json",
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    "http://lyrics.kugou.com/search", params=params, headers=self._headers()
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as e:
            raise PlatformError(self.platform_name, f"Get lyric failed: {e}")

        if data.get("status") != 200:
            return None

        candidates = data.get("candidates", [])
        if not candidates:
            return None

        lyric_id = candidates[0].get("id", "")
        lyric_key = candidates[0].get("accesskey", "")

        if not lyric_id:
            return None

        lyric_params = {
            "id": lyric_id,
            "accesskey": lyric_key,
            "fmt": "krc",
            "charset": "utf8",
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    "http://lyrics.kugou.com/download",
                    params=lyric_params,
                    headers=self._headers(),
                )
                resp.raise_for_status()
                lyric_data = resp.json()
        except httpx.HTTPError:
            return None

        content = lyric_data.get("content", "")
        return content if content.strip() else None

    async def get_playlist(self, playlist_id: str) -> Optional[PlaylistInfo]:
        """Get playlist detail from Kugou."""
        params = {
            "specialid": playlist_id,
            "format": "json",
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    self.PLAYLIST_URL, params=params, headers=self._headers()
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as e:
            raise PlatformError(self.platform_name, f"Get playlist failed: {e}")

        if data.get("status") != 1:
            return None

        pl_data = data.get("data", {})
        tracks = pl_data.get("list", [])
        songs = []
        for item in tracks:
            song = SongInfo(
                song_id=item.get("hash", ""),
                title=item.get("filename", item.get("songname", "")),
                artist=item.get("singername", ""),
                duration=item.get("duration", 0),
                cover_url=item.get("imgUrl", ""),
                platform=self.platform_name,
            )
            songs.append(song)

        return PlaylistInfo(
            playlist_id=playlist_id,
            title=pl_data.get("specialname", ""),
            description=pl_data.get("intro", ""),
            cover_url=pl_data.get("img", pl_data.get("imgurl", "")),
            song_count=pl_data.get("songcount", len(songs)),
            songs=songs,
            platform=self.platform_name,
        )

    async def get_hot_playlists(self, limit: int = 20) -> list[PlaylistInfo]:
        """Get rank lists from Kugou."""
        params = {
            "rankid": 8888,
            "page": 1,
            "pagesize": limit,
            "with_res_tag": 1,
            "format": "json",
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    self.RANK_URL, params=params, headers=self._headers()
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as e:
            raise PlatformError(self.platform_name, f"Get hot playlists failed: {e}")

        if data.get("status") != 1:
            return []

        info = data.get("data", {}).get("info", {})
        songs_data = data.get("data", {}).get("songs", {}).get("list", [])

        songs = []
        for item in songs_data:
            song = SongInfo(
                song_id=item.get("hash", ""),
                title=item.get("filename", ""),
                artist=item.get("singername", ""),
                duration=item.get("duration", 0),
                cover_url=item.get("imgUrl", ""),
                platform=self.platform_name,
            )
            songs.append(song)

        playlist = PlaylistInfo(
            playlist_id="8888",
            title=info.get("rankname", "Hot Songs"),
            description=info.get("intro", ""),
            cover_url=info.get("banner7url", info.get("imgurl", "")),
            song_count=len(songs),
            songs=songs,
            platform=self.platform_name,
        )

        return [playlist] if songs else []
