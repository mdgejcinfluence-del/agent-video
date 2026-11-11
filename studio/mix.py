"""Mixage : voix + musique (qui s'efface sous la voix) + bruitages, puis mise au niveau « réseaux sociaux »."""
from __future__ import annotations

import json
import re
import subprocess
import wave
from pathlib import Path

import numpy as np

from . import music

SR = music.SR
SFX_DUCK = 0.5          # part retirée aux bruitages quand la voix parle (0,5 = -6 dB)


def _write_wav(path: Path, x: np.ndarray) -> None:
    x = np.clip(x, -1, 1)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(x.shape[1]); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((x * 32767).astype(np.int16).tobytes())


def _envelope(v: np.ndarray, hop_ms: int = 10, smooth: int = 22) -> np.ndarray:
    hop = SR * hop_ms // 1000
    n = len(v) // hop
    if n == 0:
        return np.zeros(len(v), dtype=np.float32)
    rms = np.sqrt(np.mean(v[: n * hop].reshape(n, hop) ** 2, axis=1))
    rms = np.convolve(rms, np.ones(smooth) / smooth, mode="same")
    return np.interp(np.arange(len(v)), np.arange(n) * hop + hop / 2, rms).astype(np.float32)


def _bande(x: np.ndarray, lo: float = 1000.0, hi: float = 4000.0) -> np.ndarray:
    """Ne garde que 1–4 kHz : la zone où se joue l'intelligibilité de la parole."""
    n = len(x)
    nfft = 1 << max(1, (n - 1).bit_length())
    spec = np.fft.rfft(x, nfft)
    f = np.fft.rfftfreq(nfft, 1 / SR)
    spec[(f < lo) | (f > hi)] = 0
    return np.fft.irfft(spec, nfft)[:n].astype(np.float32)


def clarity(voice: np.ndarray, fond: np.ndarray, win: float = 0.1) -> dict:
    """De combien la voix dépasse-t-elle le fond (musique + bruitages), entre 1 et 4 kHz, aux instants où elle parle ?

    Personne n'écoute la vidéo avant publication : cette mesure sert de garde-fou.
    Renvoie la marge médiane (dB), la marge du dixième des instants les moins favorables, et la part
    des instants parlés où le fond arrive à moins de 3 dB de la voix.
    """
    w = int(win * SR)
    k = len(voice) // w
    if k < 5:
        return {}
    b = fond.mean(axis=1) if fond.ndim == 2 else fond
    rv = np.sqrt(np.mean(_bande(voice)[: k * w].reshape(k, w) ** 2, axis=1))
    rb = np.sqrt(np.mean(_bande(b)[: k * w].reshape(k, w) ** 2, axis=1))
    if float(rv.max()) <= 0:
        return {}
    parle = rv > np.percentile(rv, 95) * 10 ** (-20 / 20)
    if not parle.any():
        return {}
    marge = 20 * np.log10(rv[parle] / np.maximum(rb[parle], 1e-7))
    return {"clarte_db": round(float(np.median(marge)), 1), "clarte_p10": round(float(np.percentile(marge, 10)), 1),
            "couvert": round(float(np.mean(marge < 3.0)), 3)}


def loudness(path: Path) -> dict:
    """Mesure EBU R128 (ffmpeg loudnorm, passe d'analyse)."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af",
                        "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"], capture_output=True, text=True)
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", r.stderr, flags=re.S)
    return json.loads(m.group(0)) if m else {}


def build(duration: float, voice_parts: list[tuple[float, np.ndarray]], cues: list[tuple[float, str]], cfg: dict,
          seed: int, out_wav: str | Path, log=print) -> dict:
    """Assemble la bande son finale (48 kHz stéréo). Renvoie des mesures."""
    acfg = cfg.get("audio", {})
    out_wav = Path(out_wav)
    n = int(duration * SR)
    voice = np.zeros(n, dtype=np.float32)
    for t, a in voice_parts:
        i = int(t * SR); m = min(len(a), n - i)
        if m > 0:
            voice[i:i + m] += a[:m]
    # voix : niveau homogène + limitation douce
    env = _envelope(voice)
    active = env > 0.02
    if active.any():
        voice *= (10 ** (-19 / 20)) / float(np.sqrt(np.mean(voice[active] ** 2)) + 1e-9)
    voice = np.tanh(voice * 1.25) / 1.25
    env = _envelope(voice)
    talk = np.clip(env / 0.03, 0, 1)                                                     # 1 quand la voix parle, 0 dans les silences
    fond = np.zeros((n, 2), dtype=np.float32)
    info = {"music": "aucune"}
    if acfg.get("music", True):
        bed, src = music.bed(duration, seed, Path(cfg.get("_root", ".")))
        info["music"] = src
        under = 10 ** (float(acfg.get("music_db", -27)) / 20) / (10 ** (-18 / 20))     # le lit est normalisé à -18 dBFS
        gaps = under * 10 ** (5 / 20)                                                    # +5 dB dans les silences
        fond += bed[:n] * (gaps + (under - gaps) * talk)[:, None]
    if acfg.get("sfx", True):
        bus = np.zeros((n, 2), dtype=np.float32)
        rng = np.random.default_rng(seed + 7)
        for i, (t, kind) in enumerate(cues):
            sig = music.sfx(kind, rng)
            g = music.SFX_GAIN.get(kind, 0.1)
            pan = 0.5 + ((i * 37) % 9 - 4) * 0.03
            music._put(bus, max(0.0, t), sig, g * (1 - pan) * 2, g * pan * 2)
        fond += bus * (1 - SFX_DUCK * talk)[:, None]                                     # les bruitages s'effacent aussi sous la voix
    # garde-fou : si le fond arrive trop près de la voix (musique personnelle trop dense, par exemple), on le baisse
    cl = clarity(voice, fond)
    cible = float(acfg.get("voice_margin_db", 14))
    if cl and cl["clarte_db"] < cible:
        baisse = min(40.0, cible - cl["clarte_db"])
        fond *= 10 ** (-baisse / 20)
        cl = clarity(voice, fond)
        cl["fond_baisse_db"] = round(baisse, 1)
    info.update(cl)
    mix = np.repeat(voice[:, None], 2, axis=1) + fond
    peak = float(np.max(np.abs(mix)) + 1e-9)
    if peak > 0.94:
        mix *= 0.94 / peak
    raw = out_wav.with_suffix(".raw.wav")
    _write_wav(raw, mix)
    # mise au niveau en deux passes (mesure, puis gain linéaire)
    target = float(acfg.get("loudness", -14))
    meas = loudness(raw)
    try:
        af = (f"loudnorm=I={target}:TP=-1.5:LRA=11:measured_I={meas['input_i']}:measured_TP={meas['input_tp']}:"
              f"measured_LRA={meas['input_lra']}:measured_thresh={meas['input_thresh']}:offset={meas['target_offset']}:linear=true")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(raw), "-af", af, "-ar", str(SR), "-ac", "2", str(out_wav)], check=True)
    except Exception as e:  # noqa: BLE001 — en dernier recours on garde le mix brut
        log(f"mise au niveau impossible ({e}) : mix brut conservé")
        raw.replace(out_wav)
    if raw.exists():
        raw.unlink()
    final = loudness(out_wav)
    info.update({"lufs_avant": meas.get("input_i"), "lufs": final.get("input_i"), "true_peak": final.get("input_tp")})
    return info
