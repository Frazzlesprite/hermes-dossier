"""Spy-techno in 5/4, in the Mission Impossible tradition.

Not four-on-the-floor trance: a chromatic ostinato, brass stabs, and a lot of
space. Sparse drums on purpose, because the last cut had claps and hats fighting
the voice.

148 BPM, five beats a bar, E minor.
"""

from __future__ import annotations

import math

import numpy as np

RATE = 44100
BPM = 148.0
BEAT = 60.0 / BPM            # 0.4054 s
BAR = BEAT * 5               # 5/4
EIGHTH = BEAT / 2

# i, VI, iv, V in E minor, one chord per bar of five.
CHORDS = [
    ([64, 67, 71], 40),   # Em
    ([60, 64, 67], 36),   # C
    ([60, 64, 67], 33),   # Am
    ([59, 63, 66], 35),   # B
]

# The ostinato: ten eighths, chromatic, with a fifth at the end for the turn.
OSTINATO = [0, 0, 1, 1, 0, 0, -1, 0, 0, 5]

# Stabs land on beat one and beat four, which is what makes five feel like five.
STAB_BEATS = (0.0, 3.0)


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


def saw(freq: float, n: int, *, voices: int = 5, detune: float = 0.008,
        harmonics: int = 7, bright: float = 0.42) -> np.ndarray:
    t = _t(n)
    out = np.zeros(n, dtype=np.float32)
    spreads = [0.0] if voices <= 1 else [detune * (2.0 * i / (voices - 1) - 1.0) for i in range(voices)]
    for index, spread in enumerate(spreads):
        phase = (index * 0.41) % 1.0
        for h in range(1, harmonics + 1):
            amp = (bright ** (h - 1)) / h
            if amp < 0.012:
                break
            out += (np.sin(2 * np.pi * freq * (1.0 + spread) * h * t + phase * h) * amp).astype(np.float32)
    return out / max(1, voices)


def kick(mix: Mix, at: float, gain: float = 0.85) -> None:
    n = int(0.2 * RATE)
    t = _t(n)
    body = np.sin(2 * np.pi * (115.0 - 70.0 * t / 0.2) * t).astype(np.float32)
    click = np.random.default_rng(3).normal(0, 1, n).astype(np.float32) * _decay(n, 300) * 0.25
    mix.add(at, (body * _decay(n, 19.0)) + click, gain)


def rim(mix: Mix, at: float, gain: float = 0.22) -> None:
    """A rim click rather than a snare: no backbeat, just a marker."""
    n = int(0.06 * RATE)
    noise = np.random.default_rng(int(at * 1300) + 5).normal(0, 1, n).astype(np.float32)
    noise = np.diff(noise, prepend=0.0)
    tone = np.sin(2 * np.pi * 1750 * _t(n)).astype(np.float32) * 0.5
    mix.add(at, (noise + tone) * _decay(n, 55.0), gain, pan=0.12)


def shaker(mix: Mix, at: float, gain: float = 0.035) -> None:
    n = int(0.05 * RATE)
    noise = np.random.default_rng(int(at * 5000) + 17).normal(0, 1, n).astype(np.float32)
    noise = np.diff(noise, prepend=0.0)
    mix.add(at, noise * _decay(n, 80.0), gain, pan=-0.35)


def hat(mix: Mix, at: float, gain: float = 0.05) -> None:
    n = int(0.035 * RATE)
    noise = np.random.default_rng(int(at * 9100) + 11).normal(0, 1, n).astype(np.float32)
    noise = np.diff(noise, prepend=0.0) * np.diff(noise, prepend=0.0)
    mix.add(at, noise * _decay(n, 120.0), gain, pan=0.3)


def ostinato(mix: Mix, at: float, note: int, gain: float = 0.3) -> None:
    n = int(0.1 * RATE)
    tone = saw(midi(note), n, voices=3, detune=0.004, harmonics=5, bright=0.34)
    mix.add(at, tone * _env(n, 0.003, 0.05) * _decay(n, 7.0), gain)


def stab(mix: Mix, at: float, notes: list[int], gain: float = 0.2) -> None:
    """Brass-ish: saw plus a squarer edge, short."""
    n = int(0.3 * RATE)
    t = _t(n)
    voice = np.zeros(n, dtype=np.float32)
    for note in notes:
        freq = midi(note)
        voice += saw(freq, n, voices=4, detune=0.006, harmonics=6, bright=0.4)
        voice += (np.sign(np.sin(2 * np.pi * freq * t)) * 0.12).astype(np.float32)
    mix.add(at, voice * _env(n, 0.008, 0.14) * _decay(n, 7.0), gain, pan=-0.08)


def pad(mix: Mix, at: float, notes: list[int], gain: float = 0.08, length: float = 2.1) -> None:
    n = int(length * RATE)
    voice = np.zeros(n, dtype=np.float32)
    for note in notes:
        voice += saw(midi(note), n, voices=5, detune=0.012, harmonics=5, bright=0.3)
    mix.add(at, voice * _env(n, 0.35, 0.5), gain, pan=0.04)


def lead(mix: Mix, at: float, note: int, length: float, gain: float = 0.12) -> None:
    n = int(length * RATE)
    t = _t(n)
    phase = 2 * np.pi * midi(note) * t + 0.22 * np.sin(2 * np.pi * 5.0 * t)
    tone = (np.sin(phase) + 0.35 * np.sin(2 * phase)).astype(np.float32)
    mix.add(at, tone * _env(n, 0.04, 0.22) * _decay(n, 1.8), gain, pan=0.1)


def riser(mix: Mix, at: float, gain: float = 0.18, length: float = 2.0) -> None:
    n = int(length * RATE)
    noise = np.random.default_rng(29).normal(0, 1, n).astype(np.float32)
    noise = np.diff(noise, prepend=0.0)
    ramp = np.clip(np.linspace(0.0, 1.0, n, dtype=np.float32), 0.0, None) ** 2.2
    mix.add(at, noise * ramp, gain)


def impact(mix: Mix, at: float, gain: float = 0.4) -> None:
    n = int(0.9 * RATE)
    t = _t(n)
    body = np.sin(2 * np.pi * (80.0 - 42.0 * t) * t).astype(np.float32) * _decay(n, 4.0)
    air = np.random.default_rng(5).normal(0, 1, n).astype(np.float32) * np.exp(-18.0 * t)
    mix.add(at, body + air * 0.35, gain)


def sidechain(n: int, kicks: list[float], depth: float = 0.45) -> np.ndarray:
    env = np.ones(n, dtype=np.float32)
    length = int(0.2 * RATE)
    curve = (1.0 - depth * np.exp(-np.arange(length) / (0.05 * RATE))).astype(np.float32)
    for at in kicks:
        i = int(at * RATE)
        if i >= n:
            continue
        j = min(n, i + length)
        env[i:j] = np.minimum(env[i:j], curve[: j - i])
    return env


def render(duration: float, plan: list[tuple[float, float, float, str]]) -> np.ndarray:
    mix = Mix(duration)
    n = mix.n

    def context(moment: float) -> tuple[float, str]:
        for start, end, level, style in plan:
            if start <= moment < end:
                return level, style
        return (plan[-1][2], plan[-1][3]) if plan else (0.8, "main")

    bass_bus = Mix(duration)
    stab_bus = Mix(duration)
    pad_bus = Mix(duration)
    kicks: list[float] = []

    bar = 0
    t = 0.0
    while t < duration - 0.02:
        chord, root = CHORDS[bar % len(CHORDS)]
        level, style = context(t)

        # Drums: kick on one and four, rim on four, shaker underneath. No
        # backbeat, no claps, nothing competing with the voice.
        if style in ("build", "main", "lift"):
            for beat in (0.0, 3.0):
                kick(mix, t + beat * BEAT, 0.8)
                kicks.append(t + beat * BEAT)
            rim(mix, t + 4.0 * BEAT, 0.2)
            for beat in (1.0, 2.0):
                hat(mix, t + beat * BEAT, 0.045)
            for step in range(10):
                shaker(mix, t + step * EIGHTH, 0.028)
        elif style == "build":
            kick(mix, t, 0.7)
            kicks.append(t)
        elif style == "break":
            kick(mix, t, 0.55)
            kicks.append(t)
        elif style == "outro":
            kick(mix, t, 0.7)
            kicks.append(t)

        # The ostinato runs almost throughout: it is the spine.
        if style != "outro" or bar == 0:
            for step, semitone in enumerate(OSTINATO):
                ostinato(bass_bus, t + step * EIGHTH, root + semitone,
                         gain=(0.24 + 0.10 * level) * (1.0 if step % 5 == 0 else 0.8))

        if style in ("main", "lift"):
            for beat in STAB_BEATS:
                stab(stab_bus, t + beat * BEAT, chord, gain=0.13 + 0.07 * level)

        pad(pad_bus, t, chord, gain=0.05 + 0.03 * level, length=BAR + 0.2)

        if style == "lift" and bar % 2 == 0:
            for index, note in enumerate((76, 75, 74, 72)):
                lead(mix, t + index * BEAT, note, BEAT * 0.9, gain=0.1)

        if style == "outro" and bar == 0:
            impact(mix, t, 0.3)

        bar += 1
        t += BAR

    pump = sidechain(n, kicks, depth=0.4)
    stab_bus.buf *= pump[:, None]
    pad_bus.buf *= sidechain(n, kicks, depth=0.3)[:, None]

    mix.buf += bass_bus.buf
    mix.buf += stab_bus.buf
    mix.buf += pad_bus.buf
    return mix.buf
