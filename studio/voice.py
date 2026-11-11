"""Voix off : texte -> audio (48 kHz mono) + horodatage de chaque mot.

Deux moteurs, essayés dans l'ordre de config.yaml :
  * edge  : voix neuronales en ligne (paquet edge-tts). Gratuit, sans clé, donne l'instant
            exact de chaque mot. Service NON officiel : il peut s'arrêter sans préavis.
  * piper : synthèse 100 % locale (hors ligne, illimitée). Voix plus « robot », sert de secours.
"""
from __future__ import annotations

import asyncio
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

from . import align

SR = 48000


def decode(path: str | Path) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


def pronounce(text: str, table: dict | None) -> str:
    for shown, said in (table or {}).items():
        text = re.sub(rf"(?<![\w-]){re.escape(shown)}(?![\w-])", said, text, flags=re.IGNORECASE)
    return text


def stress(text: str, word: str | None) -> str:
    """Isole le mot-clé à l'oral en l'entourant de guillemets : la voix marque une micro-pause avant lui.

    Sans cela, « Commente GRATUIT » s'enchaîne d'un trait et s'entend « commande gratuit »
    (vérifié par reconnaissance vocale le 11/11/2026). Le texte affiché, lui, ne change pas.
    """
    word = (word or "").strip()
    if not word:
        return text
    pat = rf"(?:[«\"“]\s*)?(?<![\w-]){re.escape(word)}(?![\w-])(?:\s*[»\"”])?"
    out, n = re.subn(pat, f"« {word} »", text)
    if n:
        return out
    hits = list(re.finditer(pat, text, flags=re.IGNORECASE))       # écrit en minuscules : on isole la dernière occurrence
    if not hits:
        return text
    m = hits[-1]
    return text[:m.start()] + f"« {word} »" + text[m.end():]


# --------------------------------------------------------------------------- edge
async def _edge_async(text: str, voice: str, rate: str, pitch: str, mp3: Path) -> list[dict]:
    import edge_tts
    try:
        com = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, boundary="WordBoundary")
    except TypeError:                      # anciennes versions : repères de mots envoyés par défaut
        com = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    words: list[dict] = []
    with open(mp3, "wb") as f:
        async for ch in com.stream():
            if ch["type"] == "audio":
                f.write(ch["data"])
            elif ch["type"] == "WordBoundary":
                t0 = ch["offset"] / 1e7
                words.append({"w": ch["text"], "t0": t0, "t1": t0 + ch["duration"] / 1e7})
    return words


def edge(text: str, vcfg: dict) -> tuple[np.ndarray, list[dict]]:
    with tempfile.TemporaryDirectory() as td:
        mp3 = Path(td) / "v.mp3"
        words = asyncio.run(_edge_async(text, vcfg.get("edge_voice", "fr-FR-HenriNeural"), vcfg.get("rate", "+0%"),
                                        vcfg.get("pitch", "+0Hz"), mp3))
        if not mp3.exists() or mp3.stat().st_size < 800:
            raise RuntimeError("edge-tts n'a renvoyé aucun son")
        return decode(mp3), words


# --------------------------------------------------------------------------- piper
def piper(text: str, vcfg: dict, root: Path) -> tuple[np.ndarray, list[dict]]:
    voice = vcfg.get("piper_voice", "fr_FR-siwis-medium")
    data = root / ".voices"; data.mkdir(exist_ok=True)
    if not (data / f"{voice}.onnx").exists():
        subprocess.run([sys.executable, "-m", "piper.download_voices", voice, "--data-dir", str(data)],
                       check=True, capture_output=True, timeout=600)
    with tempfile.TemporaryDirectory() as td:
        wav = Path(td) / "v.wav"
        rate = vcfg.get("rate", "+0%")
        m = re.match(r"([+-]\d+)%", rate)
        scale = 1.0 / (1.0 + int(m.group(1)) / 100.0) if m else 1.0
        subprocess.run([sys.executable, "-m", "piper", "-m", voice, "--data-dir", str(data), "-f", str(wav),
                        "--length-scale", f"{scale:.3f}"], input=text.encode("utf-8"), check=True, capture_output=True, timeout=600)
        return decode(wav), []


# --------------------------------------------------------------------------- gemini (optionnel)
def gemini(text: str, vcfg: dict) -> tuple[np.ndarray, list[dict]]:
    """Voix de l'API Gemini (clé gratuite Google AI Studio). API officielle, mais limitée en débit sur le palier gratuit.

    Écrit d'après la documentation Google ; NON TESTÉ sans clé. Ne fournit pas l'instant de chaque mot :
    les sous-titres sont alors calés par estimation (moins précis qu'avec « edge »).
    """
    import base64
    import os

    import requests
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY absente")
    model = vcfg.get("gemini_model", "gemini-2.5-flash-preview-tts")
    body = {"contents": [{"parts": [{"text": vcfg.get("gemini_style", "Dis ceci d'un ton dynamique et naturel : ") + text}]}],
            "generationConfig": {"responseModalities": ["AUDIO"],
                                 "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": vcfg.get("gemini_voice", "Charon")}}}}}
    r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent", params={"key": key}, json=body, timeout=120)
    if not r.ok:
        raise RuntimeError(f"Gemini TTS : HTTP {r.status_code} {r.text[:160]}")
    part = r.json()["candidates"][0]["content"]["parts"][0]["inlineData"]
    rate = int(re.search(r"rate=(\d+)", part.get("mimeType", "")).group(1)) if "rate=" in part.get("mimeType", "") else 24000
    pcm = np.frombuffer(base64.b64decode(part["data"]), dtype="<i2").astype(np.float32) / 32768.0
    n = int(len(pcm) * SR / rate)
    return np.interp(np.linspace(0, len(pcm) - 1, n), np.arange(len(pcm)), pcm).astype(np.float32), []


# --------------------------------------------------------------------------- outils
def _voiced_bounds(x: np.ndarray, thr_db: float = -42.0) -> tuple[float, float]:
    """Début et fin de la parole (en s) d'après l'énergie."""
    if len(x) == 0:
        return 0.0, 0.0
    hop = SR // 100
    n = len(x) // hop
    if n == 0:
        return 0.0, len(x) / SR
    rms = np.sqrt(np.mean(x[: n * hop].reshape(n, hop) ** 2, axis=1) + 1e-12)
    on = np.where(20 * np.log10(rms) > thr_db)[0]
    if len(on) == 0:
        return 0.0, len(x) / SR
    return on[0] * hop / SR, (on[-1] + 1) * hop / SR


def tighten(x: np.ndarray, words: list[dict], max_gap: float, lead: float = 0.03, tail: float = 0.10) -> tuple[np.ndarray, list[dict]]:
    """Raccourcit les silences (début, fin, pauses) pour un débit soutenu ; décale les horodatages."""
    if not words:
        a, b = _voiced_bounds(x)
        return x[int(max(0, a - lead) * SR): int(min(len(x) / SR, b + tail) * SR)], words
    end = len(x) / SR
    cuts: list[tuple[float, float]] = []
    if words[0]["t0"] > lead + 0.01:
        cuts.append((0.0, words[0]["t0"] - lead))
    for a, b in zip(words, words[1:]):
        gap = b["t0"] - a["t1"]
        if gap > max_gap + 0.04:
            mid, rem = (a["t1"] + b["t0"]) / 2, gap - max_gap
            cuts.append((mid - rem / 2, mid + rem / 2))
    _, voiced_end = _voiced_bounds(x)
    last = max(words[-1]["t1"], min(voiced_end, words[-1]["t1"] + 0.5))
    if end - last > tail + 0.01:
        cuts.append((last + tail, end))
    if not cuts:
        return x, words
    fade = int(0.004 * SR)
    ramp = np.linspace(0, 1, fade, dtype=np.float32)
    parts, pos = [], 0.0
    for c0, c1 in cuts:
        seg = x[int(pos * SR): int(c0 * SR)].copy()
        if len(seg) > 2 * fade:
            seg[:fade] *= ramp; seg[-fade:] *= ramp[::-1]
        parts.append(seg); pos = c1
    seg = x[int(pos * SR):].copy()
    if len(seg) > 2 * fade:
        seg[:fade] *= ramp; seg[-fade:] *= ramp[::-1]
    parts.append(seg)

    def shift(t: float) -> float:
        return t - sum(min(c1, t) - c0 for c0, c1 in cuts if c0 < t)
    new = [{"w": w["w"], "t0": shift(w["t0"]), "t1": shift(w["t1"])} for w in words]
    return np.concatenate(parts), new


def speak(say_clean: str, cfg: dict, log=print, stress_word: str | None = None) -> dict:
    """Synthétise une scène. Renvoie {audio, dur, words, provider}. `stress_word` : mot à détacher à l'oral (mot-clé)."""
    vcfg = cfg.get("voice", {})
    text = re.sub(r"(?<=\d)[ \u00a0\u202f](?=\d{3}(?!\d))", "", say_clean.replace("*", ""))   # « 68 000 » -> « 68000 » pour la voix
    text = stress(text, stress_word)
    text = pronounce(text, vcfg.get("pronounce"))
    root = Path(cfg.get("_root", "."))
    errors = []
    for prov in vcfg.get("order", ["edge", "piper"]):
        for attempt in range(3 if prov == "edge" else 1):
            try:
                audio, words = edge(text, vcfg) if prov == "edge" else gemini(text, vcfg) if prov == "gemini" else piper(text, vcfg, root)
                if len(audio) < SR * 0.3:
                    raise RuntimeError("audio trop court")
                audio, words = tighten(audio, words, float(vcfg.get("max_gap", 0.26)))
                peak = float(np.max(np.abs(audio))) or 1.0
                audio = (audio / peak * 0.9).astype(np.float32)
                return {"audio": audio, "dur": len(audio) / SR, "words": words, "provider": prov}
            except Exception as e:  # noqa: BLE001 — on passe au moteur suivant
                errors.append(f"{prov}#{attempt + 1}: {type(e).__name__}: {str(e)[:160]}")
                if prov == "edge":
                    import time
                    time.sleep(1.5 * (attempt + 1))
    raise RuntimeError("aucun moteur de voix n'a fonctionné : " + " | ".join(errors))


def word_times(toks: list[str], res: dict) -> list[tuple[float, float]]:
    if res["words"]:
        return align.map_times(toks, res["words"], res["dur"])
    return align.estimate_times(toks, res["dur"])
