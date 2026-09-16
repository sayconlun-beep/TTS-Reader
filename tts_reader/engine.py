"""Playback: piper or Kokoro renders a window of sentences around the playhead
and one PortAudio stream plays them back to back.

Same shape as the GTK version, minus mpv: the voice runs in-process, speed is
the model's own (piper's length_scale, Kokoro's speed input - natural pitch,
no time-stretching), and the audio callback pulls sentences straight off a
queue.

Every jump bumps `gen`. Audio rendered for an older generation is dropped
before it reaches the queue, so a sentence that was mid-render when you
clicked elsewhere can never slip into the new one.
"""

import collections
import json
import os
import threading
import time

import numpy as np
from PySide6.QtCore import QObject, QTimer, Signal

from . import kokoro, paths

AHEAD = 12          # sentences rendered ahead of the playhead
MODELS_KEPT = 3     # voices kept loaded, since paragraph voices alternate
KEEP_BEHIND = 20    # sentences kept behind it, so stepping back is instant
GAP = 0.2           # seconds of silence after each sentence, like piper's CLI


def voice_rate(voice, model_path):
    if paths.is_kokoro(voice):
        return kokoro.KOKORO_RATE
    with open(f"{model_path}.json", encoding="utf-8") as fh:
        return int(json.load(fh)["audio"]["sample_rate"])


class PiperBackend:
    def __init__(self, model_path):
        from piper import PiperVoice
        self.voice = PiperVoice.load(model_path)
        self.sample_rate = self.voice.config.sample_rate

    def render(self, text, speed):
        from piper import SynthesisConfig
        config = SynthesisConfig(length_scale=self.voice.config.length_scale / speed)
        return [c.audio_int16_array
                for c in self.voice.synthesize(text, syn_config=config)]


def resample(samples, src, dst):
    """int16 at src Hz -> int16 at dst Hz. Linear, which is plenty for speech
    moving between piper's 22.05 kHz and Kokoro's 24 kHz."""
    if src == dst or not len(samples):
        return samples
    n = max(1, round(len(samples) * dst / src))
    x = np.linspace(0, len(samples) - 1, n)
    return np.interp(x, np.arange(len(samples)), samples).astype(np.int16)


class KokoroBackend:
    sample_rate = kokoro.KOKORO_RATE

    def __init__(self, model, name):
        self.model, self.name = model, name

    def render(self, text, speed):
        audio = self.model.synthesize(text, self.name, speed)
        return [(np.clip(audio, -1, 1) * 32767).astype(np.int16)]


class Models:
    """Loaded voices, most recent last. Kokoro voices share one model. Hold
    `lock` while rendering: a model isn't safe to use from two threads."""

    def __init__(self):
        self.loaded = collections.OrderedDict()     # voice -> backend
        self.lock = threading.Lock()
        self.kokoro = None              # (model path, Kokoro), kept across voices

    def get(self, voice):
        with self.lock:
            model = self.loaded.pop(voice, None)
            if model is None:
                path = paths.list_voices().get(voice)
                if not path:
                    raise FileNotFoundError(f"no voice named {voice}")
                if paths.is_kokoro(voice):
                    if self.kokoro is None or self.kokoro[0] != path:
                        from piper.phonemize_espeak import ESPEAK_DATA_DIR
                        voices = os.path.join(os.path.dirname(path),
                                              kokoro.KOKORO_VOICES)
                        self.kokoro = (path, kokoro.Kokoro(path, voices,
                                                           ESPEAK_DATA_DIR))
                    model = KokoroBackend(
                        self.kokoro[1], voice[len(paths.KOKORO_PREFIX):])
                else:
                    model = PiperBackend(path)
                while len(self.loaded) >= MODELS_KEPT:
                    self.loaded.popitem(last=False)
            self.loaded[voice] = model
            return model


class SoundOutput:
    def __init__(self, rate, fill):
        import sounddevice as sd

        def callback(outdata, _frames, _time, _status):
            fill(outdata[:, 0])

        self.stream = sd.OutputStream(samplerate=rate, channels=1,
                                      dtype="int16", callback=callback)
        self.stream.start()

    def close(self):
        try:
            self.stream.abort()
            self.stream.close()
        except Exception:
            pass


class NullOutput:
    """Plays in real time into nothing - for tests and machines without sound."""

    BLOCK = 0.02

    def __init__(self, rate, fill):
        self.rate, self.fill = rate, fill
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        buf = np.zeros(int(self.rate * self.BLOCK), np.int16)
        while self.running:
            self.fill(buf)
            time.sleep(self.BLOCK)

    def close(self):
        self.running = False
        self.thread.join(timeout=1)


def make_output(rate, fill):
    if os.environ.get("TTS_READER_AUDIO") == "null":
        return NullOutput(rate, fill)
    return SoundOutput(rate, fill)


class Player(QObject):
    position = Signal(int)
    paused = Signal(bool)
    stopped = Signal()      # playback ended by itself (audio or voice failure)
    ended = Signal()
    error = Signal(str)

    def __init__(self):
        super().__init__()
        self.book = None
        self.voice = paths.DEFAULT_VOICE
        self.speed = 1.0
        self.pos = 0
        self.is_paused = True
        self.gen = 0
        self.session = 0            # bumped on teardown; render threads exit
        self.next_render = 0
        self.last = -1              # index of the book's final sentence
        self.cache = {}             # idx -> ((voice, speed), samples)
        self.queue = collections.deque()    # [idx, samples, offset played]
        self.ended_sent = False
        self.events = []            # posted by the audio and render threads
        self.cond = threading.Condition()
        self.output = None
        self.rate = None
        self.thread = None
        self.models = Models()
        # Other threads never touch Qt: they post events, drained here.
        self.poll = QTimer(self)
        self.poll.setInterval(40)
        self.poll.timeout.connect(self._drain)

    @property
    def running(self):
        return self.output is not None

    # -- lifecycle ---------------------------------------------------------
    def preload(self, voice):
        """Load the voice in the background so the first Play is quick."""
        def load():
            try:
                self._model_for(voice)
            except Exception:
                pass                    # Play reports it properly
        threading.Thread(target=load, daemon=True).start()

    def start(self, book, idx, voice, speed):
        if self.running and book is not self.book:
            self.stop()
        if self.running:
            self.set_voice(voice)
            self.set_speed(speed)
        else:
            model = paths.list_voices().get(voice)
            if not model:
                self.error.emit("That voice isn't installed.")
                return
            self.book, self.voice, self.speed = book, voice, speed
            self.pos = self.next_render = idx
            try:
                self.rate = voice_rate(voice, model)
                self.output = make_output(self.rate, self._fill)
            except Exception as e:
                self.output = None
                self.error.emit(f"Couldn't start audio playback ({e}).")
                return
            with self.cond:
                self.session += 1
                self.last = len(book.sentences) - 1
            self.thread = threading.Thread(
                target=self._render_loop, args=(book, self.session), daemon=True)
            self.thread.start()
            self.poll.start()
        if self.running:
            self.jump(idx)

    def stop(self):
        """End playback and clean up. Emits nothing - the caller asked."""
        self.poll.stop()
        if self.output:
            self.output.close()
            self.output = None
        with self.cond:
            self.session += 1
            self.gen += 1
            self.queue.clear()
            self.cache.clear()
            self.events.clear()
            self.cond.notify_all()
        if self.thread:
            self.thread.join(timeout=2)
            self.thread = None
        self.is_paused = True

    # -- controls ------------------------------------------------------------
    def jump(self, idx, play=True):
        if not self.running:
            return
        idx = max(0, min(idx, len(self.book.sentences) - 1))
        with self.cond:
            self.gen += 1
            self.pos = self.next_render = idx
            self.queue.clear()
            self.ended_sent = False
            self.cond.notify_all()
        if play:
            self.set_paused(False)
        self.position.emit(idx)

    def toggle(self):
        if self.is_paused and self.ended_sent:
            self.jump(self.pos)          # finished: play the last sentence again
        else:
            self.set_paused(not self.is_paused)

    def set_paused(self, paused):
        if not self.running:
            return
        with self.cond:
            self.is_paused = paused
        self.paused.emit(paused)

    def set_speed(self, speed):
        if speed == self.speed:
            return
        with self.cond:
            self.speed = speed
            self.cache.clear()
        if self.running:
            self.jump(self.pos, play=not self.is_paused)

    def set_voice(self, voice):
        if voice == self.voice:
            return
        with self.cond:
            self.voice = voice
            self.cache.clear()
        if not self.running:
            return
        try:
            rate = voice_rate(voice, paths.list_voices()[voice])
        except (OSError, ValueError, KeyError):
            rate = self.rate            # the render thread reports the failure
        if rate != self.rate:
            self.output.close()
            try:
                self.output = make_output(rate, self._fill)
                self.rate = rate
            except Exception as e:
                self.output = None
                self.stop()
                self.error.emit(f"Couldn't restart audio playback ({e}).")
                self.stopped.emit()
                return
        self.jump(self.pos, play=not self.is_paused)

    # -- audio thread --------------------------------------------------------
    def _fill(self, out):
        frames, filled = len(out), 0
        with self.cond:
            if not self.is_paused:
                while filled < frames and self.queue:
                    item = self.queue[0]
                    idx, samples, offset = item
                    if offset == 0:
                        self.events.append(("played", idx))
                    n = min(frames - filled, len(samples) - offset)
                    out[filled:filled + n] = samples[offset:offset + n]
                    filled += n
                    item[2] = offset + n
                    if item[2] >= len(samples):
                        self.queue.popleft()
                        if idx == self.last and not self.ended_sent:
                            self.ended_sent = True
                            self.events.append(("ended", None))
        out[filled:] = 0

    # -- main thread ---------------------------------------------------------
    def _drain(self):
        with self.cond:
            events, self.events = self.events, []
        played = [value for kind, value in events if kind == "played"]
        if played:
            with self.cond:
                self.pos = played[-1]
                self.cond.notify_all()
            self._reap()
            self.position.emit(played[-1])
        for kind, value in events:
            if kind == "error":
                self.error.emit(value)
            elif kind == "fatal":
                self.stop()
                self.error.emit(value)
                self.stopped.emit()
                return
            elif kind == "ended":
                self.ended.emit()

    def _reap(self):
        with self.cond:
            lo, hi = self.pos - KEEP_BEHIND, self.next_render + AHEAD
            for i in [i for i in self.cache if i < lo or i > hi]:
                del self.cache[i]

    # -- render thread -------------------------------------------------------
    def _post(self, kind, value):
        with self.cond:
            self.events.append((kind, value))

    def voice_for(self, book, idx):
        """The paragraph's own voice if the book gives it one, else the book voice."""
        if book.voices:
            return book.voices.get(book.paragraph_at(idx), self.voice)
        return self.voice

    def voices_changed(self, paragraphs):
        """book.voices changed for these paragraphs: re-render what's queued."""
        if not self.running:
            return
        spans = [self.book.paragraphs[n][1:] for n in paragraphs]
        with self.cond:
            for i in [i for i in self.cache if any(lo <= i < hi for lo, hi in spans)]:
                del self.cache[i]
            queued = any(lo < self.next_render and hi > self.pos for lo, hi in spans)
        if queued:
            self.jump(self.pos, play=not self.is_paused)

    def _model_for(self, voice):
        return self.models.get(voice)

    def _render_loop(self, book, session):
        total = len(book.sentences)
        while True:
            with self.cond:
                while self.session == session and self.next_render >= min(
                        total, self.pos + AHEAD + 1):
                    self.cond.wait()
                if self.session != session:
                    return
                gen, idx = self.gen, self.next_render
                key = (self.voice_for(book, idx), self.speed, self.rate)
                self.next_render += 1
                hit = self.cache.get(idx)
                samples = hit[1] if hit and hit[0] == key else None
            if samples is None:
                samples = self._synth(key, book.spoken(idx), session)
                if samples is None:
                    continue
                with self.cond:
                    if key == (self.voice_for(book, idx), self.speed, self.rate):
                        self.cache[idx] = (key, samples)
            with self.cond:
                if gen == self.gen and self.session == session:
                    self.queue.append([idx, samples, 0])

    def _synth(self, key, text, session):
        voice, speed, rate = key
        try:
            model = self._model_for(voice)
        except Exception as e:
            self._post("fatal", f"Couldn't load the voice {voice} ({e}).")
            with self.cond:
                while self.session == session:
                    self.cond.wait()
            return None
        err = None
        for _attempt in range(2):
            try:
                with self.models.lock:
                    parts = model.render(text, speed)
                break
            except Exception as e:
                err = e
        else:
            self._post("error", f"The voice failed to render a sentence ({err}).")
            return None
        gap = np.zeros(int(model.sample_rate * GAP / speed), np.int16)
        # The stream runs at the book voice's rate; another paragraph voice
        # may have its own.
        return resample(np.concatenate(parts + [gap]), model.sample_rate, rate)
