"""Chaîne de fabrication : storyboard -> contrôles -> rushs -> voix -> timeline -> son -> rendu -> contrôle qualité."""
from __future__ import annotations

import copy
import json
import re
import shutil
import time
import zlib
from pathlib import Path

from . import align, mix, qa, render, rushs, timeline, voice, writer


class RushIntrouvable(RuntimeError):
    """Aucune séquence filmée acceptable pour un passage : la vidéo n'est pas fabriquée (on ne maquille pas un manque)."""


def _rate(cfg: dict) -> float:
    m = re.match(r"([+-]?\d+)", str((cfg.get("voice") or {}).get("rate", "+0%")))
    return int(m.group(1)) / 100 if m else 0.0


def _speak_all(story: dict, cfg: dict, log) -> list[dict]:
    """Toute la vidéo est dite par UNE seule voix : si un écran a dû passer au moteur de secours, on réessaie le moteur
    principal pour cet écran ; s'il reste en panne, tous les écrans sont redits avec le moteur de secours."""
    def dire(sc, c):
        clean, _toks, _cues = align.parse_say(sc["say"])
        return voice.speak(clean, c, log, stress_word=story.get("keyword") if sc.get("type") == "fin" else None)
    out = [dire(sc, cfg) for sc in story["scenes"]]
    ordre = list((cfg.get("voice") or {}).get("order") or ["edge", "piper"])
    for _essai in range(2):
        autres = [i for i, v in enumerate(out) if v["provider"] != ordre[0]]
        if not autres:
            return out
        time.sleep(4)
        for i in autres:
            out[i] = dire(story["scenes"][i], cfg)
    autres = sorted({v["provider"] for v in out if v["provider"] != ordre[0]})
    if autres:
        secours = copy.deepcopy(cfg)
        secours.setdefault("voice", {})["order"] = [autres[0]]
        log(f"voix : le moteur « {ordre[0]} » ne répond pas pour tous les écrans — toute la vidéo est dite par « {autres[0]} » (une seule voix par vidéo)")
        out = [dire(sc, secours) for sc in story["scenes"]]
    return out


def _length(voices: list[dict], cfg: dict) -> float:
    v = cfg.get("video", {})
    return 0.04 + sum(x["dur"] for x in voices) + float(v.get("scene_gap", 0.16)) * (len(voices) - 1) + float(v.get("hold_end", 2.0))


def make_video(story: dict, cfg: dict, out_dir: str | Path, slug: str, log=print, workers: int | None = None,
               faits: dict | None = None, state=None, brain=None) -> dict:
    """Fabrique out_dir/slug.mp4 (+ .jpg couverture, + .json traçabilité). Renvoie un compte rendu.

    Le storyboard repasse ici par TOUS les contrôles (forme, garde-fous, écran de fin) : une vidéo qui les
    enfreint n'est pas rendue, d'où qu'elle vienne.
    """
    t_start = time.time()
    root = Path(cfg.get("_root", "."))
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    secs = tuple(cfg.get("video", {}).get("seconds", [38, 70]))
    story, _ = writer.controler(story, cfg, faits or {}, strict=True)
    seed = zlib.crc32(slug.encode()) % (2 ** 31)

    # 1. les séquences filmées : cherchées, téléchargées, contrôlées (format, netteté, cohérence avec la phrase)
    besoins = rushs.besoins_de(story)
    choix = rushs.choisir(besoins, cfg, state, brain, root, log)
    manque = [b for b in besoins if b["ref"] not in choix]
    if manque:
        raise RushIntrouvable("aucune séquence acceptable pour : " + " ; ".join(f"« {b['q']} » ({b['voir'][:50]})" for b in manque))

    # 2. la voix, puis ajustement du débit à la durée réellement mesurée (une seule reprise)
    vcfg = copy.deepcopy(cfg)
    voices = _speak_all(story, vcfg, log)
    total = _length(voices, cfg)
    rate0 = _rate(cfg)
    if not secs[0] <= total <= secs[1] and cfg.get("video", {}).get("ajuster_debit", True):
        cible = secs[1] - 0.6 if total > secs[1] else secs[0] + 0.6
        spoken = sum(x["dur"] for x in voices)
        k = spoken / max(1.0, spoken - (total - cible))                      # vitesse à appliquer à la parole seule
        rate1 = min(0.32, max(-0.05, (1 + rate0) * k - 1))
        if abs(rate1 - rate0) >= 0.02:
            vcfg.setdefault("voice", {})["rate"] = f"{rate1 * 100:+.0f}%"
            log(f"voix : {total:.1f} s au débit {rate0 * 100:+.0f} % — reprise au débit {rate1 * 100:+.0f} % pour viser {secs[0]}–{secs[1]} s")
            voices = _speak_all(story, vcfg, log)
            total = _length(voices, cfg)
    providers = sorted({v["provider"] for v in voices})
    log(f"voix : {len(voices)} écrans, {sum(v['dur'] for v in voices):.1f} s de parole, moteur {'+'.join(providers)}")

    # 3. la timeline, puis les séquences découpées à la durée exacte où elles restent à l'écran
    built = timeline.build(story, voices, cfg)
    tl = built["timeline"]
    seq_dir = out_dir / f".{slug}_rushs"
    for ref, need in built["rushs"].items():
        c = choix[ref]
        tl["media"][ref] = rushs.preparer(c["fichier"], need["cadre"], need["duree"], seq_dir / ref, fps=tl["fps"])
    layout = render.layout_report(tl)
    for w in layout.get("warnings", []):
        log(f"mise en page : {w}")

    wav = out_dir / f"{slug}.wav"
    audio = mix.build(built["duration"], built["voice_parts"], built["sfx"], cfg, seed, wav, log)
    log(f"son : {audio.get('lufs')} LUFS, crête {audio.get('true_peak')} dBTP, musique {audio.get('music')}, "
        f"voix {audio.get('clarte_db')} dB au-dessus du fond"
        + (f" (fond baissé de {audio['fond_baisse_db']} dB)" if audio.get("fond_baisse_db") else ""))

    mp4 = out_dir / f"{slug}.mp4"
    stats = render.render_video(tl, wav, mp4, workers=workers, log=log)
    thumb = out_dir / f"{slug}.jpg"
    render.still(tl, -1, thumb)                                             # la couverture dessinée (miniature)
    wav.unlink(missing_ok=True)

    report = qa.check(mp4, tl, layout, audio, float(cfg.get("audio", {}).get("loudness", -14)), seconds=secs)
    shutil.rmtree(seq_dir, ignore_errors=True)
    light = copy.deepcopy(tl)
    for m in light.get("media", {}).values():
        m.pop("dir", None)
    light.get("avatar", {}).pop("base", None)
    sources = {ref: {k: c.get(k) for k in ("id", "source", "page", "auteur", "licence", "controle", "mesures")} for ref, c in choix.items()}
    (out_dir / f"{slug}.json").write_text(json.dumps({"storyboard": story, "rushs": sources, "timeline": light}, ensure_ascii=False, indent=1), encoding="utf-8")
    scenes = [{"type": s["type"], "t0": s["t0"], "t1": s["t1"], "mots": len(align.parse_say(sc["say"])[1])}
              for s, sc in zip(tl["scenes"], story["scenes"])]
    out = {"video": str(mp4), "thumb": str(thumb), "thumb_ms": int(built["thumb_t"] * 1000), "duration": built["duration"],
           "words": built["words"], "voice": providers, "voice_rate": vcfg.get("voice", {}).get("rate"), "audio": audio, "render": stats,
           "qa": report, "story": story, "scenes": scenes, "layout": layout, "rushs": choix,
           "seconds_total": round(time.time() - t_start, 1)}
    log(f"vidéo : {mp4.name} — {built['duration']:.1f} s, {built['words']} mots, {len(choix)} séquence(s) filmée(s), {report['facts']['size'] / 1e6:.1f} Mo, "
        f"contrôle qualité {'OK' if report['ok'] else 'ÉCHEC : ' + '; '.join(report['problems'])}")
    return out
