"""Late-90s / early-2000s trance: 140 BPM, rolling bass, supersaws.

The reference is the uplifting end of the genre rather than the Tron score:
A minor, a sixteen-step rolling bassline, open hats on every offbeat, a
supersaw chord bed and a lead that arrives after the breakdown.

Everything is oscillators, so nothing to license.
"""

from __future__ import annotations

import math

import numpy as np

RATE = 44100
BPM = 140.0
BEAT = 60.0 / BPM          # 0.4286 s
BAR = BEAT * 4
SIXTEENTH = BEAT / 4

# Am, F, C, G twice, with a G# turn at the end of the second phrase.
CHORDS = [
    ([57, 60, 64], 33),   # Am
    ([53, 57, 60], 29),   # F
    ([48, 52, 55], 36),   # C
    ([55, 59, 62], 31),   # G
    ([57, 60, 64], 33),   # Am
    ([53, 57, 60], 29),   # F
    ([55, 59, 62], 31),   # G
    ([56, 59, 63], 28),   # G# dim, the turn
]

# The rolling pattern, in semitones from the root. This is the genre.
ROLL = [0, 0, 12, 0, 0, 12, 0, 7, 0, 0, 12, 0, 0, 12, 7, 12]

# Lead phrase: (bar, beat, note, length in beats).
LEAD = [
    (0.0, 0.0, 76, 1.5), (0.0, 1.5, 74, 0.5), (0.0, 2.0, 72, 1.0), (0.0, 3.0, 71, 1.0),
    (1.0, 0.0, 72, 1.5), (1.0, 1.5, 71, 0.5), (1.0, 2.0, 69, 2.0),
    (2.0, 0.0, 76, 1.5), (2.0, 1.5, 79, 0.5), (2.0, 2.0, 81, 1.0), (2.0, 3.0, 79, 1.0),
    (3.0, 0.0, 76, 3.0),
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


# ------------------------------------------------------------------- supersaw


def supersaw(freq: float, n: int, *, voices: int = 7, detune: float = 0.013,
             harmonics: int = 6, bright: float = 0.45) -> np.ndarray:
    """Detuned saw stack: the defining sound of the era.

    Each voice gets its own fixed phase offset, otherwise the detune comb
    filters into a buzz at the attack.
    """
    t = _t(n)
    out = np.zeros(n, dtype=np.float32)
    if voices <= 1:
        spreads = [0.0]
    else:
        spreads = [detune * (2.0 * i / (voices - 1) - 1.0) for i in range(voices)]
    for index, spread in enumerate(spreads):
        phase = (index * 0.37) % 1.0
        for h in range(1, harmonics + 1):
            amp = (bright ** (h - 1)) / h
            if amp < 0.01:
                break
            out += (np.sin(2 * np.pi * freq * (1.0 + spread) * h * t + phase * h) * amp).astype(np.float32)
    return out / max(1, voices)


# -------------------------------------------------------------------- elements


def kick(mix: Mix, at: float, gain: float = 0.9) -> None:
    n = int(0.19 * RATE)
    t = _t(n)
    body = np.sin(2 * np.pi * (120.0 - 78.0 * t / 0.19) * t).astype(np.float32)
    click = np.random.default_rng(3).normal(0, 1, n).astype(np.float32) * _decay(n, 300) * 0.32
    mix.add(at, (body * _decay(n, 20.0)) + click, gain)


def clap(mix: Mix, at: float, gain: float = 0.3) -> None:
    n = int(0.13 * RATE)
    noise = np.random.default_rng(int(at * 1300) + 5).normal(0, 1, n).astype(np.float32)
    noise = np.diff(noise, prepend=0.0)
    mix.add(at, noise * _decay(n, 45.0), gain, pan=0.05)


def open_hat(mix: Mix, at: float, gain: float = 0.14) -> None:
    """The offbeat 'tss' that carries the groove."""
    n = int(0.14 * RATE)
    noise = np.random.default_rng(int(at * 9100) + 11).normal(0, 1, n).astype(np.float32)
    noise = np.diff(noise, prepend=0.0) * np.diff(noise, prepend=0.0)
    mix.add(at, noise * _decay(n, 26.0), gain, pan=0.3)


def shaker(mix: Mix, at: float, gain: float = 0.05) -> None:
    n = int(0.04 * RATE)
    noise = np.random.default_rng(int(at * 5000) + 17).normal(0, 1, n).astype(np.float32)
    noise = np.diff(noise, prepend=0.0)
    mix.add(at, noise * _decay(n, 90.0), gain, pan=-0.3)


def crash(mix: Mix, at: float, gain: float = 0.2) -> None:
    n = int(1.1 * RATE)
    noise = np.random.default_rng(23).normal(0, 1, n).astype(np.float32)
    noise = np.diff(noise, prepend=0.0)
    mix.add(at, noise * _decay(n, 5.5), gain, pan=-0.1)


def roll_bass(mix: Mix, at: float, note: int, gain: float = 0.26) -> None:
    n = int(0.095 * RATE)
    tone = supersaw(midi(note), n, voices=3, detune=0.004, harmonics=4, bright=0.3)
    mix.add(at, tone * _env(n, 0.003, 0.06) * _decay(n, 6.0), gain)


def bass_pluck(mix: Mix, at: float, note: int, gain: float = 0.12) -> None:
    n = int(0.16 * RATE)
    tone = supersaw(midi(note), n, voices=2, detune=0.003, harmonics=5, bright=0.4)
    mix.add(at, tone * _decay(n, 22.0), gain, pan=0.0)


def chord_stab(mix: Mix, at: float, notes: list[int], gain: float = 0.16, length: float = 0.22) -> None:
    n = int(length * RATE)
    voice = np.zeros(n, dtype=np.float32)
    for note in notes:
        voice += supersaw(midi(note), n, voices=5, detune=0.011, harmonics=5, bright=0.4)
    mix.add(at, voice * _env(n, 0.005, 0.12), gain, pan=-0.05)


def pad(mix: Mix, at: float, notes: list[int], gain: float = 0.09, length: float = 1.8) -> None:
    n = int(length * RATE)
    voice = np.zeros(n, dtype=np.float32)
    for note in notes:
        voice += supersaw(midi(note), n, voices=7, detune=0.016, harmonics=5, bright=0.32)
    mix.add(at, voice * _env(n, 0.45, 0.7), gain, pan=0.0)


def lead(mix: Mix, at: float, note: int, length: float, gain: float = 0.13) -> None:
    n = int(length * RATE)
    t = _t(n)
    phase = 2 * np.pi * midi(note) * t + 0.28 * np.sin(2 * np.pi * 5.6 * t)
    tone = (np.sin(phase) + 0.45 * np.sin(2 * phase) + 0.22 * np.sin(3 * phase)).astype(np.float32)
    shimmer = supersaw(midi(note), n, voices=3, detune=0.008, harmonics=3, bright=0.4) * 0.5
    mix.add(at, (tone + shimmer) * _env(n, 0.03, 0.2) * _decay(n, 1.6), gain=gain, pan=0.1)


def riser(mix: Mix, at: float, gain: float = 0.2, length: float = 2.0) -> None:
    n = int(length * RATE)
    noise = np.random.default_rng(29).normal(0, 1, n).astype(np.float32)
    noise = np.diff(noise, prepend=0.0)
    ramp = (np.linspace(0.0, 1.0, n, dtype=np.float32) ** 2.2)
    mix.add(at, noise * ramp, gain)


def impact(mix: Mix, at: float, gain: float = 0.42) -> None:
    n = int(1.0 * RATE)
    t = _t(n)
    body = np.sin(2 * np.pi * (85.0 - 45.0 * t) * t).astype(np.float32) * _decay(n, 3.6)
    air = np.random.default_rng(5).normal(0, 1, n).astype(np.float32) * np.exp(-16.0 * t)
    mix.add(at, body + air * 0.4, gain)


# ---------------------------------------------------------------------- score


def sidechain(n: int, kicks: list[float], depth: float = 0.55) -> np.ndarray:
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

    pad_bus = Mix(duration)
    chord_bus = Mix(duration)
    bass_bus = Mix(duration)
    lead_bus = Mix(duration)
    kicks: list[float] = []

    bar = 0
    t = 0.0
    while t < duration - 0.02:
        chord, root = CHORDS[bar % len(CHORDS)]
        level, style = context(t)

        # --- drums
        if style == "break":
            kick(mix, t, 0.7)
            kicks.append(t)
        elif style == "intro":
            if bar % 2 == 0:
                for at in (t, t + 2 * BEAT):
                    kick(mix, at, 0.8)
                    kicks.append(at)
        else:
            for beat in range(4):
                kick(mix, t + beat * BEAT, 0.85)
                kicks.append(t + beat * BEAT)

        if style in ("build", "main", "lift"):
            for beat in (1, 3):
                clap(mix, t + beat * BEAT, 0.3)
            for step in range(4):
                open_hat(mix, t + step * BEAT + BEAT / 2, 0.13 + 0.03 * level)
            if style == "lift":
                for step in range(16):
                    shaker(mix, t + step * SIXTEENTH, 0.032)
            if bar % 8 == 0:
                crash(mix, t, 0.18)

        if style == "break":
            # Drums drop to a heartbeat kick; the pad and lead carry it.
            kick(mix, t, 0.7)
            kicks.append(t)
            if bar % 4 == 3:
                riser(mix, t + 2 * BEAT, 0.16, length=2 * BEAT)

        # --- rolling bass
        if style in ("build", "main", "lift", "outro"):
            for step in range(16):
                note = root + ROLL[step]
                roll_bass(bass_bus, t + step * SIXTEENTH, note,
                          gain=(0.20 + 0.10 * level) * (1.0 if step % 4 == 0 else 0.85))
            for step in range(4):
                bass_pluck(bass_bus, t + step * BEAT + BEAT / 2, root + 24,
                           gain=0.05 + 0.03 * level)

        # --- chords and pads
        if style in ("build", "main", "lift"):
            for step in (0, 2):
                chord_stab(chord_bus, t + step * BEAT, chord, gain=0.10 + 0.06 * level)
        pad(pad_bus, t, chord, gain=0.07 + 0.04 * level, length=BAR + 0.2)

        # --- lead, only after the breakdown lifts
        if style == "lift":
            for offset, beat_at, note, beats in LEAD:
                if int(offset) == bar % 4:
                    lead(lead_bus, t + beat_at * BEAT, note, beats * BEAT, gain=0.12)

        if style == "outro" and bar == 0:
            crash(mix, t, 0.22)

        bar += 1
        t += BAR

    pump = sidechain(n, kicks, depth=0.6)
    pad_bus.buf *= pump[:, None]
    chord_bus.buf *= sidechain(n, kicks, depth=0.45)[:, None]

    # A dotted-eighth delay on the lead is half the genre.
    delay_len = int(BEAT * 0.75 * RATE)
    delayed = lead_bus.buf.copy()
    for tap, gain in ((1, 0.30), (2, 0.16), (3, 0.08)):
        shifted = tap * delay_len
        delayed[shifted:] += lead_bus.buf[:-shifted] * gain

    for bus, gain in ((pad_bus.buf, 1.0), (chord_bus.buf, 1.0), (bass_bus.buf, 1.0), (delayed, 1.0)):
        mix.buf += bus * gain

    return mix.buf
