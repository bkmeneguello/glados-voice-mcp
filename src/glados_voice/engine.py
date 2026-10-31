"""Warm, streaming wrapper around the upstream GLaDOS TTS module (``glados_voice._glados``).

Models are loaded once, text is split into sentences, and playback starts as
soon as the first sentence is synthesized while the rest keeps rendering.
Only the public ``glados.TTS`` API is used.
"""

import os
import queue
import re
import threading
import time
from collections import deque
from typing import Optional

import numpy as np
import onnxruntime as ort
import sounddevice as sd

# Must run before the CUDA provider is created (no-op on builds without it).
if hasattr(ort, "preload_dlls"):
    ort.preload_dlls()

from . import _glados as glados  # noqa: E402
from .models import ensure_models, model_file, use_models_dir  # noqa: E402

SENTENCE_SPLIT = re.compile(r"(?<=[.!?;:])\s+|\n+")
CLAUSE_SPLIT = re.compile(r"(?<=,)\s+")
MAX_CHUNK_CHARS = 240
SPEECH_CHARS_PER_SECOND = 14.0  # rough spoken rate, used for retry estimates
LOAD_SECONDS_ESTIMATE = 12.0
WARMUP_PHRASES = (
    "Hello there.",
    "Hello, and welcome to the enrichment center.",
    "We hope your brief detention in the relaxation vault has been a pleasant one.",
)


def split_text(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    """Split text into sentence-sized chunks, breaking overlong ones at commas."""
    chunks = []
    for sentence in SENTENCE_SPLIT.split(text.strip()):
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(sentence) <= max_chars:
            chunks.append(sentence)
            continue
        current = ""
        for clause in CLAUSE_SPLIT.split(sentence):
            if current and len(current) + len(clause) + 1 > max_chars:
                chunks.append(current)
                current = clause
            else:
                current = f"{current} {clause}".strip()
        if current:
            chunks.append(current)
    return chunks


class VoiceEngine:
    """Background synthesis worker plus a persistent audio output stream.

    backend: ``cpu`` (default; lowest latency for sentence-sized chunks),
    ``cuda``, or ``auto`` (CPU for short chunks, CUDA for long ones).
    """

    def __init__(self, backend: Optional[str] = None, auto_cuda_chars: int = 160):
        self.backend = (backend or os.environ.get("GLADOS_BACKEND", "cpu")).lower()
        if self.backend not in ("cpu", "cuda", "auto"):
            raise ValueError(f"Unknown backend: {self.backend}")
        self.auto_cuda_chars = auto_cuda_chars
        self.ready = threading.Event()
        self.error: Optional[BaseException] = None
        self.load_seconds: Optional[float] = None
        self.last_first_audio_ms: Optional[float] = None
        self._load_started: Optional[float] = None
        self._pending_chars = 0  # text queued but not yet synthesized (approximate)

        self._tts = None
        self._cuda_session = None
        self._cpu_session = None
        self._jobs: "queue.Queue[tuple[int, str, float]]" = queue.Queue()
        self._generation = 0
        self._lock = threading.Lock()
        self._buffer: deque = deque()  # float32 mono arrays awaiting playback
        self._buffer_offset = 0
        self._in_flight = 0  # jobs queued or being synthesized
        self._idle = threading.Event()
        self._idle.set()
        self._stream: Optional[sd.OutputStream] = None
        self._thread = threading.Thread(target=self._run, name="glados-voice", daemon=True)

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> "VoiceEngine":
        self._load_started = time.perf_counter()
        self._thread.start()
        return self

    def _load(self) -> None:
        t0 = time.perf_counter()
        ensure_models()  # first run downloads the ONNX files
        use_models_dir()
        model_path = str(model_file())
        if self.backend == "cpu":
            # glados.TTS() uses every available provider; hide CUDA to skip its slow load.
            original = ort.get_available_providers
            ort.get_available_providers = lambda: ["CPUExecutionProvider"]
            try:
                self._tts = glados.TTS(model_path=model_path)
            finally:
                ort.get_available_providers = original
        else:
            self._tts = glados.TTS(model_path=model_path)
        providers = self._tts.session.get_providers()
        if "CUDAExecutionProvider" in providers:
            self._cuda_session = self._tts.session
        if self.backend == "cpu":
            self._cpu_session = self._tts.session  # already CPU-only, avoid a second slow load
        elif self.backend == "auto" and self._cuda_session is not None:
            self._cpu_session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
        if self._cpu_session is None and self._cuda_session is None:
            self._cpu_session = self._tts.session
        if self.backend == "cuda" and self._cuda_session is None:
            raise RuntimeError("CUDA backend requested but CUDAExecutionProvider is unavailable")
        self._select_session(len(WARMUP_PHRASES[0]))
        for phrase in WARMUP_PHRASES:
            self._select_session(len(phrase))
            self._tts.generate_speech_audio(phrase)
        self._stream = sd.OutputStream(
            samplerate=self._tts.rate, channels=1, dtype="float32", callback=self._on_audio
        )
        self._stream.start()
        self.load_seconds = time.perf_counter() - t0

    def _select_session(self, n_chars: int) -> None:
        if self.backend == "cuda":
            session = self._cuda_session
        elif self.backend == "auto" and self._cuda_session and n_chars >= self.auto_cuda_chars:
            session = self._cuda_session
        else:
            session = self._cpu_session
        self._tts.session = session

    def _run(self) -> None:
        try:
            self._load()
        except BaseException as e:  # surfaced through status()
            self.error = e
            return
        self.ready.set()
        while True:
            generation, text, requested_at = self._jobs.get()
            try:
                self._synthesize(generation, text, requested_at)
                self.error = None
            except Exception as e:
                self.error = e
            finally:
                with self._lock:
                    self._in_flight -= 1
                    if self._in_flight == 0:
                        self._pending_chars = 0
                    self._update_idle()

    def _synthesize(self, generation: int, text: str, requested_at: float) -> None:
        first = True
        for chunk in split_text(text):
            if generation != self._generation:
                return
            self._select_session(len(chunk))
            audio = np.asarray(self._tts.generate_speech_audio(chunk), dtype=np.float32).reshape(-1)
            with self._lock:
                if generation != self._generation:
                    return
                self._buffer.append(audio)
                self._pending_chars = max(0, self._pending_chars - len(chunk) - 1)
                self._update_idle()
            if first:
                self.last_first_audio_ms = (time.perf_counter() - requested_at) * 1e3
                first = False

    # -- playback ----------------------------------------------------------

    def _on_audio(self, outdata, frames, time_info, status) -> None:
        outdata.fill(0)
        filled = 0
        with self._lock:
            while filled < frames and self._buffer:
                head = self._buffer[0]
                take = min(frames - filled, len(head) - self._buffer_offset)
                outdata[filled : filled + take, 0] = head[self._buffer_offset : self._buffer_offset + take]
                filled += take
                self._buffer_offset += take
                if self._buffer_offset >= len(head):
                    self._buffer.popleft()
                    self._buffer_offset = 0
            self._update_idle()

    def _update_idle(self) -> None:
        if self._in_flight == 0 and not self._buffer:
            self._idle.set()
        else:
            self._idle.clear()

    # -- public API --------------------------------------------------------

    def speak(self, text: str, interrupt: bool = True) -> None:
        """Queue text for speech. Returns immediately."""
        if not text.strip():
            return
        if interrupt:
            self.stop()
        with self._lock:
            self._in_flight += 1
            self._pending_chars += len(text)
            self._idle.clear()
            generation = self._generation
        self._jobs.put((generation, text, time.perf_counter()))

    def try_speak(self, text: str) -> tuple[bool, float]:
        """Queue text only if nothing is loading, queued or playing.

        Returns (accepted, retry_after_seconds); the estimate is 0 when accepted.
        """
        if not text.strip():
            return True, 0.0
        with self._lock:
            if self._in_flight > 0 or self._buffer:
                return False, self._retry_after()
            self._in_flight += 1
            self._pending_chars += len(text)
            self._idle.clear()
            generation = self._generation
        self._jobs.put((generation, text, time.perf_counter()))
        return True, 0.0

    def _retry_after(self) -> float:
        """Estimated seconds until idle. Call with the lock held."""
        rate = self._tts.rate if self._tts else 22050
        buffered = (sum(len(a) for a in self._buffer) - self._buffer_offset) / rate
        pending = self._pending_chars / SPEECH_CHARS_PER_SECOND
        return buffered + pending + self.load_eta() + 1.0

    def stop(self) -> None:
        """Drop queued text and silence current playback."""
        with self._lock:
            self._generation += 1
            self._pending_chars = 0
            self._buffer.clear()
            self._buffer_offset = 0
            drained = 0
            try:
                while True:
                    self._jobs.get_nowait()
                    drained += 1
            except queue.Empty:
                pass
            self._in_flight -= drained
            self._update_idle()

    def wait_idle(self, timeout: Optional[float] = None) -> bool:
        """Block until everything queued has been synthesized and played."""
        return self._idle.wait(timeout)

    def load_eta(self) -> float:
        """Estimated seconds until the models are loaded (0 once ready or failed)."""
        if self.ready.is_set() or self.error or self._load_started is None:
            return 0.0
        return max(2.0, LOAD_SECONDS_ESTIMATE - (time.perf_counter() - self._load_started))

    def status(self) -> dict:
        load_failed = self.error is not None and not self.ready.is_set()
        return {
            "ready": self.ready.is_set(),
            "load_eta_seconds": round(self.load_eta()),
            "error": repr(self.error) if self.error else None,
            "backend": self.backend,
            "providers": self._tts.session.get_providers() if self._tts else None,
            "load_seconds": self.load_seconds,
            "last_first_audio_ms": self.last_first_audio_ms,
            "speaking": not load_failed and not self._idle.is_set(),  # a failed load never plays queued text
        }
