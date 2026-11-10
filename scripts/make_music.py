"""A playful bed: C major, 126 BPM, swung sixteenths, glockenspiel lead.

The spy ostinato was too stern for a 34 second demo. This is a bouncy pluck
groove: staccato bass, offbeat claps, a woodblock, and a glock melody that
answers the chord every other bar. Sparse enough to leave the voice alone.
"""

from __future__ import annotations

import math

import numpy as np

RATE = 44100
BPM = 126.0
BEAT = 60.0 / BPM
BAR = BEAT * 4
SIXTEENTH = BEAT / 4
SWING = 0.62          # the second sixteenth of each pair lands late

CHORDS = [
    ([60, 64, 67], 36),   # C
    ([57, 60, 64], 33),   # Am
    ([53, 57, 60], 29),   # F
    ([55, 59, 62], 31),   # G
]

# (bar offset, beat offset, note, length in beats) for the glock answer.
MOTIF = [
    (0.0, 0.0, 79, 0.5), (0.0, 0.75, 81, 0.5), (0.0, 1.5, 79, 1.0),
    (1.0, 0.0, 76, 0.5), (1.0, 0.75, 74, 0.5), (1.0, 1.5, 72, 1.0),
]


def midi(note: int) -> float:
    return 440.0 * (2.0 ** ((note - 69) / 12.0))


def _t(n: int) -> np.ndarray:
    return np.arange(n, dtype=np.float32) / RATE


def _decay(n: int, rate: float) -> np.ndarray:
    return np.exp(-rate * _t(n)).astype(np.float32)


def _env(n: int, attack: float, release: float) -> np.ndarray:
    a = max(1, min(n, int(attack * RATE)))
    r = max(1, min(n, int(release * RATE)))
    env = np.ones(n, dtype=np.float32)
    env[:a] *= np.linspace(0.0, 1.0, a, dtype=np.float32)
    env[-r:] *= np.linspace(1.0, 0.0, r, dtype=np.float32)
    return env


class Mix:
    def __init__(self, duration: float) -> None:
        self.n = int(duration * RATE)
        self.buf = np.zeros((self.n, 2), dtype=np.float32)

    def add(self, at: float, signal: np.ndarray, gain: float = 1.0, pan: float = 0.0) -> None:
        i = int(at * RATE)
        if i < 0 or i >= self.n:
            return
        j = min(self.n, i + len(signal))
        chunk = signal[: j - i] * gain
        left = math.sqrt(max(0.0, 0.5 * (1.0 - pan)))
        right = math.sqrt(max(0.0, 0.5 * (1.0 + pan)))
        self.buf[i:j, 0] += chunk * left
        self.buf[i:j, 1] += chunk * right


def pluck(freq: float, n: int, *, bright: float = 0.5) -> np.ndarray:
    t = _t(n)
    tone = np.zeros(n, dtype=np.float32)
    for h, weight in ((1, 1.0), (2, 0.42), (3, 0.22), (5, 0.1)):
        tone += (np.sin(2 * np.pi * freq * h * t) * weight * (bright ** (h - 1))).astype(np.float32)
    return tone / 2.4


def glock(freq: float, n: int) -> np.ndarray:
    t = _t(n)
    tone = (
        np.sin(2 * np.pi * freq * t)
        + 0.5 * np.sin(2 * np.pi * freq * 2.76 * t)
        + 0.2 * np.sin(2 * np.pi * freq * 5.4 * t)
    ).astype(np.float32)
    return tone * np.exp(-9.0 * t)


def kick(mix: Mix, at: float, gain: float = 0.5) -> None:
    n = int(0.16 * RATE)
    t = _t(n)
    body = np.sin(2 * np.pi * (110.0 - 55.0 * t / 0.16) * t).astype(np.float32)
    mix.add(at, body * _decay(n, 22.0), gain)


def clap(mix: Mix, at: float, gain: float = 0.18) -> None:
    n = int(0.09 * RATE)
    noise = np.random.default_rng(int(at * 1300) + 5).normal(0, 1, n).astype(np.float32)
    noise = np.diff(noise, prepend=0.0)
    mix.add(at, noise * _decay(n, 60.0), gain, pan=0.12)


def woodblock(mix: Mix, at: float, gain: float = 0.16) -> None:
    n = int(0.06 * RATE)
    t = _t(n)
    tone = (np.sin(2 * np.pi * 1180 * t) + 0.4 * np.sin(2 * np.pi * 1760 * t)).astype(np.float32)
    mix.add(at, tone * _decay(n, 70.0), gain, pan=-0.2)


def shaker(mix: Mix, at: float, gain: float = 0.03) -> None:
    n = int(0.04 * RATE)
    noise = np.random.default_rng(int(at * 5000) + 17).normal(0, 1, n).astype(np.float32)
    noise = np.diff(noise, prepend=0.0)
    mix.add(at, noise * _decay(n, 90.0), gain, pan=-0.3)


def bass(mix: Mix, at: float, note: int, gain: float = 0.26) -> None:
    n = int(0.13 * RATE)
    tone = pluck(midi(note), n, bright=0.35)
    mix.add(at, tone * _env(n, 0.004, 0.07) * _decay(n, 14.0), gain)


def stab(mix: Mix, at: float, notes: list[int], gain: float = 0.1) -> None:
    n = int(0.18 * RATE)
    voice = np.zeros(n, dtype=np.float32)
    for note in notes:
        voice += pluck(midi(note + 12), n, bright=0.45)
    mix.add(at, voice * _env(n, 0.006, 0.1) * _decay(n, 18.0), gain, pan=0.08)


def bend(mix: Mix, at: float, note: int, gain: float = 0.09) -> None:
    """A little upward scoop: the cheapest way to sound friendly."""
    n = int(0.16 * RATE)
    t = _t(n)
    freq = midi(note) * (1.0 + 0.04 * np.exp(-18.0 * t))
    phase = 2 * np.pi * np.cumsum(freq) / RATE
    tone = np.sin(phase).astype(np.float32) * 0.7 + np.sin(2 * phase).astype(np.float32) * 0.2
    mix.add(at, tone * _decay(n, 16.0), gain, pan=0.25)


def render(duration: float, plan: list[tuple[float, float, float, str]]) -> np.ndarray:
    mix = Mix(duration)
    n = mix.n

    def context(moment: float) -> tuple[float, str]:
        for start, end, level, style in plan:
            if start <= moment < end:
                return level, style
        return (plan[-1][2], plan[-1][3]) if plan else (0.8, "main")

    chord_bus = Mix(duration)
    bass_bus = Mix(duration)
    scores = Mix(duration)

    bar = 0
    t = 0.0
    while t < duration - 0.02:
        chord, root = CHORDS[bar % len(CHORDS)]
        level, style = context(t)

        if style in ("build", "main", "lift"):
            kick(mix, t, 0.42)
            kick(mix, t + 2 * BEAT, 0.42)
            clap(mix, t + BEAT, 0.16)
            clap(mix, t + 3 * BEAT, 0.16)
            woodblock(mix, t + 1.5 * BEAT, 0.14)
            woodblock(mix, t + 3.5 * BEAT, 0.1)
            for step in range(16):
                shaker(mix, t + step * SIXTEENTH, 0.024)

        if style != "intro":
            for step in range(8):
                offset = step * 2 * SIXTEENTH
                if step % 2:
                    offset += SIXTEENTH * (SWING - 0.5) * 2
                note = root + (7 if step % 4 == 3 else 0)
                bass(bass_bus, t + offset, note, gain=0.22 + 0.08 * level)

        if style in ("build", "main", "lift"):
            for step in range(16):
                swung = step * SIXTEENTH
                if step % 2:
                    swung += SIXTEENTH * (SWING - 0.5) * 2
                note = chord[step % len(chord)] + (12 if step % 8 >= 4 else 0)
                gain = (0.075 + 0.045 * level) * (1.0 if step % 4 == 0 else 0.75)
                pl = pluck(midi(note), int(0.13 * RATE), bright=0.5)
                chord_bus.add(t + swung, pl * _decay(int(0.13 * RATE), 20.0), gain,
                              pan=(-0.35, 0.35)[step % 2])

        if style in ("main", "lift"):
            for bar_offset, beat_at, note, beats in MOTIF:
                if int(bar_offset) == bar % 2:
                    scores.add(t + beat_at * BEAT, glock(midi(note), int(0.5 * RATE)) * 0.6,
                               gain=0.10 + 0.04 * level, pan=0.2)
            if bar % 2 == 1:
                bend(scores, t + 2.5 * BEAT, chord[1] + 12, gain=0.07 + 0.03 * level)

        if style == "intro":
            # Something soft under the hook: quarter-note plucks, no drums.
            for beat in range(4):
                note = chord[beat % len(chord)] + (12 if beat % 2 else 0)
                pl = pluck(midi(note), int(0.4 * RATE), bright=0.38)
                chord_bus.add(t + beat * BEAT, pl * _decay(int(0.4 * RATE), 7.0), 0.055,
                              pan=(-0.2, 0.2)[beat % 2])

        if style == "break":
            for step in (0, 2):
                pl = pluck(midi(chord[step % len(chord)] + 12), int(0.3 * RATE), bright=0.4)
                chord_bus.add(t + step * BEAT, pl * _decay(int(0.3 * RATE), 9.0), 0.06)

        t += BAR
        bar += 1

    # A little duck of the bus under the chord, so it bounces.
    bounce = np.ones(n, dtype=np.float32)
    length = int(0.14 * RATE)
    curve = (1.0 - 0.35 * np.exp(-np.arange(length) / (0.04 * RATE))).astype(np.float32)
    step = 0.0
    while step < duration:
        i = int(step * RATE)
        j = min(n, i + length)
        if i < n:
            bounce[i:j] = np.minimum(bounce[i:j], curve[: j - i])
        step += BEAT

    mix.buf += chord_bus.buf * bounce[:, None]
    mix.buf += bass_bus.buf * bounce[:, None]
    mix.buf += scores.buf
    return mix.buf
