"""Kokoro-82M voices: onnxruntime plus the espeak-ng bridge piper ships.

kokoro-onnx does the same job, but it pins Python below 3.14 and pulls in
phonemizer's dependency tree; this needs nothing piper doesn't already bring.
Only the English voices are offered: `a...` are American, `b...` British.
"""

# -- Kokoro: identical in tts_reader/kokoro.py and the rice's kokoro-tts ----
import re
import zipfile

import numpy as np

KOKORO_MODEL = "kokoro-v1.0.onnx"
KOKORO_VOICES = "voices-v1.0.bin"
KOKORO_RATE = 24000
KOKORO_LANGS = {"a": "en-us", "b": "en"}       # voice prefix -> espeak voice
KOKORO_MAX = 510                               # phonemes per model call
KOKORO_VOCAB = dict(zip(
    ';:,.!?—…"()“” ̃ʣʥʦʨᵝꭧAIOQSTWYᵊabcdefhijklmnopqrstuvwxyzɑɐɒæβɔɕçɖðʤəɚɛɜɟɡɥɨɪʝɯɰŋɳɲɴøɸθœɹɾɻʁɽʂʃʈʧʊʋʌɣɤχʎʒʔˈˌːʰʲ↓→↗↘ᵻ',
    [1, 2, 3, 4, 5, 6, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22,
     23, 24, 25, 31, 33, 35, 36, 39, 41, 42, 43, 44, 45, 46, 47, 48, 50, 51,
     52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69,
     70, 71, 72, 75, 76, 77, 78, 80, 81, 82, 83, 85, 86, 87, 90, 92, 99, 101,
     102, 103, 110, 111, 112, 113, 114, 115, 116, 118, 119, 120, 123, 125,
     126, 128, 129, 130, 131, 132, 133, 135, 136, 138, 139, 140, 142, 143,
     147, 148, 156, 157, 158, 162, 164, 169, 171, 172, 173, 177]))


def kokoro_voice_names(voices_path):
    """The English voices in a voices-v1.0.bin (an .npz archive)."""
    with zipfile.ZipFile(voices_path) as z:
        return sorted(n[:-4] for n in z.namelist()
                      if n.endswith(".npy") and n[:1] in KOKORO_LANGS)


def _trim(audio, top_db=60, frame=2048, hop=512):
    """Cut leading and trailing silence, like librosa.effects.trim."""
    if len(audio) < frame:
        return audio
    padded = np.pad(audio, frame // 2)
    frames = np.lib.stride_tricks.sliding_window_view(padded, frame)[::hop]
    power = np.maximum(np.mean(frames.astype(np.float64) ** 2, axis=1), 1e-10)
    db = 10 * np.log10(power)
    loud = np.flatnonzero(db > db.max() - top_db)
    if loud.size == 0:
        return audio[:0]
    return audio[loud[0] * hop:min(len(audio), (loud[-1] + 1) * hop)]


class Kokoro:
    """One loaded model; every voice shares it, so switching voices is free."""

    def __init__(self, model_path, voices_path, espeak_data):
        import onnxruntime
        from piper import espeakbridge
        from piper import voice as piper_voice
        from piper.phonemize_espeak import EspeakPhonemizer

        # espeak-ng is process-wide, and initialising it again after piper
        # has corrupts its phoneme tables: share piper's one setup and lock.
        self.bridge = espeakbridge
        self.espeak_lock = piper_voice._ESPEAK_PHONEMIZER_LOCK
        with self.espeak_lock:
            if piper_voice._ESPEAK_PHONEMIZER is None:
                piper_voice._ESPEAK_PHONEMIZER = EspeakPhonemizer(espeak_data)
        self.session = onnxruntime.InferenceSession(
            str(model_path), providers=["CPUExecutionProvider"])
        self.archive = np.load(voices_path)
        self.styles = {}
        self.names = kokoro_voice_names(voices_path)

    def _chunks(self, text, lang):
        """Phonemes in pieces the model accepts, split between clauses."""
        with self.espeak_lock:
            self.bridge.set_voice(lang)
            clauses = self.bridge.get_phonemes(text)
        chunks, current = [], ""
        for phonemes, terminator, _end in clauses:
            # Drop espeak's (lang) switch flags and its palatalisation marks,
            # which Kokoro never saw in training.
            clause = re.sub(r"\([^)]+\)", "", phonemes).replace("ʲ", "")
            clause = "".join(c for c in clause + terminator if c in KOKORO_VOCAB)
            clause = clause.strip()
            while len(clause) > KOKORO_MAX:
                cut = clause.rfind(" ", 0, KOKORO_MAX)
                cut = cut if cut > 0 else KOKORO_MAX
                chunks.append(clause[:cut].strip())
                clause = clause[cut:].strip()
            if not clause:
                continue
            if current and len(current) + 1 + len(clause) > KOKORO_MAX:
                chunks.append(current)
                current = clause
            else:
                current = f"{current} {clause}" if current else clause
        if current:
            chunks.append(current)
        return [c for c in chunks if c]

    def synthesize(self, text, voice, speed=1.0):
        """float32 samples at KOKORO_RATE with the edges' silence trimmed."""
        if voice not in self.styles:            # NpzFile re-reads on every access
            self.styles[voice] = self.archive[voice]
        style = self.styles[voice]
        parts = []
        for chunk in self._chunks(text, KOKORO_LANGS[voice[0]]):
            ids = [KOKORO_VOCAB[c] for c in chunk]
            audio = self.session.run(None, {
                "tokens": np.array([[0, *ids, 0]], np.int64),
                "style": style[len(ids)],
                "speed": np.array([speed], np.float32),
            })[0]
            parts.append(_trim(np.asarray(audio, np.float32).reshape(-1)))
        return np.concatenate(parts) if parts else np.zeros(0, np.float32)
# -- end Kokoro --------------------------------------------------------------
