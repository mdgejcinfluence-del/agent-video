"""Musique de fond et bruitages, entièrement synthétisés (numpy).

Pourquoi synthétiser ? Zéro licence, zéro téléchargement, zéro risque de réclamation de droits
d'auteur, et une boucle différente à chaque vidéo (graine = identifiant de la vidéo).
Pour utiliser tes propres morceaux, dépose des .mp3/.wav dans assets/music/ : ils sont prioritaires.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np

SR = 48000
TAU = 2 * np.pi


def _mtof(m: float) -> float:
    return 440.0 * 2 ** ((m - 69) / 12)


def _band(x: np.ndarray, lo: float, hi: float) -> np.ndarray:
    X = np.fft.rfft(x); f = np.fft.rfftfreq(len(x), 1 / SR)
    X[(f < lo) | (f > hi)] = 0
    return np.fft.irfft(X, len(x)).astype(np.float32)


def _rel(x: np.ndarray, ms: float = 12) -> np.ndarray:
    n = min(len(x), int(SR * ms / 1000))
    if n > 1:
        x[-n:] *= np.linspace(1, 0, n, dtype=np.float32)
    return x


def keys(freq: float, dur: float) -> np.ndarray:
    """Timbre « piano électrique » doux (modulation de fréquence qui s'éteint)."""
    t = np.arange(int(dur * SR), dtype=np.float32) / SR
    mod = np.sin(TAU * freq * t) * (1.9 * np.exp(-t / 0.16) + 0.3)
    x = 0.72 * np.sin(TAU * freq * t + mod) + 0.22 * np.sin(TAU * 2 * freq * t) * np.exp(-t / 0.35)
    env = np.minimum(1, t / 0.007) * np.exp(-t / 0.9)
    return _rel((x * env).astype(np.float32), 30)


def bass(freq: float, dur: float) -> np.ndarray:
    t = np.arange(int(dur * SR), dtype=np.float32) / SR
    x = np.sin(TAU * freq * t + 0.4 * np.sin(TAU * freq * t)) + 0.15 * np.sin(TAU * 2 * freq * t)
    env = np.minimum(1, t / 0.008) * np.exp(-t / 0.55)
    return _rel((x * env).astype(np.float32), 25)


def kick() -> np.ndarray:
    t = np.arange(int(0.3 * SR), dtype=np.float32) / SR
    f = 44 + 100 * np.exp(-t / 0.032)
    x = np.sin(TAU * np.cumsum(f) / SR) * np.exp(-t / 0.15)
    return _rel(x.astype(np.float32), 20)


def snare(rng) -> np.ndarray:
    n = int(0.2 * SR); t = np.arange(n, dtype=np.float32) / SR
    nz = _band(rng.standard_normal(n).astype(np.float32), 1100, 8500)
    x = nz * np.exp(-t / 0.06) * 0.8 + np.sin(TAU * 190 * t) * np.exp(-t / 0.045) * 0.45
    return _rel(x.astype(np.float32), 10)


def hat(rng, open_: bool = False) -> np.ndarray:
    n = int((0.11 if open_ else 0.04) * SR); t = np.arange(n, dtype=np.float32) / SR
    nz = _band(rng.standard_normal(n).astype(np.float32), 7200, 16000)
    return _rel((nz * np.exp(-t / (0.035 if open_ else 0.011))).astype(np.float32), 4)


def _put(buf: np.ndarray, t: float, sig: np.ndarray, gl: float, gr: float | None = None) -> None:
    i = int(t * SR)
    if i >= len(buf) or i < 0:
        return
    n = min(len(sig), len(buf) - i)
    buf[i:i + n, 0] += sig[:n] * gl
    buf[i:i + n, 1] += sig[:n] * (gl if gr is None else gr)


PROGS = [[0, 8, 3, 10], [0, 5, 10, 3], [8, 10, 0, 0], [0, 7, 8, 10], [0, 3, 8, 7], [5, 0, 8, 10]]


def _chord(root: int, off: int) -> list[int]:
    r = root + off
    if off in (3, 8):
        iv = [0, 4, 7, 11]          # majeur 7
    elif off == 10:
        iv = [0, 4, 7, 9]           # sixte
    else:
        iv = [0, 3, 7, 10]          # mineur 7
    notes = [r + 12 + i for i in iv]
    return [n - 12 if n > 74 else n for n in notes]


def generate(duration: float, seed: int = 0) -> np.ndarray:
    """Boucle « lo-fi / chill » : accords, basse, batterie légère. Renvoie un tableau (n, 2)."""
    rng = np.random.default_rng(seed)
    bpm = int(rng.choice([82, 86, 90, 94]))
    root = int(rng.choice([45, 48, 50, 52, 43, 47]))
    prog = PROGS[int(rng.integers(len(PROGS)))]
    step = 60 / bpm / 4
    swing = 0.14 * step
    n = int((duration + 1.0) * SR)
    buf = np.zeros((n, 2), dtype=np.float32)
    k, s = kick(), snare(rng)
    hats = [hat(rng) for _ in range(4)]
    oh = hat(rng, True)
    chord_steps = [(0, 1.0), (6, 0.45), (10, 0.6)] if rng.random() < 0.5 else [(0, 1.0), (7, 0.5), (11, 0.45)]
    bass_steps = [(0, 1.0, 5), (7, 0.7, 2), (10, 0.8, 3)]
    bar = 0
    while bar * 16 * step < duration + 0.5:
        t0 = bar * 16 * step
        off = prog[bar % 4]
        notes = _chord(root, off)
        fill = (bar % 4 == 3)
        for st, vel in chord_steps:
            tt = t0 + st * step + (swing if st % 2 else 0)
            for j, m in enumerate(notes if st == 0 else notes[1:]):
                sig = keys(_mtof(m), step * (9 if st == 0 else 5))
                pan = 0.5 + (j - 1.5) * 0.14
                _put(buf, tt + j * 0.012, sig, 0.105 * vel * (1 - pan) * 2, 0.105 * vel * pan * 2)
        for st, vel, ln in bass_steps:
            _put(buf, t0 + st * step + (swing if st % 2 else 0), bass(_mtof(root + off - 12), step * ln), 0.34 * vel)
        for st in ([0, 10] + ([7] if bar % 2 else [])):
            _put(buf, t0 + st * step + (swing if st % 2 else 0), k, 0.6)
        for st in (4, 12):
            _put(buf, t0 + st * step, s, 0.2)
        for st in range(0, 16, 2):
            _put(buf, t0 + st * step, hats[st % 4], 0.085 if st % 4 == 0 else 0.055, 0.06 if st % 4 == 0 else 0.08)
        if fill:
            for st in (13, 14, 15):
                _put(buf, t0 + st * step, hats[st % 4], 0.05)
            _put(buf, t0 + 14 * step, oh, 0.05)
        bar += 1
    buf = buf[: int(duration * SR)]
    for c in range(2):                          # un peu de chaleur : on coupe l'extrême aigu
        buf[:, c] = _band(buf[:, c], 28, 11000)
    buf = np.tanh(buf * 1.4) / 1.4
    rms = float(np.sqrt(np.mean(buf ** 2)) + 1e-9)
    buf *= (10 ** (-18 / 20)) / rms
    fo = min(len(buf), int(1.4 * SR))
    buf[-fo:] *= np.linspace(1, 0, fo, dtype=np.float32)[:, None] ** 1.5
    return buf.astype(np.float32)


def from_file(path: Path, duration: float) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "2", "-ar", str(SR), "-"],
                         capture_output=True, check=True).stdout
    x = np.frombuffer(raw, dtype=np.float32).reshape(-1, 2).copy()
    n = int(duration * SR)
    if len(x) < n:
        x = np.tile(x, (n // max(1, len(x)) + 1, 1))
    x = x[:n]
    rms = float(np.sqrt(np.mean(x ** 2)) + 1e-9)
    x *= (10 ** (-18 / 20)) / rms
    fo = min(n, int(1.4 * SR))
    x[-fo:] *= np.linspace(1, 0, fo, dtype=np.float32)[:, None]
    return x


def bed(duration: float, seed: int, root: Path) -> tuple[np.ndarray, str]:
    files = sorted(p for p in (root / "assets" / "music").glob("*") if p.suffix.lower() in (".mp3", ".wav", ".m4a", ".ogg", ".flac"))
    if files:
        f = files[seed % len(files)]
        try:
            return from_file(f, duration), f"fichier:{f.name}"
        except Exception:  # noqa: BLE001 — fichier illisible : on synthétise
            pass
    return generate(duration, seed), "synthèse"


# --------------------------------------------------------------------------- bruitages
def sfx(kind: str, rng) -> np.ndarray:
    if kind == "pop":
        t = np.arange(int(0.09 * SR), dtype=np.float32) / SR
        f = 420 + 520 * (1 - np.exp(-t / 0.02))
        return _rel((np.sin(TAU * np.cumsum(f) / SR) * np.exp(-t / 0.028)).astype(np.float32), 5)
    if kind == "tick":
        t = np.arange(int(0.035 * SR), dtype=np.float32) / SR
        return _rel((np.sin(TAU * 1900 * t) * np.exp(-t / 0.007) * 0.7).astype(np.float32), 3)
    if kind == "thud":
        t = np.arange(int(0.22 * SR), dtype=np.float32) / SR
        x = np.sin(TAU * (70 + 60 * np.exp(-t / 0.03)) * t) * np.exp(-t / 0.07)
        x[: int(0.012 * SR)] += _band(rng.standard_normal(int(0.012 * SR)).astype(np.float32), 800, 6000) * 0.5
        return _rel(x.astype(np.float32), 10)
    if kind == "whoosh":
        n = int(0.34 * SR); t = np.arange(n, dtype=np.float32) / SR
        nz = rng.standard_normal(n).astype(np.float32)
        lo, hi = _band(nz, 300, 1800), _band(nz, 1800, 7000)
        mix = lo * (1 - t / t[-1]) + hi * (t / t[-1])
        env = np.exp(-((t - 0.19) / 0.085) ** 2)
        return (mix * env * 0.9).astype(np.float32)
    if kind == "ding":
        t = np.arange(int(0.7 * SR), dtype=np.float32) / SR
        x = (np.sin(TAU * 1318.5 * t) + 0.6 * np.sin(TAU * 1975.5 * t) + 0.3 * np.sin(TAU * 2637 * t)) * np.exp(-t / 0.2)
        return _rel((x * np.minimum(1, t / 0.004) * 0.5).astype(np.float32), 30)
    if kind == "rise":
        t = np.arange(int(0.5 * SR), dtype=np.float32) / SR
        f = 500 + 900 * (t / t[-1]) ** 2
        return _rel((np.sin(TAU * np.cumsum(f) / SR) * np.sin(np.pi * t / t[-1]) ** 2 * 0.5).astype(np.float32), 20)
    return np.zeros(1, dtype=np.float32)


SFX_GAIN = {"pop": 0.16, "tick": 0.09, "thud": 0.34, "whoosh": 0.13, "ding": 0.16, "rise": 0.07}
