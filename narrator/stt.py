"""Speech-to-text via Silero VAD + mlx-whisper."""

import sys
import time
from typing import Optional

import numpy as np


class VoiceInput:
    """Mic capture with VAD-gated recording and Whisper transcription."""

    def __init__(
        self,
        stt_model: str = "mlx-community/whisper-tiny",
        silence_timeout: float = 1.5,
        listen_timeout: float = 10.0,
    ):
        self.stt_model = stt_model
        self.silence_timeout = silence_timeout
        self.listen_timeout = listen_timeout
        self._vad_model = None
        self._vad_utils = None

    # ------------------------------------------------------------------
    # Lazy model loading
    # ------------------------------------------------------------------

    def _ensure_vad(self):
        if self._vad_model is not None:
            return
        import torch
        self._vad_model, self._vad_utils = torch.hub.load(
            repo_or_dir="snakers4/silero-vad",
            model="silero_vad",
            trust_repo=True,
        )

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record_utterance(self) -> Optional[np.ndarray]:
        """Record audio from the mic with VAD-based start/stop detection.

        Opens a sounddevice InputStream at 16 kHz mono. Waits for speech
        to begin (Silero VAD), then records until *silence_timeout* seconds
        of continuous silence. Returns the audio as a float32 numpy array
        normalised to [-1, 1], or None on timeout.
        """
        import sounddevice as sd
        import torch
        self._ensure_vad()

        sample_rate = 16000
        chunk_samples = 512  # ~32 ms at 16 kHz
        speech_threshold = 0.5

        frames: list[np.ndarray] = []
        speech_started = False
        silence_start: Optional[float] = None
        deadline = time.monotonic() + self.listen_timeout

        stream = sd.InputStream(
            samplerate=sample_rate,
            channels=1,
            dtype="int16",
            blocksize=chunk_samples,
        )
        stream.start()

        try:
            while time.monotonic() < deadline:
                data, _ = stream.read(chunk_samples)
                audio_f32 = data.flatten().astype(np.float32) / 32768.0
                tensor = torch.from_numpy(audio_f32)

                confidence = self._vad_model(tensor, sample_rate).item()

                if not speech_started:
                    if confidence >= speech_threshold:
                        speech_started = True
                        silence_start = None
                        frames.append(audio_f32)
                else:
                    frames.append(audio_f32)
                    if confidence < speech_threshold:
                        if silence_start is None:
                            silence_start = time.monotonic()
                        elif time.monotonic() - silence_start >= self.silence_timeout:
                            break
                    else:
                        silence_start = None
        finally:
            stream.stop()
            stream.close()
            # Reset VAD state for next call
            self._vad_model.reset_states()

        if not frames:
            return None

        return np.concatenate(frames)

    # ------------------------------------------------------------------
    # Transcription
    # ------------------------------------------------------------------

    def transcribe(self, audio: np.ndarray) -> str:
        """Transcribe a float32 audio array using mlx-whisper."""
        import mlx_whisper

        result = mlx_whisper.transcribe(
            audio,
            path_or_hf_repo=self.stt_model,
            language="en",
        )
        return result.get("text", "").strip()

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def listen_and_transcribe(self) -> Optional[str]:
        """Record from the mic, then transcribe. Returns text or None."""
        audio = self.record_utterance()
        if audio is None or len(audio) < 1600:  # < 0.1 s
            return None
        text = self.transcribe(audio)
        return text if text else None
