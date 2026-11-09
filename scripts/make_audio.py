"""Synthesise the soundtrack for the demo, so the audio is ours to ship.

A pad-and-pulse bed in A minor, built from oscillators rather than sampled
music, plus cue sounds on the same timestamps the video uses. No third-party
audio, no licensing question, and it rebuilds with the video.

    from make_audio import build
    wav = build(74.5, scene_starts)

Developer tooling only: numpy is not a plugin dependency.
"""

from __future__ import annotations

import math
import tempfile
import wave
from pathlib import Path

import numpy as np

RATE = 44100
PEAK = 0.89


def midi(note: int) -> float:
    return 440.0 * (2.0 ** ((note - 69) / 12.0))


def envelope(n: int, attack: float, release: float, sustain: float = 1.0) -> np.ndarray:
    a = max(1, int(attack * RATE))
    r = max(1, int(release * RATE))
    env = np.ones(n, dtype=np.float32) * sustain
    a = min(a, n)
    env[:a] *= np.linspace(0.0, 1.0, a, dtype=np.float32)
    r = min(r, n)
    env[-r:] *= np.linspace(1.0, 0.0, r, dtype=np.float32)
    return env


def sweep(n: int, f0: float, f1: float, kind: str = "sine") -> np.ndarray:
    t = np.arange(n, dtype=np.float32) / RATE
    freqs = np.linspace(f0, f1, n, dtype=np.float32)
    phase = 2.0 * np.pi * np.cumsum(freqs) / RATE
    if kind == "saw":
        return (2.0 * ((phase / (2.0 * np.pi)) % 1.0) - 1.0).astype(np.float32)
    return np.sin(phase).astype(np.float32)


class Mix:
    def __init__(self, duration: float) -> None:
        self.n = int(duration * RATE)
        self.buf = np.zeros((self.n, 2), dtype=np.float32)

    def add(self, start: float, signal: np.ndarray, gain: float = 1.0, pan: float = 0.0) -> None:
        i = int(start * RATE)
        if i >= self.n or i < 0:
            return
        j = min(self.n, i + len(signal))
        chunk = signal[: j - i] * gain
        left = math.sqrt(max(0.0, 0.5 * (1.0 - pan)))
        right = math.sqrt(max(0.0, 0.5 * (1.0 + pan)))
        self.buf[i:j, 0] += chunk * left
        self.buf[i:j, 1] += chunk * right

    def write(self, path: Path) -> Path:
        data = np.tanh(self.buf * 1.15)
        peak = float(np.max(np.abs(data))) or 1.0
        data = data / peak * PEAK
        pcm = (data * 32767.0).astype("<i2")
        path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(path), "wb") as handle:
            handle.setnchannels(2)
            handle.setsampwidth(2)
            handle.setframerate(RATE)
            handle.writeframes(pcm.tobytes())
        return path


CHORDS = [
    ([57, 60, 64], 33),  # A minor
    ([53, 57, 60], 29),  # F major
    ([60, 64, 67], 36),  # C major
    ([55, 59, 62], 31),  # G major
]


def pad(mix: Mix, start: float, dur: float, notes: list[int], gain: float) -> None:
    n = int(dur * RATE)
    env = envelope(n, 0.7, 1.1, 1.0)
    for index, note in enumerate(notes):
        base = midi(note)
        voice = np.zeros(n, dtype=np.float32)
        for detune, weight in ((1.0, 1.0), (1.003, 0.6), (0.997, 0.5)):
            voice += np.sin(2 * np.pi * base * detune * np.arange(n) / RATE).astype(np.float32) * weight
        voice += np.sin(2 * np.pi * base * 2 * np.arange(n) / RATE).astype(np.float32) * 0.18
        mix.add(start, voice * env, gain * (0.9 - 0.1 * index), pan=-0.25 + 0.25 * index)


def sub(mix: Mix, start: float, dur: float, note: int, gain: float) -> None:
    n = int(dur * RATE)
    env = envelope(n, 0.4, 0.9, 0.9)
    tone = np.sin(2 * np.pi * midi(note) * np.arange(n) / RATE).astype(np.float32)
    mix.add(start, tone * env, gain)


def pluck(mix: Mix, start: float, note: int, gain: float, pan: float = 0.0) -> None:
    n = int(0.42 * RATE)
    t = np.arange(n) / RATE
    decay = np.exp(-9.0 * t).astype(np.float32)
    tone = (
        np.sin(2 * np.pi * midi(note) * t) * 0.7
        + np.sin(2 * np.pi * midi(note) * 2 * t) * 0.22
    ).astype(np.float32)
    mix.add(start, tone * decay, gain, pan=pan)


def thump(mix: Mix, start: float, gain: float) -> None:
    n = int(0.28 * RATE)
    t = np.arange(n) / RATE
    decay = np.exp(-16.0 * t).astype(np.float32)
    body = np.sin(2 * np.pi * (58.0 - 18.0 * t) * t).astype(np.float32)
    mix.add(start, body * decay, gain)


def hat(mix: Mix, start: float, gain: float) -> None:
    n = int(0.07 * RATE)
    decay = np.exp(-55.0 * np.arange(n) / RATE).astype(np.float32)
    noise = np.random.default_rng(int(start * 1000)).normal(0.0, 1.0, n).astype(np.float32)
    noise = np.diff(noise, prepend=0.0)  # cheap high-pass
    mix.add(start, noise * decay, gain, pan=0.3)


def whoosh(mix: Mix, start: float, gain: float) -> None:
    n = int(0.42 * RATE)
    env = envelope(n, 0.2, 0.2)
    tone = sweep(n, 320.0, 2400.0, "saw") * 0.35
    noise = np.random.default_rng(int(start * 977)).normal(0.0, 1.0, n).astype(np.float32) * 0.5
    mix.add(start, (tone + noise) * env, gain)


def tick(mix: Mix, start: float, gain: float, freq: float = 1500.0) -> None:
    n = int(0.05 * RATE)
    decay = np.exp(-60.0 * np.arange(n) / RATE).astype(np.float32)
    mix.add(start, np.sin(2 * np.pi * freq * np.arange(n) / RATE).astype(np.float32) * decay, gain)


def impact(mix: Mix, start: float, gain: float) -> None:
    n = int(1.1 * RATE)
    t = np.arange(n) / RATE
    decay = np.exp(-5.0 * t).astype(np.float32)
    body = np.sin(2 * np.pi * (72.0 - 40.0 * t) * t).astype(np.float32)
    air = np.random.default_rng(7).normal(0.0, 1.0, n).astype(np.float32) * np.exp(-22.0 * t)
    mix.add(start, (body + air * 0.3) * decay, gain)


def build(duration: float, scenes: list[tuple[str, float]], out: Path | None = None, cues: dict | None = None) -> Path:
    """scenes: (name, duration) in order. cues can override ticks, impacts and typing."""
    mix = Mix(duration)
    starts: list[float] = []
    cursor = 0.0
    for _name, dur in scenes:
        starts.append(cursor)
        cursor += dur

    # Harmony first, all the way through.
    bar = 2.86
    index = 0
    time = 0.0
    while time < duration:
        notes, root = CHORDS[index % len(CHORDS)]
        remaining = duration - time
        span = min(bar, remaining)
        if span <= 0:
            break
        level = 0.16 if time < 8.0 else 0.2
        pad(mix, time, span + 0.4, notes, level)
        sub(mix, time, span, root, 0.10)
        index += 1
        time += bar

    # Pulse and arpeggio come in at the sources scene, 8.0 seconds in.
    beat = 0.714
    time = 8.0
    step = 0
    while time < duration:
        chord, _root = CHORDS[int((time - 8.0) // bar) % len(CHORDS)]
        thump(mix, time, 0.22 if step % 2 == 0 else 0.12)
        if time > 14.0:
            hat(mix, time + beat / 2, 0.05)
        note = chord[step % len(chord)] + 12
        pluck(mix, time, note, 0.09, pan=(-0.3, 0.3)[step % 2])
        time += beat
        step += 1

    cues = cues or {}

    # Scene changes: a whoosh, and a soft impact on the big reveals.
    for start in starts[1:]:
        whoosh(mix, start - 0.16, 0.16)
    for moment in cues.get("impacts", (starts[3], starts[5], starts[6])):
        impact(mix, float(moment), 0.22)

    for start in cues.get("typing", (starts[1] + 0.35,)):
        for i in range(10):
            tick(mix, float(start) + i * 0.08, 0.05, 900 + 70 * i)

    for moment in cues.get("ticks", (starts[3] + 1.0,)):
        tick(mix, float(moment), 0.10, 1760.0)
    for moment in cues.get("soft", ()):
        tick(mix, float(moment), 0.06, 1180.0)

    # Quiet tail.
    fade_n = int(1.4 * RATE)
    mix.buf[-fade_n:] *= np.linspace(1.0, 0.0, fade_n, dtype=np.float32)[:, None]

    target = out or (Path(tempfile.gettempdir()) / "opencode" / "valve-audio.wav")
    return mix.write(target)


if __name__ == "__main__":
    scenes = [("title", 4.5), ("command", 3.5), ("sources", 12.5), ("brief", 17.0),
              ("series", 11.5), ("pdf", 7.5), ("diff", 9.5), ("close", 8.5)]
    print(build(sum(d for _, d in scenes), scenes))
