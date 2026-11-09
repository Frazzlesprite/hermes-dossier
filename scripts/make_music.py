"""An upbeat bed with variation, not a four-bar loop.

120 BPM, four on the floor, C major. What changed from the first version:

- an eight-bar progression with passing chords instead of four, so the loop does
  not announce itself every eight seconds
- per-bar variation in the kick, hats, bass and arpeggio, chosen from a fixed
  table so the render stays deterministic
- a snare fill on the last bar of every fourth, and a breakdown where the kick
  drops out
- a simple four-note motif that only enters once, so the second half has
  something the first half did not

Everything is oscillators, so there is nothing to license.
"""

from __future__ import annotations

import math

import numpy as np

RATE = 44100
BPM = 120.0
BEAT = 60.0 / BPM
BAR = BEAT * 4

# Eight bars: C, G, Am, F, Dm, G, F, G. The Dm in bar five is the turn that
# makes it feel like a progression rather than a loop.
CHORDS = [
    ([60, 64, 67, 74], 36),
    ([55, 59, 62, 69], 31),
    ([57, 60, 64, 71], 33),
    ([53, 57, 60, 67], 29),
    ([62, 65, 69, 72], 38),
    ([55, 59, 62, 69], 31),
    ([53, 57, 60, 67], 29),
    ([55, 59, 62, 69], 31),
]

MOTIF = [76, 79, 81, 79]  # E5 G5 A5 G5, over the last four bars


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


def kick(mix: Mix, at: float, gain: float = 0.9) -> None:
    n = int(0.22 * RATE)
    t = _t(n)
    body = np.sin(2 * np.pi * (95.0 - 60.0 * t / 0.22) * t).astype(np.float32)
    click = np.random.default_rng(3).normal(0, 1, n).astype(np.float32) * _decay(n, 220) * 0.25
    mix.add(at, (body * _decay(n, 18.0)) + click, gain)


def clap(mix: Mix, at: float, gain: float = 0.35, tight: bool = False) -> None:
    n = int((0.09 if tight else 0.18) * RATE)
    noise = np.random.default_rng(int(at * 1000) + 7).normal(0, 1, n).astype(np.float32)
    noise = np.diff(noise, prepend=0.0)
    mix.add(at, noise * _decay(n, 60.0 if tight else 34.0), gain, pan=0.1)


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
        voice += (2.0 * ((freq * t) % 1.0) - 1.0).astype(np.float32) * 0.32
    mix.add(at, voice * _env(n, 0.01, 0.16) * _decay(n, 6.0), gain, pan=-0.15)


def pluck(mix: Mix, at: float, note: int, gain: float = 0.14, pan: float = 0.0, ring: float = 0.2) -> None:
    n = int(ring * RATE)
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


# Per-bar pattern tables, so bar 1 and bar 5 do not sound identical.
KICK_PATTERNS = [
    [0, 1, 2, 3],
    [0, 1, 2, 3],
    [0, 1.5, 2, 3],
    [0, 1, 2, 2.75, 3],
    [0, 2, 2.75, 3],
    [0, 1, 2, 3],
    [0, 1, 2.5, 3],
    [0, 1, 2, 3.5],
]
ARP_SHAPES = ["up", "updown", "skip", "up", "double", "updown", "skip", "up"]


def render(duration: float, plan: list[tuple[float, float, float, str]]) -> np.ndarray:
    """plan: [(start, end, level 0..1, style)] covering the timeline in order."""
    mix = Mix(duration)
    bar = 0
    t = 0.0

    def context(moment: float) -> tuple[float, str]:
        for start, end, level, style in plan:
            if start <= moment < end:
                return level, style
        return (plan[-1][2], plan[-1][3]) if plan else (0.6, "groove")

    while t < duration - 0.05:
        chord, root = CHORDS[bar % len(CHORDS)]
        level, style = context(t)
        rng = np.random.default_rng(bar * 97 + 13)
        human = 0.94 + float(rng.random()) * 0.12

        pad(mix, t, chord, gain=(0.06 + 0.05 * level) * human, length=BAR + 0.2)

        if style != "intro":
            # Bass: root, fifth, octave, with a syncopated push every other bar.
            bass(mix, t, root, gain=0.28 + 0.2 * level)
            bass(mix, t + BEAT * 1.5, root + 7, gain=0.14 + 0.12 * level)
            bass(mix, t + BEAT * 2, root, gain=0.24 + 0.18 * level)
            if bar % 2 == 1:
                bass(mix, t + BEAT * 3.25, root + 12, gain=0.16 + 0.12 * level, length=0.16)

        if style in ("groove", "full"):
            for beat in KICK_PATTERNS[bar % len(KICK_PATTERNS)]:
                if style == "break" and beat in (1, 3):
                    continue
                kick(mix, t + beat * BEAT, gain=(0.55 + 0.3 * level) * human)

            clap(mix, t + BEAT, gain=(0.26 + 0.16 * level) * human)
            clap(mix, t + 3 * BEAT, gain=(0.26 + 0.16 * level) * human)

            offbeats = 8 if bar % 2 == 0 else 4
            for step in range(offbeats):
                hat(mix, t + step * BEAT / 2, gain=(0.06 + 0.05 * level) * human,
                    open_hat=(step % 2 == 1 and bar % 4 == 2))

        if style == "full" or (style == "groove" and level > 0.8):
            shape = ARP_SHAPES[bar % len(ARP_SHAPES)]
            for step in range(16):
                if shape == "skip" and step % 2 == 1:
                    continue
                index = step % len(chord)
                if shape == "updown" and (step // len(chord)) % 2 == 1:
                    index = len(chord) - 1 - index
                note = chord[index] + (12 if (shape == "double" or step % 8 >= 4) else 0)
                pluck(mix, t + step * BEAT / 4, note, gain=(0.06 + 0.05 * level) * human,
                      pan=(-0.35, 0.35)[step % 2], ring=0.16)
            if bar % 2 == 0:
                stab(mix, t + BEAT * 2.5, chord, gain=(0.09 + 0.07 * level) * human)

        if style == "break":
            # Half-time: pad, sparse pluck, no kick. Room to breathe.
            for step in range(4):
                pluck(mix, t + step * BEAT, chord[step % len(chord)] + 12,
                      gain=0.07, pan=(-0.2, 0.2)[step % 2], ring=0.35)

        if style == "full" and level >= 0.9 and bar % 8 >= 4:
            # The motif enters late, so the back half has a new idea.
            for index, note in enumerate(MOTIF):
                pluck(mix, t + index * BEAT, note, gain=0.08, pan=0.1, ring=0.5)

        # Fill on the last bar of every fourth.
        if style in ("groove", "full") and bar % 4 == 3:
            for index in range(4):
                clap(mix, t + 3 * BEAT + index * BEAT / 4, gain=0.16 + 0.03 * index, tight=True)

        t += BAR
        bar += 1

    return mix.buf
