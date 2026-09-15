"""Where things live, on Windows and Linux alike."""

import os
import sys
from pathlib import Path

APP_NAME = "TTS Reader"
DEFAULT_VOICE = "en_GB-jenny_dioco-medium"
FROZEN = getattr(sys, "frozen", False)


def bundle_dir():
    """Read-only app files: PyInstaller's _internal folder, or the repo."""
    if FROZEN:
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def data_dir():
    """Library, settings, the log and user-added voices."""
    override = os.environ.get("TTS_READER_DATA")
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming"
        return Path(base) / APP_NAME
    base = os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share"
    # Not "tts-reader": that one belongs to the rice's GTK version.
    return Path(base) / "tts-reader-qt"


def user_voices_dir():
    return data_dir() / "voices"


def voice_dirs():
    dirs = [user_voices_dir(), bundle_dir() / "voices",
            bundle_dir() / "build" / "voices"]
    if sys.platform != "win32":
        dirs.append(Path.home() / ".local" / "share" / "piper-tts" / "voices")
    return dirs


def list_voices():
    """{voice name: model path}. The first folder holding a name wins."""
    found = {}
    for folder in voice_dirs():
        try:
            files = sorted(folder.iterdir())
        except OSError:
            continue
        for f in files:
            if f.suffix == ".onnx" and f.with_name(f.name + ".json").is_file():
                found.setdefault(f.stem, str(f))
    return dict(sorted(found.items()))
