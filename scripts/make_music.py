"""A Tron-ish score: analog saw stacks, 16th pulse, gated snares, sidechain.

The reference is Daft Punk's Tron: Legacy rather than disco: minor progression,
pulsing filtered arpeggio, wide detuned pads, big gated snare, and a mix that
breathes with the kick. All oscillators, so nothing to license.

Styles: intro, build, main, lift, break, outro.
"""

from __future__ import annotations

import math

import numpy as np

RATE = 44100
BPM = 120.0
BEAT = 60.0 / BPM
BAR = BEAT * 4

# D minor with a VI-VII turn: i, VI, III, VII, i, VI, iv, V.
CHORDS = [
    ([62, 65, 69], 38),   # Dm
    ([58, 62, 65], 34),   # Bb
    ([57, 60, 65], 41),   # F
    ([60, 64, 67], 36),   # C
    ([62, 65, 69], 38),   # Dm
    ([58, 62, 65], 34),   # Bb
    ([55, 58, 62], 43),   # Gm
    ([57, 61, 64], 33),   # A
]

# A four-bar phrase that resolves down, played on a saw lead in the lift.
MOTIF = [(0.0, 74, 1.5), (1.5, 72, 0.5), (2.0, 69, 1.0), (3.0, 67, 1.0),
         (4.0, 69, 1.5), (5.5, 67, 0.5), (6.0, 65, 2.0)]


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


# ---------------------------------------------------------------- oscillators


def saw_stack(freq: float, n: int, *, harmonics: int = 9, bright: float = 0.55,
              detune: float = 0.006) -> np.ndarray:
    """Additive saw with a controllable rolloff, two slightly detuned voices.

    `bright` sets the harmonic decay per sample, which is how the filter sweep
    is approximated without a stateful filter loop.
    """
    t = _t(n)
    out = np.zeros(n, dtype=np.float32)
    for voice, cents in ((1.0, 1.0), (1.0, 1.0 + detune), (1.0, 1.0 - detune)):
        for h in range(1, harmonics + 1):
            amp = (bright ** (h - 1)) / h
            if amp < 0.004:
                break
            out += (np.sin(2 * np.pi * freq * h * cents * t) * amp).astype(np.float32)
    return out / 3.0


def sweep_stack(freq: float, n: int, *, dark: float = 0.18, light: float = 0.72,
                rise: bool = True) -> np.ndarray:
    """Crossfade a dark and a bright version: a filter sweep in two passes."""
    curve = np.linspace(0.0, 1.0, n, dtype=np.float32)
    if not rise:
        curve = curve[::-1].copy()
    low = saw_stack(freq, n, bright=dark, harmonics=6)
    high = saw_stack(freq, n, bright=light, harmonics=11)
    return low * (1.0 - curve) + high * curve


# ------------------------------------------------------------------- elements


def kick(mix: Mix, at: float, gain: float = 0.95) -> None:
    n = int(0.24 * RATE)
    t = _t(n)
    body = np.sin(2 * np.pi * (110.0 - 72.0 * t / 0.24) * t).astype(np.float32)
    click = np.random.default_rng(3).normal(0, 1, n).astype(np.float32) * _decay(n, 260) * 0.3
    mix.add(at, (body * _decay(n, 16.0)) + click, gain)


def snare(mix: Mix, at: float, gain: float = 0.4, gated: bool = True) -> None:
    """Gated snare: the Tron signature. Noise, short body, delayed tail."""
    n = int(0.34 * RATE)
    noise = np.random.default_rng(int(at * 1300) + 5).normal(0, 1, n).astype(np.float32)
    noise = np.diff(noise, prepend=0.0)
    body = noise * _decay(n, 40.0)
    if not gated:
        mix.add(at, body, gain, pan=0.05)
        return
    tail = np.zeros(n, dtype=np.float32)
    offset = int(0.045 * RATE)
    tail[offset:] = noise[: n - offset] * _decay(n - offset, 9.0) * 0.55
    mix.add(at, body + tail, gain, pan=0.05)


def hat(mix: Mix, at: float, gain: float = 0.1, open_hat: bool = False) -> None:
    n = int((0.18 if open_hat else 0.045) * RATE)
    noise = np.random.default_rng(int(at * 9100) + 11).normal(0, 1, n).astype(np.float32)
    noise = np.diff(noise, prepend=0.0) * np.diff(noise, prepend=0.0)
    mix.add(at, noise * _decay(n, 110.0 if not open_hat else 22.0), gain, pan=0.28)


def tom(mix: Mix, at: float, note: float, gain: float = 0.3) -> None:
    n = int(0.26 * RATE)
    t = _t(n)
    body = np.sin(2 * np.pi * (note - note * 0.35 * t / 0.26) * t).astype(np.float32)
    mix.add(at, body * _decay(n, 13.0), gain, pan=-0.2)


def bass_pulse(mix: Mix, at: float, note: int, gain: float = 0.34, length: float = 0.19) -> None:
    n = int(length * RATE)
    tone = saw_stack(midi(note), n, harmonics=5, bright=0.35, detune=0.002)
    mix.add(at, tone * _env(n, 0.004, 0.1) * _decay(n, 4.0), gain)


def arp(mix: Mix, at: float, note: int, gain: float = 0.12, pan: float = 0.0, ring: float = 0.14) -> None:
    n = int(ring * RATE)
    tone = sweep_stack(midi(note), n, dark=0.3, light=0.62, rise=False)
    mix.add(at, tone * _decay(n, 22.0), gain, pan=pan)


def pad(mix: Mix, at: float, notes: list[int], gain: float = 0.1, length: float = 2.2) -> None:
    n = int(length * RATE)
    voice = np.zeros(n, dtype=np.float32)
    for index, note in enumerate(notes):
        voice += saw_stack(midi(note), n, harmonics=5, bright=0.3, detune=0.004) * (0.6 - index * 0.1)
    mix.add(at, voice * _env(n, 0.5, 0.8), gain, pan=-0.05)


def lead(mix: Mix, at: float, note: int, length: float, gain: float = 0.14) -> None:
    n = int(length * RATE)
    t = _t(n)
    phase = 2 * np.pi * midi(note) * t + 0.35 * np.sin(2 * np.pi * 5.2 * t)
    tone = (np.sin(phase) + 0.4 * np.sin(2 * phase) + 0.2 * np.sin(3 * phase)).astype(np.float32)
    mix.add(at, tone * _env(n, 0.03, 0.25) * _decay(n, 2.2), gain, pan=0.08)


def swell(mix: Mix, at: float, note: int, gain: float = 0.18, length: float = 2.2) -> None:
    """Orchestral-ish riser: stacked fifths and noise, opening up."""
    n = int(length * RATE)
    voice = np.zeros(n, dtype=np.float32)
    for interval, weight in ((0, 1.0), (7, 0.6), (12, 0.35)):
        voice += sweep_stack(midi(note + interval), n, dark=0.15, light=0.6, rise=True) * weight
    noise = np.random.default_rng(21).normal(0, 1, n).astype(np.float32) * 0.18
    ramp = np.linspace(0.0, 1.0, n, dtype=np.float32) ** 1.6
    mix.add(at, (voice + noise) * ramp * _env(n, 0.2, 0.05), gain)


def impact(mix: Mix, at: float, gain: float = 0.45) -> None:
    n = int(1.1 * RATE)
    t = _t(n)
    body = np.sin(2 * np.pi * (78.0 - 42.0 * t) * t).astype(np.float32) * _decay(n, 3.4)
    air = np.random.default_rng(5).normal(0, 1, n).astype(np.float32) * np.exp(-16.0 * t)
    mix.add(at, body + air * 0.4, gain)


# ------------------------------------------------------------------- effects


def delay(signal: np.ndarray, seconds: float, feedback: float = 0.32, taps: int = 3) -> np.ndarray:
    out = signal.copy()
    d = int(seconds * RATE)
    if d <= 0:
        return out
    for tap in range(1, taps + 1):
        gain = feedback ** tap
        shifted = int(tap * d)
        out[shifted:] += signal[:-shifted] * gain
    return out


def sidechain(n: int, kicks: list[float], depth: float = 0.55) -> np.ndarray:
    env = np.ones(n, dtype=np.float32)
    length = int(0.22 * RATE)
    curve = (1.0 - depth * np.exp(-np.arange(length) / (0.055 * RATE))).astype(np.float32)
    for at in kicks:
        i = int(at * RATE)
        if i >= n:
            continue
        j = min(n, i + length)
        env[i:j] = np.minimum(env[i:j], curve[: j - i])
    return env


# ---------------------------------------------------------------------- score


def render(duration: float, plan: list[tuple[float, float, float, str]]) -> np.ndarray:
    """plan: [(start, end, level, style)] covering the timeline in order."""
    mix = Mix(duration)
    n = mix.n

    def context(moment: float) -> tuple[float, str]:
        for start, end, level, style in plan:
            if start <= moment < end:
                return level, style
        return (plan[-1][2], plan[-1][3]) if plan else (0.7, "main")

    # Drums and pump are placed on a beat grid first, so the sidechain knows
    # exactly where the kicks are.
    kicks: list[float] = []
    bar = 0
    t = 0.0
    while t < duration - 0.05:
        level, style = context(t)
        if style in ("build", "main", "lift"):
            for beat in range(4):
                kicks.append(t + beat * BEAT)
        elif style == "break":
            kicks.extend([t, t + 2 * BEAT])
        elif style == "outro" and bar % 2 == 0:
            kicks.append(t)

        if style == "build":
            kick(mix, t, 0.5)
            kick(mix, t + BEAT, 0.5)
            snare(mix, t + 2 * BEAT, 0.2, gated=False)
        elif style in ("main", "lift"):
            for beat in range(4):
                kick(mix, t + beat * BEAT, 0.85)
            snare(mix, t + BEAT, 0.34)
            snare(mix, t + 3 * BEAT, 0.36)
            steps = 16 if style == "lift" else 8
            for step in range(steps):
                hat(mix, t + step * BEAT / (steps / 4), 0.055 + (0.02 if step % 2 else 0.0),
                    open_hat=(step == steps - 2))
            if bar % 8 == 7:
                for index in range(4):
                    tom(mix, t + 3 * BEAT + index * BEAT / 4, 190 - index * 18, 0.2)
        elif style == "break":
            kick(mix, t, 0.7)
            kick(mix, t + 2 * BEAT, 0.7)
            snare(mix, t + BEAT, 0.3)
            snare(mix, t + 3 * BEAT, 0.3)

        bar += 1
        t += BAR

    # Pads and bass, then the pump over the top of them.
    chord_bus = Mix(duration)
    bass_bus = Mix(duration)
    arp_bus = Mix(duration)
    lead_bus = Mix(duration)

    bar = 0
    t = 0.0
    while t < duration - 0.05:
        chord, root = CHORDS[bar % len(CHORDS)]
        level, style = context(t)

        pad(chord_bus, t, chord, gain=0.10 + 0.07 * level, length=BAR + 0.3)

        if style != "intro":
            for step in range(8):
                note = root + (12 if step % 4 == 3 else 0)
                bass_pulse(bass_bus, t + step * BEAT / 2, note,
                           gain=(0.26 + 0.12 * level) * (1.0 if step % 2 == 0 else 0.7))

        if style in ("build", "main", "lift"):
            steps = 16
            for step in range(steps):
                index = step % len(chord)
                note = chord[index] + (12 if step % 8 >= 4 else 0) + (12 if style == "lift" else 0)
                arp(arp_bus, t + step * BEAT / 4, note,
                    gain=0.075 + 0.045 * level, pan=(-0.4, 0.4)[step % 2],
                    ring=0.12 if style != "lift" else 0.1)

        if style == "lift":
            for beat_offset, note, length in MOTIF:
                if beat_offset < 4:
                    lead(lead_bus, t + beat_offset * BEAT, note, length * BEAT, gain=0.11)

        if style == "intro" and bar % 2 == 0:
            arp(arp_bus, t, chord[0] + 12, gain=0.05, ring=1.6)

        if style == "outro" and bar == 0:
            swell(mix, t, root + 12, gain=0.2, length=2.0)

        bar += 1
        t += BAR

    pump = sidechain(n, kicks, depth=0.6)
    arp_bus.buf *= pump[:, None]
    chord_bus.buf *= sidechain(n, kicks, depth=0.45)[:, None]

    lead_bus.buf = delay(lead_bus.buf, BEAT * 0.75, feedback=0.3, taps=3)
    arp_bus.buf = delay(arp_bus.buf, BEAT * 0.5, feedback=0.22, taps=2)

    for bus, gain in ((chord_bus, 1.0), (bass_bus, 1.0), (arp_bus, 0.9), (lead_bus, 1.0)):
        mix.buf += bus.buf * gain

    return mix.buf
