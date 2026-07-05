"""Subtle start/stop recording blips (Windows winsound, async, no deps).

Soft short sine tones with a fade so they don't click. Generated once into
temp WAVs and cached. play_start() is a higher note, play_stop() a lower one.
"""

import tempfile
import wave
from pathlib import Path

import numpy as np

_CACHE: dict[str, str] = {}


def _make_wav(path: Path, freq: float, ms: int = 110, vol: float = 0.22):
    sr = 16000
    n = int(sr * ms / 1000)
    t = np.arange(n) / sr
    env = np.clip(np.minimum(t * 60, (n / sr - t) * 60), 0, 1)  # fast fade in/out
    tone = (np.sin(2 * np.pi * freq * t)
            + 0.3 * np.sin(2 * np.pi * freq * 2 * t)) * env * vol
    pcm = (np.clip(tone, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def _get(name: str, freq: float) -> str:
    if name not in _CACHE:
        p = Path(tempfile.gettempdir()) / f"fw_blip_{name}.wav"
        if not p.exists():
            _make_wav(p, freq)
        _CACHE[name] = str(p)
    return _CACHE[name]


def _play(path: str):
    try:
        import winsound
        winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
    except Exception:
        pass


def play_start():
    _play(_get("start", 720))


def play_stop():
    _play(_get("stop", 480))
