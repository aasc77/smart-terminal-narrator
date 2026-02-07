"""Wake word detection using openWakeWord with optional speech interrupt."""

import threading
import time
from typing import Callable, Optional

import numpy as np


class WakeWordListener:
    """Always-on wake word detection that triggers a callback on detection."""

    def __init__(
        self,
        wake_phrase: str = "hey jarvis",
        on_wake: Optional[Callable[[], None]] = None,
        on_speech_interrupt: Optional[Callable[[], None]] = None,
        threshold: float = 0.5,
    ):
        self.wake_phrase = wake_phrase
        self.on_wake = on_wake
        self.on_speech_interrupt = on_speech_interrupt
        self.threshold = threshold
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._oww_model = None
        self._vad_model = None

    def _ensure_models(self):
        if self._oww_model is not None:
            return

        from openwakeword.model import Model
        self._oww_model = Model(
            wakeword_models=[self.wake_phrase],
            inference_framework="onnx",
        )

        # Silero VAD for speech-based interrupt detection
        if self.on_speech_interrupt:
            import torch
            self._vad_model, _ = torch.hub.load(
                repo_or_dir="snakers4/silero-vad",
                model="silero_vad",
                trust_repo=True,
            )

    def start(self):
        """Start wake word detection in a background thread."""
        self._stop.clear()
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop the listener."""
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _listen_loop(self):
        import sounddevice as sd

        self._ensure_models()

        sample_rate = 16000
        # openWakeWord expects 1280-sample chunks (80 ms at 16 kHz)
        chunk_samples = 1280
        cooldown_until = 0.0

        stream = sd.InputStream(
            samplerate=sample_rate,
            channels=1,
            dtype="int16",
            blocksize=chunk_samples,
        )
        stream.start()

        try:
            while not self._stop.is_set():
                data, _ = stream.read(chunk_samples)
                audio_i16 = data.flatten()

                # Feed openWakeWord
                prediction = self._oww_model.predict(audio_i16)

                now = time.monotonic()
                for name, score in prediction.items():
                    if score >= self.threshold and now >= cooldown_until:
                        cooldown_until = now + 3.0  # 3 s cooldown
                        if self.on_wake:
                            threading.Thread(
                                target=self.on_wake, daemon=True
                            ).start()
                        break

                # VAD-based interrupt: detect user speech during TTS
                if self._vad_model and self.on_speech_interrupt:
                    import torch
                    audio_f32 = audio_i16.astype(np.float32) / 32768.0
                    # Silero VAD needs 512-sample chunks
                    for i in range(0, len(audio_f32) - 511, 512):
                        chunk = torch.from_numpy(audio_f32[i:i + 512])
                        conf = self._vad_model(chunk, sample_rate).item()
                        if conf >= 0.7:
                            self.on_speech_interrupt()
                            break
        finally:
            stream.stop()
            stream.close()
            if self._vad_model:
                self._vad_model.reset_states()
