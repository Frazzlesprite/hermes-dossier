"""An upbeat bed: 120 BPM, four on the floor, built from oscillators.

Cheap to render, easy to re-cut, and no licensing. Intensity follows the scene
map, so the music lifts when the brief lands and drops out for the diff.
"""

from __future__ import annotations

import math

import numpy as np

RATE = 44100
BPM = 120.0
BEAT = 60.0 / BPM
BAR = BEAT * 4


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


# Bright, hopeful progression: C - G - Am - F, with a raised 9th on the stabs.
CHORDS = [
    ([60, 64, 67, 74], 36),
    ([55, 59, 62, 69], 31),
    ([57, 60, 64, 71], 33),
    ([53, 57, 60, 67], 29),
]


def kick(mix: Mix, at: float, gain: float = 0.9) -> None:
    n = int(0.22 * RATE)
    t = _t(n)
    body = np.sin(2 * np.pi * (95.0 - 60.0 * t / 0.22) * t).astype(np.float32)
    click = np.random.default_rng(3).normal(0, 1, n).astype(np.float32) * _decay(n, 220) * 0.25
    mix.add(at, (body * _decay(n, 18.0)) + click, gain)


def clap(mix: Mix, at: float, gain: float = 0.35) -> None:
    n = int(0.18 * RATE)
    noise = np.random.default_rng(int(at * 1000) + 7).normal(0, 1, n).astype(np.float32)
    noise = np.diff(noise, prepend=0.0)
    mix.add(at, noise * _decay(n, 34.0), gain, pan=0.1)


def hat(mix: Mix, at: float, gain: float = 0.12, open_hat: bool = False) -> None:
    n = int((0.16 if open_hat else 0.05) * RATE)
    noise = np.random.default_rng(int(at * 9000) + 11).normal(0, 1, n).astype(np.float32)
    noise = np.diff(noise, prepend=0.0) * np.diff(noise, prepend=0.0)
    mix.add(at, noise * _decay(n, 90.0 if not open_hat else 26.0), gain, pan=0.25)


def bass(mix: Mix, at: float, note: int, gain: float = 0.5, length: float = 0.22) -> None:
    n = int(length * RATE)
    t = _t(n)
    tone = (np.sin(2 * np.pi * midi(note) * t) + 0.35 * np.sin(4 * np.pi * midi(note) * t)).astype(np.float32)
    mix.add(at, tone * _env(n, 0.005, 0.12) * _decay(n, 5.0), gain)


def stab(mix: Mix, at: float, notes: list[int], gain: float = 0.16) -> None:
    n = int(0.26 * RATE)
    t = _t(n)
    voice = np.zeros(n, dtype=np.float32)
    for note in notes:
        freq = midi(note)
        saw = 2.0 * ((freq * t) % 1.0) - 1.0
        voice += saw.astype(np.float32) * 0.32
    mix.add(at, voice * _env(n, 0.01, 0.16) * _decay(n, 6.0), gain, pan=-0.15)


def arp(mix: Mix, at: float, note: int, gain: float = 0.14, pan: float = 0.0) -> None:
    n = int(0.2 * RATE)
    t = _t(n)
    tone = (
        np.sin(2 * np.pi * midi(note) * t) * 0.6
        + np.sin(4 * np.pi * midi(note) * t) * 0.25
        + np.sin(6 * np.pi * midi(note) * t) * 0.12
    ).astype(np.float32)
    mix.add(at, tone * _decay(n, 16.0), gain, pan=pan)


def pad(mix: Mix, at: float, notes: list[int], gain: float = 0.1, length: float = 2.0) -> None:
    n = int(length * RATE)
    t = _t(n)
    voice = np.zeros(n, dtype=np.float32)
    for index, note in enumerate(notes[:3]):
        voice += np.sin(2 * np.pi * midi(note) * t).astype(np.float32) * (0.5 - index * 0.08)
    mix.add(at, voice * _env(n, 0.4, 0.6), gain)


def riser(mix: Mix, at: float, gain: float = 0.16, length: float = 1.0) -> None:
    n = int(length * RATE)
    t = _t(n)
    freqs = np.linspace(240.0, 1800.0, n, dtype=np.float32)
    phase = 2 * np.pi * np.cumsum(freqs) / RATE
    tone = (2.0 * ((phase / (2 * np.pi)) % 1.0) - 1.0).astype(np.float32) * 0.25
    noise = np.random.default_rng(21).normal(0, 1, n).astype(np.float32) * 0.5
    mix.add(at, (tone + noise) * _env(n, 0.05, 0.08) * np.linspace(0.2, 1.0, n, dtype=np.float32), gain)


def impact(mix: Mix, at: float, gain: float = 0.4) -> None:
    n = int(0.9 * RATE)
    t = _t(n)
    body = np.sin(2 * np.pi * (85.0 - 45.0 * t) * t).astype(np.float32) * _decay(n, 4.0)
    air = np.random.default_rng(5).normal(0, 1, n).astype(np.float32) * np.exp(-18.0 * t)
    mix.add(at, body + air * 0.35, gain)


def render(duration: float, intensity: list[tuple[float, float, float]]) -> np.ndarray:
    """intensity: [(start, end, level 0..1)] in order, covering the timeline."""
    mix = Mix(duration)
    beat_index = 0
    t = 0.0

    def level_at(moment: float) -> float:
        for start, end, value in intensity:
            if start <= moment < end:
                return value
        return intensity[-1][2] if intensity else 0.5

    while t < duration - 0.05:
        bar = int(t // BAR)
        chord, root = CHORDS[bar % len(CHORDS)]
        level = level_at(t)

        # Harmony runs throughout, softest at the hook.
        pad(mix, t, chord, gain=0.07 + 0.05 * level, length=BAR + 0.2)

        if level > 0.15:
            for step in range(2):
                bass(mix, t + step * BEAT * 2, root, gain=0.30 + 0.25 * level)
                bass(mix, t + step * BEAT * 2 + BEAT, root + 12, gain=0.16 + 0.14 * level)

        if level > 0.35:
            for b in range(4):
                kick(mix, t + b * BEAT, gain=0.55 + 0.35 * level)
            clap(mix, t + BEAT, gain=0.28 + 0.2 * level)
            clap(mix, t + 3 * BEAT, gain=0.28 + 0.2 * level)
            for eighth in range(8):
                hat(mix, t + eighth * BEAT / 2, gain=0.07 + 0.06 * level,
                    open_hat=(eighth % 2 == 1))

        if level > 0.55:
            for sixteenth in range(16):
                if sixteenth % 4 == 2:
                    stab(mix, t + sixteenth * BEAT / 4, chord, gain=0.10 + 0.08 * level)
                note = chord[sixteenth % len(chord)] + (12 if sixteenth % 8 >= 4 else 0)
                arp(mix, t + sixteenth * BEAT / 4, note, gain=0.07 + 0.06 * level,
                    pan=(-0.35, 0.35)[sixteenth % 2])

        t += BAR
        beat_index += 1

    return mix.buf
