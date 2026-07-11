#!/usr/bin/env python3
"""MCP Music Server - Exposes music playback and search tools to LLM agents.

Usage:
    mcp-music-server              # Run with default settings
    MCP_PORT=8090 mcp-music-server  # Custom port
    MCP_MUSIC_DIR=/path/to/music mcp-music-server  # Custom music directory
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.server.sse import SseServerTransport
from mcp.types import Tool, TextContent

from .platforms.base import PlatformError
from .platforms.netease import NeteasePlatform
from .platforms.qqmusic import QQMusicPlatform
from .platforms.kugou import KugouPlatform
from .platforms.local import LocalPlatform
from .utils.audio import AudioPlayer
from .utils.qqmusic_auth import DEFAULT_CREDENTIAL_PATH

load_dotenv()

MUSIC_DIR = os.getenv("MCP_MUSIC_DIR", os.path.expanduser("~/Music"))
NETEASE_COOKIE = os.getenv("MCP_NETEASE_COOKIE", "")
QQMUSIC_COOKIE = os.getenv("MCP_QQMUSIC_COOKIE", "")
QQMUSIC_CREDENTIAL_PATH = os.getenv("MCP_QQMUSIC_CREDENTIAL_PATH", str(DEFAULT_CREDENTIAL_PATH))
KUGOU_COOKIE = os.getenv("MCP_KUGOU_COOKIE", "")
ENABLED_PLATFORMS = os.getenv(
    "MCP_ENABLED_PLATFORMS", "netease,qqmusic,kugou,local"
).split(",")

server = Server("mcp-music-server")
player = AudioPlayer()

_platforms: dict[str, Any] = {}


def _init_platforms():
    """Initialize enabled music platforms."""
    global _platforms
    _platforms = {}

    platform_map = {
        "netease": lambda: NeteasePlatform(cookie=NETEASE_COOKIE),
        "qqmusic": lambda: QQMusicPlatform(cookie=QQMUSIC_COOKIE, credential_path=QQMUSIC_CREDENTIAL_PATH),
        "kugou": lambda: KugouPlatform(cookie=KUGOU_COOKIE),
        "local": lambda: LocalPlatform(music_dir=MUSIC_DIR),
    }

    for name in ENABLED_PLATFORMS:
        name = name.strip()
        if name in platform_map:
            try:
                _platforms[name] = platform_map[name]()
            except Exception:
                pass


def _get_platform(name: str):
    platform = _platforms.get(name)
    if platform is None or not platform.is_available():
        raise PlatformError(name, "Platform is not available or not enabled.")
    return platform


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="music_search",
            description="Search for music across enabled platforms (netease, qqmusic, kugou, local). Returns song list with IDs, artists, albums, and durations.",
            inputSchema={
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "Search keyword (song name, artist, album, etc.)",
                    },
                    "platform": {
                        "type": "string",
                        "enum": ENABLED_PLATFORMS + ["all"],
                        "description": "Platform to search on. Use 'all' to search across all enabled platforms.",
                        "default": "all",
                    },
                    "page": {
                        "type": "integer",
                        "description": "Page number (starts at 1)",
                        "default": 1,
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Results per page (max 50)",
                        "default": 20,
                    },
                },
                "required": ["keyword"],
            },
        ),
        Tool(
            name="music_get_song",
            description="Get detailed song information including cover URL, duration, and available formats.",
            inputSchema={
                "type": "object",
                "properties": {
                    "song_id": {
                        "type": "string",
                        "description": "Song ID from search results",
                    },
                    "platform": {
                        "type": "string",
                        "description": "Platform name (netease, qqmusic, kugou, local)",
                    },
                },
                "required": ["song_id", "platform"],
            },
        ),
        Tool(
            name="music_get_play_url",
            description="Get a playable audio URL or file path for a song. Supports multiple quality levels.",
            inputSchema={
                "type": "object",
                "properties": {
                    "song_id": {
                        "type": "string",
                        "description": "Song ID from search results",
                    },
                    "platform": {
                        "type": "string",
                        "description": "Platform name",
                    },
                    "quality": {
                        "type": "string",
                        "enum": ["low", "standard", "high", "lossless"],
                        "description": "Audio quality level",
                        "default": "standard",
                    },
                },
                "required": ["song_id", "platform"],
            },
        ),
        Tool(
            name="music_get_lyrics",
            description="Get song lyrics (synced or plain text). Returns empty if unavailable.",
            inputSchema={
                "type": "object",
                "properties": {
                    "song_id": {
                        "type": "string",
                        "description": "Song ID",
                    },
                    "platform": {
                        "type": "string",
                        "description": "Platform name",
                    },
                },
                "required": ["song_id", "platform"],
            },
        ),
        Tool(
            name="music_get_playlist",
            description="Get playlist details including song list, cover image, and description.",
            inputSchema={
                "type": "object",
                "properties": {
                    "playlist_id": {
                        "type": "string",
                        "description": "Playlist ID (from platform URL or hot playlist results)",
                    },
                    "platform": {
                        "type": "string",
                        "description": "Platform name",
                    },
                },
                "required": ["playlist_id", "platform"],
            },
        ),
        Tool(
            name="music_get_hot_playlists",
            description="Get popular/hot playlists from a platform.",
            inputSchema={
                "type": "object",
                "properties": {
                    "platform": {
                        "type": "string",
                        "description": "Platform name (netease, qqmusic, kugou). Local platform returns directory playlists.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max playlists to return",
                        "default": 10,
                    },
                },
                "required": ["platform"],
            },
        ),
        Tool(
            name="music_play",
            description="Play a song. Supports local files and online URLs. For online songs, call music_get_play_url first to get the playable URL.",
            inputSchema={
                "type": "object",
                "properties": {
                    "song_id": {
                        "type": "string",
                        "description": "Song ID to play",
                    },
                    "platform": {
                        "type": "string",
                        "description": "Platform name. For local files, use 'local'.",
                    },
                    "quality": {
                        "type": "string",
                        "enum": ["low", "standard", "high", "lossless"],
                        "description": "Audio quality for online playback",
                        "default": "standard",
                    },
                },
                "required": ["song_id", "platform"],
            },
        ),
        Tool(
            name="music_stop",
            description="Stop current music playback.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="music_pause",
            description="Pause current music playback.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="music_resume",
            description="Resume paused music playback.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="music_get_playback_state",
            description="Get current playback state (playing/paused/stopped, current song info).",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="music_get_platform_status",
            description="Check which music platforms are currently available and enabled.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    try:
        result = await _handle_tool(name, arguments)
        return [TextContent(type="text", text=result)]
    except PlatformError as e:
        return [TextContent(type="text", text=json.dumps(
            {"error": str(e), "platform": e.platform}, ensure_ascii=False
        ))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps(
            {"error": str(e)}, ensure_ascii=False
        ))]


async def _handle_tool(name: str, args: dict[str, Any]) -> str:
    if name == "music_search":
        return await _search(args)
    elif name == "music_get_song":
        return await _get_song(args)
    elif name == "music_get_play_url":
        return await _get_play_url(args)
    elif name == "music_get_lyrics":
        return await _get_lyrics(args)
    elif name == "music_get_playlist":
        return await _get_playlist(args)
    elif name == "music_get_hot_playlists":
        return await _get_hot_playlists(args)
    elif name == "music_play":
        return await _play(args)
    elif name == "music_stop":
        return _stop()
    elif name == "music_pause":
        return _pause()
    elif name == "music_resume":
        return _resume()
    elif name == "music_get_playback_state":
        return _get_playback_state()
    elif name == "music_get_platform_status":
        return _platform_status()
    else:
        return json.dumps({"error": f"Unknown tool: {name}"})


async def _search(args: dict) -> str:
    keyword = args["keyword"]
    platform_name = args.get("platform", "all")
    page = max(1, int(args.get("page", 1)))
    limit = min(50, max(1, int(args.get("limit", 20))))

    if platform_name == "all":
        results = {}
        for pname, platform in _platforms.items():
            if not platform.is_available():
                continue
            try:
                result = await platform.search(keyword, page=page, limit=limit)
                results[pname] = result.to_dict()
            except PlatformError as e:
                results[pname] = {"error": str(e)}

        return json.dumps({"keyword": keyword, "platforms": results}, ensure_ascii=False)

    platform = _get_platform(platform_name)
    result = await platform.search(keyword, page=page, limit=limit)
    return json.dumps(result.to_dict(), ensure_ascii=False)


async def _get_song(args: dict) -> str:
    platform = _get_platform(args["platform"])
    song = await platform.get_song(args["song_id"])
    if song is None:
        return json.dumps({"error": "Song not found"}, ensure_ascii=False)
    return json.dumps(song.to_dict(), ensure_ascii=False)


async def _get_play_url(args: dict) -> str:
    platform = _get_platform(args["platform"])
    quality = args.get("quality", "standard")
    url = await platform.get_play_url(args["song_id"], quality=quality)
    if url is None:
        return json.dumps({"error": "Play URL not available. The song may be region-restricted or require VIP."}, ensure_ascii=False)
    return json.dumps({"play_url": url, "quality": quality}, ensure_ascii=False)


async def _get_lyrics(args: dict) -> str:
    platform = _get_platform(args["platform"])
    lyric = await platform.get_lyric(args["song_id"])
    if lyric is None:
        return json.dumps({"lyric": "", "message": "No lyrics available."}, ensure_ascii=False)
    return json.dumps({"lyric": lyric}, ensure_ascii=False)


async def _get_playlist(args: dict) -> str:
    platform = _get_platform(args["platform"])
    playlist = await platform.get_playlist(args["playlist_id"])
    if playlist is None:
        return json.dumps({"error": "Playlist not found"}, ensure_ascii=False)
    return json.dumps(playlist.to_dict(), ensure_ascii=False)


async def _get_hot_playlists(args: dict) -> str:
    platform = _get_platform(args["platform"])
    limit = min(30, max(1, int(args.get("limit", 10))))
    playlists = await platform.get_hot_playlists(limit=limit)
    return json.dumps(
        {"platform": args["platform"], "count": len(playlists), "playlists": [p.to_dict() for p in playlists]},
        ensure_ascii=False,
    )


async def _play(args: dict) -> str:
    platform = _get_platform(args["platform"])
    song_id = args["song_id"]
    quality = args.get("quality", "standard")

    song = await platform.get_song(song_id)
    if song is None:
        return json.dumps({"error": "Song not found"}, ensure_ascii=False)

    play_url = song.play_url
    if not play_url or play_url.startswith("file://"):
        play_url = await platform.get_play_url(song_id, quality=quality)

    if not play_url:
        return json.dumps({"error": "No playable URL available"}, ensure_ascii=False)

    if not player.is_available():
        return json.dumps(
            {
                "play_url": play_url,
                "song": song.to_dict(),
                "warning": "No audio player available on this system. Use the play_url to play externally.",
            },
            ensure_ascii=False,
        )

    success = player.play(play_url)
    if success:
        return json.dumps(
            {"status": "playing", "song": song.to_dict(), "play_url": play_url},
            ensure_ascii=False,
        )
    else:
        return json.dumps(
            {"play_url": play_url, "song": song.to_dict(), "warning": "Playback failed. Use the URL to play externally."},
            ensure_ascii=False,
        )


def _stop() -> str:
    player.stop()
    return json.dumps({"status": "stopped"})


def _pause() -> str:
    if player.pause():
        return json.dumps({"status": "paused"})
    return json.dumps({"status": "pause not supported on this system"})


def _resume() -> str:
    if player.resume():
        return json.dumps({"status": "playing"})
    return json.dumps({"status": "resume not supported on this system"})


def _get_playback_state() -> str:
    state = player.get_state()
    return json.dumps(
        {
            "is_playing": state.is_playing,
            "current_song": state.current_song,
            "current_platform": state.current_platform,
            "volume": state.volume,
        }
    )


def _platform_status() -> str:
    status = {}
    for pname, platform in _platforms.items():
        status[pname] = {
            "enabled": True,
            "available": platform.is_available(),
            "name": platform.platform_name,
        }

    status["audio_player"] = {
        "available": player.is_available(),
    }

    status["music_directory"] = MUSIC_DIR

    return json.dumps(status, ensure_ascii=False)


async def main():
    """Run the MCP Music Server. Supports stdio and SSE transports."""
    _init_platforms()

    available = ", ".join(
        [p.platform_name for p in _platforms.values() if p.is_available()]
    )
    if not available:
        print(f"[mcp-music-server] No platforms available. Check configuration.", file=sys.stderr)
    else:
        print(f"[mcp-music-server] Platforms: {available}", file=sys.stderr)

    transport = os.getenv("MCP_TRANSPORT", "stdio")

    if transport == "sse":
        await _run_sse()
    else:
        await _run_stdio()


async def _run_stdio():
    """Run server via stdio transport (for local MCP clients)."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream, server.create_initialization_options()
        )


async def _run_sse():
    """Run server via SSE/HTTP transport (for remote MCP clients)."""
    try:
        from starlette.applications import Starlette
        from starlette.responses import Response
        from starlette.routing import Mount, Route
        import uvicorn
    except ImportError:
        print(
            "[mcp-music-server] SSE transport requires starlette and uvicorn. "
            "Install with: pip install mcp-music-server[sse]",
            file=sys.stderr,
        )
        sys.exit(1)

    host = os.getenv("MCP_HOST", "0.0.0.0")
    port = int(os.getenv("MCP_PORT", "8090"))

    transport_instance = SseServerTransport("/messages/")

    async def handle_sse(request):
        async with transport_instance.connect_sse(
            request.scope, request.receive, request._send
        ) as (read_stream, write_stream):
            await server.run(
                read_stream, write_stream, server.create_initialization_options()
            )
        return Response()

    app = Starlette(
        routes=[
            Route("/sse", endpoint=handle_sse, methods=["GET"]),
            Mount("/messages/", app=transport_instance.handle_post_message),
        ]
    )

    print(
        f"[mcp-music-server] SSE server starting on http://{host}:{port}",
        file=sys.stderr,
    )
    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server_instance = uvicorn.Server(config)
    await server_instance.serve()


if __name__ == "__main__":
    asyncio.run(main())
