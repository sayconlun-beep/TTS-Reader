"""Download the voices bundled with the Windows build into build/voices."""

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
OUT = Path(__file__).resolve().parent.parent / "build" / "voices"


def url(name, ext):
    lang, speaker, quality = name.split("-")
    return f"{BASE}/{lang.split('_')[0]}/{lang}/{speaker}/{quality}/{name}{ext}"


def fetch(src, dest):
    tmp = dest.with_name(dest.name + ".part")
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(src, timeout=60) as resp, open(tmp, "wb") as fh:
                while chunk := resp.read(1 << 20):
                    fh.write(chunk)
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
    print(f"voices ready in {OUT}")


if __name__ == "__main__":
    main()
