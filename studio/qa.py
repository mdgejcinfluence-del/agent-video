"""Contrôle qualité automatique d'une vidéo terminée (aucun humain dans la boucle).

Une vidéo qui échoue à un contrôle bloquant n'est pas publiée.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import numpy as np


def probe(path: str | Path) -> dict:
    r = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
                       capture_output=True, text=True, check=True)
    d = json.loads(r.stdout)
    v = next((s for s in d["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in d["streams"] if s["codec_type"] == "audio"), None)
    num, den = (v["r_frame_rate"].split("/") + ["1"])[:2] if v else ("0", "1")
    return {"duration": float(d["format"]["duration"]), "size": int(d["format"]["size"]),
            "width": v and v["width"], "height": v and v["height"], "fps": float(num) / float(den or 1) if v else 0,
            "vcodec": v and v["codec_name"], "pix_fmt": v and v.get("pix_fmt"), "acodec": a and a["codec_name"],
            "audio_rate": a and int(a["sample_rate"]), "channels": a and a["channels"]}


def _frame(path: Path, t: float) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", str(path), "-frames:v", "1", "-vf", "scale=108:192",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.uint8).reshape(192, 108, 3).astype(np.float32)


def check(video: str | Path, timeline: dict, layout: dict | None = None, audio_info: dict | None = None,
          target_lufs: float = -14.0, seconds: tuple[float, float] | None = None) -> dict:
    video = Path(video)
    problems, warnings = [], []
    p = probe(video)
    if (p["width"], p["height"]) != (1080, 1920):
        problems.append(f"format {p['width']}x{p['height']} au lieu de 1080x1920")
    if abs(p["fps"] - timeline.get("fps", 30)) > 0.01:
        problems.append(f"cadence {p['fps']} img/s")
    if abs(p["duration"] - timeline["duration"]) > 0.3:
        problems.append(f"durée {p['duration']:.2f} s, attendue {timeline['duration']:.2f} s")
    if not p["acodec"]:
        problems.append("pas de piste audio")
    if p["vcodec"] != "h264" or p["pix_fmt"] != "yuv420p":
        problems.append(f"codec {p['vcodec']}/{p['pix_fmt']} (attendu h264/yuv420p)")
    if not 5 <= p["duration"] <= 90:
        problems.append(f"durée {p['duration']:.1f} s hors limites des Reels (5–90 s)")
    if seconds:
        lo, hi = seconds
        if not lo - 7 <= p["duration"] <= hi + 10:
            problems.append(f"durée {p['duration']:.1f} s trop éloignée du format visé ({lo:g}–{hi:g} s)")
        elif not lo <= p["duration"] <= hi:
            warnings.append(f"durée {p['duration']:.1f} s hors du format visé ({lo:g}–{hi:g} s)")
    # le résultat doit être à l'image dès la première seconde, et la preuve doit être lisible
    sc = timeline.get("scenes") or []
    if sc and (sc[0].get("type") != "resultat" or not sc[0].get("visuel")):
        problems.append("la première image ne montre pas le résultat produit")
    if sc and not timeline.get("media"):
        problems.append("aucun média de preuve dans la vidéo")
    if p["size"] > 100 * 1024 * 1024:
        problems.append("fichier de plus de 100 Mo")
    # images : ni vides ni figées
    ts = [0.4] + [timeline["duration"] * k / 6 for k in range(1, 6)] + [timeline["duration"] - 0.4]
    frames = [_frame(video, t) for t in ts]
    if min(float(f.std()) for f in frames) < 3:
        problems.append("au moins une image est vide (unie)")
    diffs = [float(np.abs(a - b).mean()) for a, b in zip(frames, frames[1:])]
    if max(diffs) < 0.8:
        problems.append("l'image ne change pas : rendu figé")
    # sous-titres
    caps = timeline.get("captions", [])
    if not caps:
        problems.append("aucun sous-titre")
    bad = [g for g in caps if g["t1"] <= g["t0"] or g["t0"] < 0 or g["t1"] > timeline["duration"] + 0.01]
    if bad:
        problems.append(f"{len(bad)} sous-titre(s) avec un horodatage incohérent")
    for g, nxt in zip(caps, caps[1:]):
        if nxt["t0"] < g["t1"] - 0.001:
            problems.append("sous-titres qui se chevauchent"); break
    for w in (layout or {}).get("warnings", []):
        m = re.search(r"réduit(?:e)? à (\d+) %", w)
        blocking = "déborde" in w or "descend sous" in w or (m and int(m.group(1)) < 78)      # sous 78 %, le texte n'est plus lisible sur téléphone
        (problems if blocking else warnings).append("mise en page : " + w)
    if audio_info and audio_info.get("lufs") is not None:
        try:
            if abs(float(audio_info["lufs"]) - target_lufs) > 2.0:
                warnings.append(f"niveau sonore {audio_info['lufs']} LUFS (cible {target_lufs})")
        except (TypeError, ValueError):
            pass
    # voix / fond sonore : seuils tirés d'un essai (11/11/2026) — la reconnaissance vocale restait stable de 24 à 12 dB
    # de marge et se dégradait nettement à 0 dB. Personne n'écoute la vidéo avant publication : on garde de la marge.
    cl = (audio_info or {}).get("clarte_db")
    if cl is not None:
        if cl < 6:
            problems.append(f"voix couverte par le fond sonore (marge {cl} dB entre 1 et 4 kHz, minimum 6)")
        elif cl < 12:
            warnings.append(f"voix peu détachée du fond sonore (marge {cl} dB, conseillé : 12 ou plus)")
    return {"ok": not problems, "problems": problems, "warnings": warnings, "facts": p}
