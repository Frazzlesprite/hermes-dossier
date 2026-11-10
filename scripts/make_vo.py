"""Voiceover: neural TTS, cached, converted to a float track we can mix.

edge-tts needs the network at build time. If it is unavailable the build fails
loudly rather than shipping a silent video that pretends to have a voice.
"""

from __future__ import annotations

import asyncio
import hashlib
import subprocess
import tempfile
import wave
from pathlib import Path

import numpy as np

VOICE = "en-GB-RyanNeural"
RATE_CHANGE = "+12%"
PITCH = "-12Hz"
RATE = 44100
CACHE = Path(tempfile.gettempdir()) / "opencode" / "vo-cache"


def _ffmpeg() -> str:
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def synthesise(text: str) -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(f"{VOICE}|{RATE_CHANGE}|{PITCH}|{text}".encode("utf-8")).hexdigest()[:16]
    target = CACHE / f"{digest}.wav"
    if target.exists():
        return target

    mp3 = CACHE / f"{digest}.mp3"

    async def run() -> None:
        import edge_tts

        await edge_tts.Communicate(text, VOICE, rate=RATE_CHANGE, pitch=PITCH).save(str(mp3))

    asyncio.run(run())
    subprocess.run(
        [_ffmpeg(), "-y", "-loglevel", "error", "-i", str(mp3), "-ar", str(RATE), "-ac", "2", str(target)],
        check=True,
    )
    return target


def load(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as handle:
        frames = handle.readframes(handle.getnframes())
        width = handle.getsampwidth()
        channels = handle.getnchannels()
    if width != 2:
        raise ValueError("expected 16-bit PCM")
    data = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
    if channels == 2:
        data = data.reshape(-1, 2)
    else:
        data = np.repeat(data.reshape(-1, 1), 2, axis=1)
    return data


def track(lines: list[tuple[str, float]], duration: float) -> tuple[np.ndarray, list[tuple[str, float, float]]]:
    """Place each line at its start time. Returns the track and what landed where."""
    out = np.zeros((int(duration * RATE), 2), dtype=np.float32)
    placed: list[tuple[str, float, float]] = []
    for text, at in lines:
        clip = load(synthesise(text))
        # TTS lands around -7 dBFS peak, well under the music. Normalise each
        # line so the voice sits on top of the bed instead of inside it.
        peak = float(np.max(np.abs(clip))) or 1.0
        clip = clip * (0.95 / peak)
        start = int(at * RATE)
        end = min(out.shape[0], start + clip.shape[0])
        if start >= out.shape[0]:
            continue
        out[start:end] += clip[: end - start]
        placed.append((text, at, clip.shape[0] / RATE))
    return out, placed
