"""Audio playback control utilities."""

import subprocess
import platform
import shutil
from dataclasses import dataclass
from typing import Optional


@dataclass
class PlaybackState:
    is_playing: bool = False
    current_song: str = ""
    current_platform: str = ""
    volume: int = 50
    position: float = 0.0
    duration: float = 0.0


class AudioPlayer:
    """Cross-platform audio player using system commands.

    Uses platform-appropriate players:
    - macOS: afplay (built-in)
    - Linux: mpg123 or ffplay
    - Windows: PowerShell media player
    """

    def __init__(self):
        self._process: Optional[subprocess.Popen] = None
        self._state = PlaybackState()
        self._player_cmd = self._detect_player()

    @staticmethod
    def _detect_player() -> Optional[str]:
        system = platform.system()

        if system == "Darwin":
            return "afplay"
        elif system == "Linux":
            for cmd in ["mpg123", "ffplay", "aplay"]:
                if shutil.which(cmd):
                    return cmd
        elif system == "Windows":
            return "powershell"

        return None

    def is_available(self) -> bool:
        return self._player_cmd is not None

    def play(self, url_or_path: str) -> bool:
        """Start playback of a URL or local file."""
        if not self._player_cmd:
            return False

        self.stop()

        filepath = url_or_path
        if filepath.startswith("file://"):
            filepath = filepath[7:]

        try:
            if self._player_cmd == "afplay":
                self._process = subprocess.Popen(
                    ["afplay", filepath],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            elif self._player_cmd == "mpg123":
                self._process = subprocess.Popen(
                    ["mpg123", "-q", filepath],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            elif self._player_cmd == "ffplay":
                self._process = subprocess.Popen(
                    ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", filepath],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            elif self._player_cmd == "powershell":
                self._process = subprocess.Popen(
                    [
                        "powershell",
                        "-c",
                        f'Add-Type -AssemblyName PresentationCore; $player = New-Object System.Windows.Media.MediaPlayer; $player.Open("{filepath}"); $player.Play(); Start-Sleep -Seconds 10',
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

            if self._process:
                self._state.is_playing = True
                return True
        except Exception:
            pass

        return False

    def stop(self) -> bool:
        """Stop current playback."""
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
            self._process = None

        self._state.is_playing = False
        return True

    def pause(self) -> bool:
        """Pause playback (send SIGSTOP on Unix)."""
        if self._process and self._state.is_playing:
            try:
                if platform.system() != "Windows":
                    self._process.send_signal(subprocess.signal.SIGSTOP)
                    self._state.is_playing = False
                    return True
            except Exception:
                pass
        return False

    def resume(self) -> bool:
        """Resume paused playback."""
        if self._process and not self._state.is_playing:
            try:
                if platform.system() != "Windows":
                    self._process.send_signal(subprocess.signal.SIGCONT)
                    self._state.is_playing = True
                    return True
            except Exception:
                pass
        return False

    def get_state(self) -> PlaybackState:
        """Get current playback state."""
        if self._process:
            poll = self._process.poll()
            if poll is not None:
                self._state.is_playing = False
        return self._state
