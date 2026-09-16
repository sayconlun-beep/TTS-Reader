"""Where things live, on Windows, macOS and Linux alike."""

import os
import sys
import zipfile
from pathlib import Path

APP_NAME = "TTS Reader"
DEFAULT_VOICE = "kokoro:bm_fable"
PIPER_DEFAULT_VOICE = "en_GB-jenny_dioco-medium"    # when Kokoro isn't there
KOKORO_PREFIX = "kokoro:"
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
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    base = os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share"
    # Not "tts-reader": that one belongs to the rice's GTK version.
    return Path(base) / "tts-reader-qt"


def user_voices_dir():
    return data_dir() / "voices"


def voice_dirs():
    dirs = [user_voices_dir(), bundle_dir() / "voices",
            bundle_dir() / "build" / "voices"]
    if sys.platform != "win32":
        share = Path.home() / ".local" / "share"
        # The rice's piper voices and its kokoro-tts model.
        dirs += [share / "piper-tts" / "voices", share / "kokoro-tts"]
    return dirs


def is_kokoro(voice):
    return voice.startswith(KOKORO_PREFIX)


def default_voice(voices):
    """Fable if Kokoro is installed, else Jenny, else whatever there is."""
    for name in (DEFAULT_VOICE, PIPER_DEFAULT_VOICE):
        if name in voices:
            return name
    return next(iter(voices), None)


def list_voices():
    """{voice name: model path}. The first folder holding a name wins.

    Piper voices are named after their .onnx file. Kokoro voices all share
    one model, so they are "kokoro:<voice>" and map to that model's path.
    """
    from .kokoro import KOKORO_MODEL, KOKORO_VOICES, kokoro_voice_names

    found, kokoro = {}, None
    for folder in voice_dirs():
        try:
            files = sorted(folder.iterdir())
        except OSError:
            continue
        for f in files:
            if f.name == KOKORO_MODEL:
                if kokoro is None and f.with_name(KOKORO_VOICES).is_file():
                    kokoro = f
            elif f.suffix == ".onnx" and f.with_name(f.name + ".json").is_file():
                found.setdefault(f.stem, str(f))
    if kokoro is not None:
        try:
            for name in kokoro_voice_names(kokoro.with_name(KOKORO_VOICES)):
                found[KOKORO_PREFIX + name] = str(kokoro)
        except (OSError, zipfile.BadZipFile):
            pass
    return dict(sorted(found.items()))
