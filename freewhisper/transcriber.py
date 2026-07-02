import os
import sys
from pathlib import Path

import numpy as np


def _add_cuda_dlls():
    """Make pip-installed NVIDIA DLLs (cublas/cudnn) findable by ctranslate2."""
    base = Path(sys.prefix) / "Lib" / "site-packages" / "nvidia"
    for sub in ("cublas", "cudnn", "cuda_nvrtc"):
        p = base / sub / "bin"
        if p.is_dir():
            os.add_dll_directory(str(p))
            os.environ["PATH"] = str(p) + os.pathsep + os.environ.get("PATH", "")


class Transcriber:
    """Lazy-loads one faster-whisper model per language and keeps them warm."""

    def __init__(self, cfg):
        self.cfg = cfg
        self._models: dict[str, object] = {}

    def _get_model(self, language: str):
        if language not in self._models:
            _add_cuda_dlls()
            from faster_whisper import WhisperModel  # slow import, keep it lazy
            print(f"[stt] loading model for '{language}': {self.cfg.models[language]} ...")
            self._models[language] = WhisperModel(
                self.cfg.models[language],
                device=self.cfg.device,
                compute_type=self.cfg.compute_type,
            )
            print("[stt] model ready")
        return self._models[language]

    def transcribe(self, audio: np.ndarray, language: str) -> str:
        if audio.size < 1600:  # <0.1s — hotkey tap, not speech
            return ""
        model = self._get_model(language)
        # initial_prompt biases Whisper toward the personal dictionary
        prompt = ", ".join(self.cfg.dictionary) or None
        segments, _ = model.transcribe(
            audio,
            language=language,
            beam_size=self.cfg.beam_size,
            vad_filter=True,
            initial_prompt=prompt,
        )
        return " ".join(s.text.strip() for s in segments).strip()
