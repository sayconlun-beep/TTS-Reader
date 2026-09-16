"""Download the voices bundled with the Windows build into build/voices."""

import hashlib
import sys
import time
import urllib.request
from pathlib import Path

VOICES = [
    "en_GB-jenny_dioco-medium",
    "en_GB-alan-medium",
    "en_GB-northern_english_male-medium",
]
BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0"
# One model shared by every Kokoro voice, pinned by hash.
KOKORO_BASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
KOKORO = {
    "kokoro-v1.0.onnx": "7d5df8ecf7d4b1878015a32686053fd0eebe2bc377234608764cc0ef3636a6c5",
    "voices-v1.0.bin": "bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d",
}
OUT = Path(__file__).resolve().parent.parent / "build" / "voices"


def url(name, ext):
    lang, speaker, quality = name.split("-")
    return f"{BASE}/{lang.split('_')[0]}/{lang}/{speaker}/{quality}/{name}{ext}"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def fetch(src, dest, digest=None):
    tmp = dest.with_name(dest.name + ".part")
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(src, timeout=60) as resp, open(tmp, "wb") as fh:
                while chunk := resp.read(1 << 20):
                    fh.write(chunk)
            if digest and sha256(tmp) != digest:
                raise OSError("checksum mismatch")
            tmp.replace(dest)
            return
        except OSError as e:
            print(f"  attempt {attempt} failed: {e}", file=sys.stderr)
            time.sleep(3 * attempt)
    raise SystemExit(f"could not download {src}")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name in VOICES:
        for ext in (".onnx.json", ".onnx"):
            dest = OUT / f"{name}{ext}"
            if dest.exists() and dest.stat().st_size > 0:
                continue
            print(f"downloading {dest.name}")
            fetch(url(name, ext), dest)
    for name, digest in KOKORO.items():
        dest = OUT / name
        if dest.exists() and sha256(dest) == digest:
            continue
        print(f"downloading {name}")
        fetch(f"{KOKORO_BASE}/{name}", dest, digest)
    print(f"voices ready in {OUT}")


if __name__ == "__main__":
    main()
