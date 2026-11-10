"""Mix the demo soundtrack in four stems, per the Murch hierarchy.

Order of precedence: dialogue, story sounds, music, effects, ambience. Each
stem yields to the one above it, which in practice means the voice ducks
everything else and the story sounds get out of the way of consonants.

Space is synthesised rather than recorded: a decaying-noise impulse response
convolved over the music and voice buses.
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
PEAK_CEILING = 0.74


# --------------------------------------------------------------------- space


def impulse_response(seconds: float = 1.6, decay: float = 4.2, seed: int = 7) -> tuple[np.ndarray, np.ndarray]:
    """Decaying noise with early reflections. Cheap stand-in for a real room."""
    n = int(seconds * RATE)
    rng = np.random.default_rng(seed)
    t = np.arange(n) / RATE
    shape = np.exp(-decay * t)
    left = rng.normal(0, 1, n) * shape
    right = rng.normal(0, 1, n) * shape
    # Early reflections: a few discrete taps, panned, so it reads as a room.
    for delay, gain, pan in ((0.011, 0.5, -0.4), (0.019, 0.35, 0.5), (0.031, 0.28, -0.2), (0.047, 0.2, 0.3)):
        i = int(delay * RATE)
        left[i] += gain * (1 - pan) / 2
        right[i] += gain * (1 + pan) / 2
    left /= np.max(np.abs(left)) or 1.0
    right /= np.max(np.abs(right)) or 1.0
    return left.astype(np.float32), right.astype(np.float32)


def _convolve(signal: np.ndarray, ir: np.ndarray) -> np.ndarray:
    n = len(signal) + len(ir) - 1
    size = 1 << (n - 1).bit_length()
    spec = np.fft.rfft(signal, size) * np.fft.rfft(ir, size)
    return np.fft.irfft(spec, size)[: len(signal)].astype(np.float32)


def reverb(bus: np.ndarray, ir: tuple[np.ndarray, np.ndarray], wet: float) -> np.ndarray:
    if wet <= 0:
        return bus
    left = _convolve(bus[:, 0], ir[0])
    right = _convolve(bus[:, 1], ir[1])
    wet_bus = np.stack([left, right], axis=1)
    return bus * (1.0 - wet * 0.35) + wet_bus * wet


# --------------------------------------------------------------------- stems


def ambience(n: int, level: float = 0.012) -> np.ndarray:
    """Low room tone with a slow wander, so the mix has a floor."""
    rng = np.random.default_rng(41)
    noise = rng.normal(0, 1, n).astype(np.float32)
    # Brown-ish: cumulative sum with leak, then a gentle smoothing pass.
    brown = np.cumsum(noise) / 60.0
    brown -= np.linspace(brown[0], brown[-1], n, dtype=np.float32)
    width = 480
    cumulative = np.cumsum(brown, dtype=np.float64)
    smooth = ((cumulative[width:] - cumulative[:-width]) / width).astype(np.float32)
    smooth = np.pad(smooth, (0, n - smooth.shape[0]), mode="edge")
    wander = 1.0 + 0.25 * np.sin(2 * np.pi * 0.07 * np.arange(n) / RATE).astype(np.float32)
    mono = smooth * wander * level
    return np.stack([mono, mono * 0.96], axis=1)



def _set_rms(stem: np.ndarray, target_db: float) -> np.ndarray:
    """Normalise a stem to a measured RMS target, in dBFS."""
    rms = float(np.sqrt((stem ** 2).mean()))
    if rms < 1e-9:
        return stem
    return (stem * (10.0 ** (target_db / 20.0) / rms)).astype(np.float32)



def _set_active_rms(stem: np.ndarray, target_db: float, floor: float = 0.02) -> np.ndarray:
    """Normalise on the part of the stem that actually has content.

    Sparse stems (a handful of hits in 66 seconds) cannot be normalised over the
    whole timeline: the silence pulls the average down and each hit is boosted
    into a spike.
    """
    mono = np.abs(stem).max(axis=1)
    if mono.max() <= 0:
        return stem
    mask = mono > mono.max() * floor
    active = stem[mask]
    rms = float(np.sqrt((active ** 2).mean())) if active.size else 0.0
    if rms < 1e-9:
        return stem
    return (stem * (10.0 ** (target_db / 20.0) / rms)).astype(np.float32)


def _smooth(signal: np.ndarray, attack: float = 0.02, release: float = 0.25) -> np.ndarray:
    out = np.zeros_like(signal)
    a = 1.0 - math.exp(-1.0 / (attack * RATE))
    r = 1.0 - math.exp(-1.0 / (release * RATE))
    level = 0.0
    for index, value in enumerate(signal):
        coefficient = a if value > level else r
        level += coefficient * (value - level)
        out[index] = level
    return out


def _place(target: np.ndarray, at: float, signal: np.ndarray, gain: float, pan: float = 0.0) -> None:
    i = int(at * RATE)
    if i < 0 or i >= target.shape[0]:
        return
    j = min(target.shape[0], i + signal.shape[0])
    chunk = signal[: j - i] * gain
    target[i:j, 0] += chunk * math.sqrt(max(0.0, 0.5 * (1 - pan)))
    target[i:j, 1] += chunk * math.sqrt(max(0.0, 0.5 * (1 + pan)))


def tick(seconds: float = 0.09, freq: float = 1760.0) -> np.ndarray:
    n = int(seconds * RATE)
    t = np.arange(n) / RATE
    env = np.exp(-26.0 * t).astype(np.float32)
    tone = (np.sin(2 * np.pi * freq * t) + 0.4 * np.sin(2 * np.pi * freq * 1.5 * t)).astype(np.float32)
    return tone * env


def click() -> np.ndarray:
    n = int(0.035 * RATE)
    noise = np.random.default_rng(3).normal(0, 1, n).astype(np.float32)
    noise = np.diff(noise, prepend=0.0)
    return noise * np.exp(-90.0 * np.arange(n) / RATE).astype(np.float32)


def thud() -> np.ndarray:
    n = int(0.5 * RATE)
    t = np.arange(n) / RATE
    body = np.sin(2 * np.pi * (72.0 - 38.0 * t) * t).astype(np.float32) * np.exp(-6.0 * t)
    air = np.random.default_rng(9).normal(0, 1, n).astype(np.float32) * np.exp(-20.0 * t) * 0.3
    return (body + air).astype(np.float32)


def whoosh(seconds: float = 0.38) -> np.ndarray:
    n = int(seconds * RATE)
    noise = np.random.default_rng(13).normal(0, 1, n).astype(np.float32)
    noise = np.diff(noise, prepend=0.0)
    ramp = np.clip(np.sin(np.linspace(0, np.pi, n, dtype=np.float32)), 0.0, None) ** 1.4
    return (noise * ramp).astype(np.float32)


# ---------------------------------------------------------------------- mix


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
    n = int(duration * RATE)

    plan = cues.get("plan") or [(s, s + span, 0.8, "main") for s, (_n, span) in zip(starts, scenes)]
    music = make_music.render(duration, plan)

    # Story sounds: the six rows, the typed command, the zero, the transitions.
    effects = np.zeros((n, 2), dtype=np.float32)
    for moment in cues.get("rows", ()):
        _place(effects, float(moment), tick(), 0.42, pan=0.15)
    for index, moment in enumerate(cues.get("keys", ())):
        _place(effects, float(moment), click(), 0.5, pan=(-0.1, 0.1)[index % 2])
    for moment in cues.get("marks", ()):
        _place(effects, float(moment), thud(), 0.55)
    for start in starts[1:]:
        _place(effects, max(0.0, start - 0.2), whoosh(), 0.22, pan=-0.2)

    voice = None
    lines = cues.get("voice") or []
    if lines:
        voice, placed = make_vo.track(lines, duration)
        for text, at, span in placed:
            print(f"  dialogue {at:5.1f}s  {span:4.1f}s  {text}")

    room = ambience(n)

    ir = impulse_response()
    music = reverb(music, ir, 0.07)
    effects = reverb(effects, ir, 0.05)
    # Voice stays dry: narration in a wet room reads as an effect, not a person.

    # Targets from the brief: dialogue sits over the bed, ambience is a floor
    # rather than a layer you notice.
    stems = {
        "voice": _set_active_rms(voice, -12.0) if voice is not None else np.zeros((n, 2), dtype=np.float32),
        "effects": _set_active_rms(effects, -20.0),
        "music": _set_rms(music, -19.0),
        "ambience": _set_rms(room, -36.0),
    }

    # Hierarchy last: the voice ducks everything under it, and nothing may
    # re-normalise the bed afterwards or the ducking is undone.
    if voice is not None:
        envelope = _smooth(np.abs(voice).max(axis=1), attack=0.01, release=0.18)
        peak = float(envelope.max()) or 1.0
        # Scale to 35 percent of the voice's own peak so quiet phrases still
        # pull the bed down, then clamp so the duck is decisive.
        duck = np.clip(envelope / (0.35 * peak), 0.0, 1.0)[:, None]
        stems["music"] = stems["music"] * (1.0 - 0.90 * duck)
        stems["ambience"] = stems["ambience"] * (1.0 - 0.50 * duck)
        stems["effects"] = stems["effects"] * (1.0 - 0.25 * duck)

    # Evidence that the hierarchy actually holds: measure the bed inside each
    # dialogue window, not in the gap after it.
    for text, at, span in (placed[:3] if lines else []):
        i = int(at * RATE)
        j = min(n, int((at + span) * RATE))
        voice_rms = float(np.sqrt((stems["voice"][i:j] ** 2).mean()))
        bed_rms = float(np.sqrt((stems["music"][i:j] ** 2).mean()))
        print(
            f"  inside dialogue at {at:5.1f}s: voice {20 * np.log10(max(voice_rms, 1e-9)):6.1f} dBFS"
            f" / music {20 * np.log10(max(bed_rms, 1e-9)):6.1f} dBFS"
            f" ({20 * np.log10(max(voice_rms, 1e-9) / max(bed_rms, 1e-9)):+.1f} dB)"
        )

    mix = np.zeros((n, 2), dtype=np.float32)
    for name, stem in stems.items():
        mix += stem
        print(f"  stem {name:9s} rms {20 * np.log10(max(float(np.sqrt((stem ** 2).mean())), 1e-9)):6.1f} dBFS")

    # Master: remove DC, soft limit, then measure rather than assume.
    mix -= mix.mean(axis=0, keepdims=True)
    mix = np.tanh(mix * 1.15)
    peak = float(np.max(np.abs(mix))) or 1.0
    mix = mix / peak * PEAK_CEILING

    target = out or (Path(tempfile.gettempdir()) / "opencode" / "demo-audio.wav")
    target.parent.mkdir(parents=True, exist_ok=True)
    pcm = (mix.astype(np.float32) * 32767.0).astype("<i2")
    with wave.open(str(target), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        handle.writeframes(pcm.tobytes())

    rms = float(np.sqrt((mix ** 2).mean()))
    print(f"  master peak {peak * PEAK_CEILING / peak:.2f} (limited) rms {20 * np.log10(max(rms, 1e-9)):.1f} dBFS")
    return target
