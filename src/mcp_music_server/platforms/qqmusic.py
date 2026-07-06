"""QQ Music platform implementation."""

import json
from typing import Optional

import httpx

from .base import (
    BasePlatform,
    PlatformError,
    PlaylistInfo,
    SearchResult,
    SongInfo,
)


class QQMusicPlatform(BasePlatform):
    """QQ Music implementation using the c.y.qq.com API."""

    BASE_URL = "https://c.y.qq.com"
    U_URL = "https://u.y.qq.com"

    def __init__(self, cookie: str = ""):
        self._cookie = cookie
        self._available = True

    @property
    def platform_name(self) -> str:
        return "qqmusic"

    def is_available(self) -> bool:
        return self._available

    def _headers(self) -> dict:
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://y.qq.com/",
            "Cookie": self._cookie or "",
        }

    async def search(
        self, keyword: str, page: int = 1, limit: int = 20
    ) -> SearchResult:
        """Search songs on QQ Music."""
        url = f"{self.BASE_URL}/soso/fcgi-bin/client_search_cp"
        params = {
            "w": keyword,
            "format": "json",
            "p": page,
            "n": limit,
            "t": 0,
            "aggr": 1,
            "lossless": 1,
            "cr": 1,
            "new_json": 1,
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url, params=params, headers=self._headers())
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as e:
            raise PlatformError(self.platform_name, f"Search failed: {e}")

        if data.get("code") != 0:
            raise PlatformError(
                self.platform_name,
                f"Search failed: code={data.get('code')}",
            )

        song_list = data.get("data", {}).get("song", {}).get("list", [])
        total = data.get("data", {}).get("song", {}).get("totalnum", 0)

        songs = []
        for item in song_list:
            singers = ", ".join(s.get("name", "") for s in item.get("singer", []))
            song = SongInfo(
                song_id=str(item.get("mid", item.get("id", ""))),
                title=item.get("title", item.get("name", "")),
                artist=singers,
                album=item.get("album", {}).get("title", item.get("albumname", "")),
                duration=item.get("interval", 0),
                cover_url=f"https://y.qq.com/music/photo_new/T002R300x300M000{item.get('album', {}).get('mid', '')}.jpg",
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
        """Get song detail from QQ Music."""
        url = f"{self.U_URL}/cgi-bin/musicu.fcg"
        payload = {
            "comm": {"ct": 24, "cv": 0},
            "songinfo": {
                "method": "get_song_detail_yqq",
                "param": {"song_mid": song_id},
                "module": "music.pf_song_detail_svr",
            },
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    url, json=payload, headers=self._headers()
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as e:
            raise PlatformError(self.platform_name, f"Get song failed: {e}")

        if data.get("code") != 0:
            return None

        song_info = (
            data.get("songinfo", {})
            .get("data", {})
            .get("track_info", {})
        )
        if not song_info:
            return None

        singers = ", ".join(s.get("name", "") for s in song_info.get("singer", []))
        return SongInfo(
            song_id=song_id,
            title=song_info.get("name", song_info.get("title", "")),
            artist=singers,
            album=song_info.get("album", {}).get("name", ""),
            duration=song_info.get("interval", 0),
            cover_url=f"https://y.qq.com/music/photo_new/T002R300x300M000{song_info.get('album', {}).get('mid', '')}.jpg",
            platform=self.platform_name,
        )

    async def get_play_url(
        self, song_id: str, quality: str = "standard"
    ) -> Optional[str]:
        """Get playable URL from QQ Music."""
        quality_map = {
            "low": "M500",
            "standard": "M800",
            "high": "C400",
            "lossless": "F000",
        }
        prefix = quality_map.get(quality, "M800")

        getkey_url = f"{self.BASE_URL}/v8/fcg-bin/fcg_play_single_song.fcg"
        params = {
            "platform": "yqq.json",
            "format": "json",
            "songmid": song_id,
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    getkey_url, params=params, headers=self._headers()
                )
                resp.raise_for_status()
                key_data = resp.json()
        except httpx.HTTPError as e:
            raise PlatformError(self.platform_name, f"Get play URL failed: {e}")

        if key_data.get("code") != 0:
            return None

        urls = key_data.get("data", [])
        if not urls:
            return None

        url_item = urls[0]
        vkey = url_item.get("vkey", "")

        play_url = None
        providers = [
            f"http://isure.stream.qqmusic.qq.com/{prefix}{song_id}.mp3",
            f"http://dl.stream.qqmusic.qq.com/{prefix}{song_id}.mp3",
        ]

        for base in providers:
            if vkey:
                play_url = f"{base}?vkey={vkey}&guid=0&uin=0&fromtag=66"
                return play_url

        return None

    async def get_lyric(self, song_id: str) -> Optional[str]:
        """Get lyrics from QQ Music."""
        url = f"{self.BASE_URL}/lyric/fcgi-bin/fcg_query_lyric_new.fcg"
        params = {
            "songmid": song_id,
            "format": "json",
            "g_tk": "5381",
            "nobase64": 1,
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    url, params=params, headers={**self._headers(), "Referer": "https://y.qq.com/portal/player.html"}
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as e:
            raise PlatformError(self.platform_name, f"Get lyric failed: {e}")

        if data.get("code") != 0:
            return None

        lyric_text = data.get("lyric", "")
        trans_text = data.get("trans", "")

        if trans_text:
            lyric_text += f"\n\n--- Translation ---\n{trans_text}"

        return lyric_text if lyric_text.strip() else None

    async def get_playlist(self, playlist_id: str) -> Optional[PlaylistInfo]:
        """Get playlist detail from QQ Music."""
        url = f"{self.U_URL}/cgi-bin/musicu.fcg"
        payload = {
            "comm": {"ct": 24, "cv": 0},
            "songlist": {
                "method": "get_songlist_detail",
                "param": {"disstid": int(playlist_id), "onlysonglist": 0},
                "module": "music.musichallSong.PlayListDetailServer",
            },
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(url, json=payload, headers=self._headers())
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as e:
            raise PlatformError(self.platform_name, f"Get playlist failed: {e}")

        if data.get("code") != 0:
            return None

        pl_data = (
            data.get("songlist", {})
            .get("data", {})
            .get("songlist", {})
        )
        if not pl_data:
            return None

        tracks = pl_data.get("songlist", [])
        songs = []
        for item in tracks:
            singers = ", ".join(s.get("name", "") for s in item.get("singer", []))
            song = SongInfo(
                song_id=str(item.get("mid", item.get("songmid", ""))),
                title=item.get("title", item.get("songname", "")),
                artist=singers,
                album=item.get("album", {}).get("title", item.get("albumname", "")),
                duration=item.get("interval", 0),
                cover_url=f"https://y.qq.com/music/photo_new/T002R300x300M000{item.get('album', {}).get('mid', '')}.jpg",
                platform=self.platform_name,
            )
            songs.append(song)

        return PlaylistInfo(
            playlist_id=playlist_id,
            title=pl_data.get("title", ""),
            description=pl_data.get("desc", ""),
            cover_url=pl_data.get("dirLogo", pl_data.get("logo", "")),
            song_count=pl_data.get("total_song_num", len(songs)),
            songs=songs,
            platform=self.platform_name,
        )

    async def get_hot_playlists(self, limit: int = 20) -> list[PlaylistInfo]:
        """Get hot playlists from QQ Music."""
        url = f"{self.BASE_URL}/v8/fcg-bin/fcg_v8_toplist_opt.fcg"
        params = {
            "page": "index",
            "format": "json",
            "topid": 4,
            "cmd": 2,
            "song_begin": 0,
            "song_num": 0,
            "date": "",
            "uin": 0,
            "tpl": 1,
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url, params=params, headers=self._headers())
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as e:
            raise PlatformError(self.platform_name, f"Get hot playlists failed: {e}")

        if data.get("code") != 0:
            return []

        playlists = []
        top_list = data.get("toplist", [])
        for item in top_list[:limit]:
            playlist = PlaylistInfo(
                playlist_id=str(item.get("topID", item.get("id", ""))),
                title=item.get("ListName", item.get("topName", "")),
                cover_url=item.get("FrontPicUrl", item.get("picUrl", "")),
                platform=self.platform_name,
            )
            playlists.append(playlist)

        return playlists
