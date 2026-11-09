"""Mix the demo soundtrack: upbeat bed, scene hits, and the voiceover on top.

The music is ducked under the voice so the narration stays legible, which is the
only mixing decision that really matters here.

    from make_audio import build
    wav = build(duration, scenes, cues={"intensity": [...], "voice": [...]})
"""

from __future__ import annotations

import math
import tempfile
import wave
from pathlib import Path

import numpy as np

import make_music
import make_vo

RATE = 44100
PEAK = 0.78


def _smooth(signal: np.ndarray, attack: float = 0.02, release: float = 0.25) -> np.ndarray:
    """One-pole envelope follower, so the duck does not click."""
    out = np.zeros_like(signal)
    a = 1.0 - math.exp(-1.0 / (attack * RATE))
    r = 1.0 - math.exp(-1.0 / (release * RATE))
    level = 0.0
    for index, value in enumerate(signal):
        coefficient = a if value > level else r
        level += coefficient * (value - level)
        out[index] = level
    return out


def build(
    duration: float,
    scenes: list[tuple[str, float]],
    out: Path | None = None,
    cues: dict | None = None,
) -> Path:
    cues = cues or {}
    starts: list[float] = []
    cursor = 0.0
    for _name, span in scenes:
        starts.append(cursor)
        cursor += span

    plan = cues.get("plan") or [
        (start, start + span, 0.8, "groove") for start, (_name, span) in zip(starts, scenes)
    ]
    music = make_music.render(duration, plan)

    events = make_music.Mix(duration)
    for start in starts[1:]:
        make_music.riser(events, max(0.0, start - 2.0), gain=0.18, length=2.0)
        make_music.impact(events, start, gain=0.30)
    for moment in cues.get("ticks", ()):
        make_music.open_hat(events, float(moment), gain=0.3)
    music = music + events.buf

    lines = cues.get("voice") or []
    speech = None
    placed = []
    if lines:
        speech, placed = make_vo.track(lines, duration)
        envelope = _smooth(np.abs(speech).max(axis=1))
        peak = float(envelope.max()) or 1.0
        behind = 1.0 - 0.86 * (envelope / peak)
        music *= behind[:, None]

    music *= 0.82  # leave room for the voice
    mix = music if speech is None else music + speech
    data = np.tanh(mix * 1.05)
    peak = float(np.max(np.abs(data))) or 1.0
    data = data / peak * PEAK

    target = out or (Path(tempfile.gettempdir()) / "opencode" / "demo-audio.wav")
    target.parent.mkdir(parents=True, exist_ok=True)
    pcm = (data * 32767.0).astype("<i2")
    with wave.open(str(target), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        handle.writeframes(pcm.tobytes())

    for text, at, span in placed:
        print(f"  voice {at:5.1f}s  {span:4.1f}s  {text}")
    return target
