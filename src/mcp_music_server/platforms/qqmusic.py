"""QQ Music platform implementation."""

import json
import logging
import uuid
from typing import Optional

import httpx

from .base import (
    BasePlatform,
    PlatformError,
    PlaylistInfo,
    SearchResult,
    SongInfo,
)
from ..utils.qqmusic_auth import QQMusicAuth

logger = logging.getLogger(__name__)


class QQMusicPlatform(BasePlatform):
    """QQ Music implementation using the c.y.qq.com API."""

    BASE_URL = "https://c.y.qq.com"
    U_URL = "https://u.y.qq.com"

    def __init__(self, cookie: str = "", credential_path: str = ""):
        self._cookie = cookie
        self._available = True
        self._auth: QQMusicAuth | None = None
        if credential_path:
            self._auth = QQMusicAuth(credential_path)
            self._auth.load()

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

    def _parse_cookie(self, key: str) -> str:
        """Extract a value from the cookie string by key."""
        for part in (self._cookie or "").split("; "):
            if part.startswith(f"{key}="):
                return part[len(key) + 1 :]
        return ""

    async def _ensure_cookies(self):
        """Refresh cookie from credential manager if available."""
        if self._auth and self._auth.is_loaded:
            try:
                if await self._auth.ensure_valid():
                    cookie_dict = self._auth.get_cookies()
                    self._cookie = "; ".join(f"{k}={v}" for k, v in cookie_dict.items() if v)
            except Exception:
                logger.debug("Failed to refresh QQ Music credential, using existing cookie")

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
        await self._ensure_cookies()
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
        """Get playable URL from QQ Music.

        Uses the modern vkey-based API: music.vkey.GetVkey / UrlGetVkey.
        Reference: https://github.com/L-1124/QQMusicApi
        """
        await self._ensure_cookies()
        quality_map = {
            "low": ("M500", ".mp3"),
            "standard": ("M500", ".mp3"),
            "high": ("M800", ".mp3"),
            "lossless": ("F000", ".flac"),
        }
        prefix, suffix = quality_map.get(quality, ("M800", ".mp3"))

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                # Step 1: Get media_mid from song detail
                song_url = f"{self.BASE_URL}/v8/fcg-bin/fcg_play_single_song.fcg"
                resp = await client.get(
                    song_url,
                    params={"platform": "yqq.json", "format": "json", "songmid": song_id},
                    headers=self._headers(),
                )
                resp.raise_for_status()
                song_data = resp.json()

                if song_data.get("code") != 0 or not song_data.get("data"):
                    return None

                item = song_data["data"][0]
                media_mid = item.get("file", {}).get("media_mid", "")
                if not media_mid:
                    return None

                # Step 2: Request vkey/purl via UrlGetVkey
                guid = uuid.uuid4().hex
                filename = f"{prefix}{media_mid}{suffix}"
                uin = self._parse_cookie("uin") or "0"

                payload = {
                    "req_0": {
                        "module": "music.vkey.GetVkey",
                        "method": "UrlGetVkey",
                        "param": {
                            "uin": uin,
                            "filename": [filename],
                            "guid": guid,
                            "songmid": [song_id],
                            "songtype": [0],
                            "ctx": 0,
                        },
                    }
                }

                resp2 = await client.post(
                    f"{self.U_URL}/cgi-bin/musicu.fcg",
                    json=payload,
                    headers={**self._headers(), "Content-Type": "application/json"},
                )
                resp2.raise_for_status()
                vkey_data = resp2.json()

                # Step 3: Extract purl and construct full URL
                midurlinfo = (
                    vkey_data.get("req_0", {}).get("data", {}).get("midurlinfo", [])
                )
                if not midurlinfo:
                    return None

                info = midurlinfo[0]
                if info.get("result", -1) != 0:
                    return None

                purl = info.get("purl", "")
                if not purl:
                    return None

                sip_list = vkey_data.get("req_0", {}).get("data", {}).get("sip", [])
                cdn = sip_list[0] if sip_list else "http://aqqmusic.tc.qq.com/"

                return f"{cdn}{purl}"

        except httpx.HTTPError as e:
            raise PlatformError(self.platform_name, f"Get play URL failed: {e}")

    async def get_lyric(self, song_id: str) -> Optional[str]:
        """Get lyrics from QQ Music."""
        await self._ensure_cookies()
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
        """Get playlist detail from QQ Music. Supports both user playlists (dissid) and official charts (topID)."""
        await self._ensure_cookies()
        # First try user playlist API (dissid)
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                resp = await client.get(
                    f"{self.BASE_URL}/v8/fcg-bin/fcg_v8_playlist_cp.fcg",
                    params={"id": playlist_id, "format": "json"},
                    headers=self._headers(),
                )
                resp.raise_for_status()
                data = resp.json()
            except httpx.HTTPError:
                data = {}

            if data.get("code") == 0:
                cdlist = data.get("data", {}).get("cdlist", [])
                if cdlist:
                    return self._parse_playlist_response(playlist_id, cdlist[0])

            # Fallback to official chart API (topID)
            try:
                resp = await client.get(
                    f"{self.BASE_URL}/v8/fcg-bin/fcg_v8_toplist_opt.fcg",
                    params={
                        "page": "index", "format": "json", "topid": playlist_id,
                        "cmd": 2, "song_begin": 0, "song_num": 0,
                        "date": "", "uin": 0, "tpl": 1,
                    },
                    headers=self._headers(),
                )
                resp.raise_for_status()
                data = resp.json()
            except httpx.HTTPError:
                return None

            topinfo = data.get("topinfo", {})
            if not topinfo:
                return None

            songs = []
            for item in data.get("songlist", []):
                song_data = item.get("data", item)
                singers = ", ".join(s.get("name", "") for s in song_data.get("singer", []))
                songs.append(SongInfo(
                    song_id=str(song_data.get("mid", song_data.get("songmid", ""))),
                    title=song_data.get("title", song_data.get("songname", "")),
                    artist=singers,
                    album=song_data.get("albumname", song_data.get("album", {}).get("title", "")),
                    duration=song_data.get("interval", 0),
                    cover_url=f"https://y.qq.com/music/photo_new/T002R300x300M000{song_data.get('albummid', song_data.get('album', {}).get('mid', ''))}.jpg",
                    platform=self.platform_name,
                ))

            return PlaylistInfo(
                playlist_id=playlist_id,
                title=topinfo.get("ListName", ""),
                description=topinfo.get("info", ""),
                cover_url=topinfo.get("MacDetailPicUrl", topinfo.get("picUrl", "")),
                song_count=len(songs),
                songs=songs,
                platform=self.platform_name,
            )

    def _parse_playlist_response(self, playlist_id: str, pl_data: dict) -> PlaylistInfo:
        tracks = pl_data.get("songlist", [])
        songs = []
        for item in tracks:
            singers = ", ".join(s.get("name", "") for s in item.get("singer", []))
            song = SongInfo(
                song_id=str(item.get("songmid", item.get("mid", ""))),
                title=item.get("songname", item.get("title", "")),
                artist=singers,
                album=item.get("albumname", item.get("album", {}).get("title", "")),
                duration=item.get("interval", 0),
                cover_url=f"https://y.qq.com/music/photo_new/T002R300x300M000{item.get('albummid', item.get('album', {}).get('mid', ''))}.jpg",
                platform=self.platform_name,
            )
            songs.append(song)

        return PlaylistInfo(
            playlist_id=playlist_id,
            title=pl_data.get("dissname", ""),
            description=pl_data.get("desc", ""),
            cover_url=pl_data.get("logo", ""),
            song_count=pl_data.get("songnum", len(songs)),
            songs=songs,
            platform=self.platform_name,
        )

    async def get_hot_playlists(self, limit: int = 20) -> list[PlaylistInfo]:
        """Get hot playlists from QQ Music."""
        top_ids = [4, 26, 27, 5, 6, 3, 16, 17, 28, 18, 19, 20, 21, 22, 23]
        playlists = []

        async with httpx.AsyncClient(timeout=15.0) as client:
            for top_id in top_ids[:limit]:
                url = f"{self.BASE_URL}/v8/fcg-bin/fcg_v8_toplist_opt.fcg"
                params = {
                    "page": "index",
                    "format": "json",
                    "topid": top_id,
                    "cmd": 2,
                    "song_begin": 0,
                    "song_num": 0,
                    "date": "",
                    "uin": 0,
                    "tpl": 1,
                }
                try:
                    resp = await client.get(url, params=params, headers=self._headers())
                    resp.raise_for_status()
                    data = resp.json()
                except httpx.HTTPError:
                    continue

                if data.get("code", 0) != 0:
                    continue

                topinfo = data.get("topinfo", {})
                if not topinfo:
                    continue

                playlist = PlaylistInfo(
                    playlist_id=str(topinfo.get("topID", top_id)),
                    title=topinfo.get("ListName", ""),
                    cover_url=topinfo.get("MacDetailPicUrl", topinfo.get("picUrl", "")),
                    platform=self.platform_name,
                )
                playlists.append(playlist)

        return playlists
