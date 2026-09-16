# TTS Reader

Read EPUBs, PDFs, Word documents (.docx) and Markdown files aloud with [Kokoro](https://huggingface.co/hexgrad/Kokoro-82M)
or [piper](https://github.com/OHF-Voice/piper1-gpl) voices, highlighting each sentence as it is spoken. Click any sentence or chapter to read from
there; speed, voice, sleep timer and reading positions are remembered. Right-click a
paragraph (or a selection spanning several) to have it read by a different voice, for
dialogue or narration; those paragraphs get a soft tint, and the choice is saved per book.

A cross-platform Qt port of the GTK reader in the Hyprland rice, packaged for Windows
and macOS.

## Windows

Download `TTSReader-Setup-<version>.exe` from the latest release and run it. It installs
for your user only (no admin prompt) and adds TTS Reader to the Start menu and to the
"Open with" menu for EPUB, PDF, DOCX and Markdown files. It comes with 28 American and
British Kokoro voices (the more natural ones, marked "Kokoro" in the voice list) and three
British piper voices (lighter on older CPUs).

To add more piper voices, pick **Menu → Add Voices…**, drop a voice's `.onnx` and `.onnx.json`
from [rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices) into the folder
that opens, and switch back to the app.

Closing the window while it's reading keeps it going from the tray.

Settings, reading positions and `log.txt` live in `%APPDATA%\TTS Reader`.

## macOS

Apple Silicon Macs on macOS 14 or newer; onnxruntime has no Intel macOS builds.

Download `TTSReader-<version>-macOS-AppleSilicon.dmg`, open it and drag **TTS Reader**
into Applications. The app is ad-hoc signed but not notarised, so macOS blocks the first
launch: go to **System Settings → Privacy & Security**, click **Open Anyway** next to
TTS Reader, and confirm. After that it opens normally. It also appears under Finder's
**Open With** for EPUB, PDF, DOCX and Markdown files.

Voices you add go in `~/Library/Application Support/TTS Reader/voices`, and the log is
kept alongside.

## Development

```sh
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m tts_reader [book.epub]
QT_QPA_PLATFORM=offscreen TTS_READER_AUDIO=null .venv/bin/python -m unittest discover -s tests
.venv/bin/python -m tts_reader --self-test
```

On Linux, voices are also picked up from `~/.local/share/piper-tts/voices`, and Kokoro from
`kokoro-v1.0.onnx` + `voices-v1.0.bin` in `~/.local/share/kokoro-tts`
(`python packaging/fetch_voices.py` downloads both into `build/voices`).

Kokoro runs on onnxruntime and is phonemised with the espeak-ng bridge piper ships
(`tts_reader/kokoro.py`), rather than kokoro-onnx, which doesn't install on Python 3.14.
Use the full-precision model: the int8 one renders slower than real time on the CPU.

## Releases

`.github/workflows/build-windows.yml` builds on a Windows runner on every push to
`main`: unit tests, PyInstaller, a self-test of the packaged exe (offscreen window and
silent audio), then an Inno Setup installer. `.github/workflows/build-macos.yml` does the
same on an Apple Silicon runner and makes a DMG, but only for tags and manual runs,
because macOS minutes cost 10x on a private repo. Pushing a `v*` tag runs both and
publishes the installer, portable zip and DMG to one GitHub release:

```sh
git tag v0.1.0 && git push origin v0.1.0
```

The Kokoro model is Apache-2.0. piper-tts is GPL-3.0 and PyMuPDF is AGPL-3.0, so a public copy of this project needs a
compatible license.
