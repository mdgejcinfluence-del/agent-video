"""Chaîne de fabrication : storyboard -> contrôles -> voix -> timeline -> son -> rendu -> contrôle qualité."""
from __future__ import annotations

import copy
import json
import re
import time
import zlib
from pathlib import Path

from . import align, mix, preuves, qa, render, schema, timeline, voice, writer


def _rate(cfg: dict) -> float:
    m = re.match(r"([+-]?\d+)", str((cfg.get("voice") or {}).get("rate", "+0%")))
    return int(m.group(1)) / 100 if m else 0.0


def _speak_all(story: dict, cfg: dict, log) -> list[dict]:
    out = []
    for sc in story["scenes"]:
        clean, _toks, _cues = align.parse_say(sc["say"])
        out.append(voice.speak(clean, cfg, log, stress_word=story.get("keyword") if sc.get("type") == "cta" else None))
    return out


def _length(voices: list[dict], cfg: dict) -> float:
    v = cfg.get("video", {})
    return 0.05 + sum(x["dur"] for x in voices) + float(v.get("scene_gap", 0.2)) * (len(voices) - 1) + float(v.get("hold_end", 2.2))


def make_video(story: dict, cfg: dict, out_dir: str | Path, slug: str, log=print, workers: int | None = None,
               pack: dict | None = None, faits: dict | None = None) -> dict:
    """Fabrique out_dir/slug.mp4 (+ .jpg couverture, + .json traçabilité). Renvoie un compte rendu.

    Le storyboard repasse ici par TOUS les contrôles (forme, phrase de fin, preuve, nombres, formulations) :
    une vidéo qui les enfreint n'est pas rendue, d'où qu'elle vienne.
    """
    t_start = time.time()
    root = Path(cfg.get("_root", "."))
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    secs = tuple(cfg.get("video", {}).get("seconds", [35, 45]))
    pack = pack or preuves.charger(root, story.get("preuve"))
    story, notes = writer.controler(story, cfg, pack, faits or {}, None)
    for n_ in notes:
        log(f"storyboard : {n_}")
    seed = zlib.crc32(slug.encode()) % (2 ** 31)
    media = preuves.medias(pack, root / ".cache" / "preuves", schema.refs_in(story))

    # voix, puis ajustement du débit à la durée réellement mesurée (une seule reprise)
    vcfg = copy.deepcopy(cfg)
    voices = _speak_all(story, vcfg, log)
    total = _length(voices, cfg)
    rate0 = _rate(cfg)
    if not secs[0] <= total <= secs[1] and cfg.get("video", {}).get("ajuster_debit", True):
        cible = secs[1] - 0.6 if total > secs[1] else secs[0] + 0.6
        spoken = sum(x["dur"] for x in voices)
        k = spoken / max(1.0, spoken - (total - cible))                      # vitesse à appliquer à la parole seule
        rate1 = min(0.30, max(-0.08, (1 + rate0) * k - 1))
        if abs(rate1 - rate0) >= 0.02:
            vcfg.setdefault("voice", {})["rate"] = f"{rate1 * 100:+.0f}%"
            log(f"voix : {total:.1f} s au débit {rate0 * 100:+.0f} % — reprise au débit {rate1 * 100:+.0f} % pour viser {secs[0]}–{secs[1]} s")
            voices = _speak_all(story, vcfg, log)
            total = _length(voices, cfg)
    providers = sorted({v["provider"] for v in voices})
    log(f"voix : {len(voices)} scènes, {sum(v['dur'] for v in voices):.1f} s de parole, moteur {'+'.join(providers)}")

    built = timeline.build(story, voices, cfg, media, fictif=bool(pack.get("fictif")))
    tl = built["timeline"]
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
    render.still(tl, built["thumb_t"], thumb)
    wav.unlink(missing_ok=True)

    report = qa.check(mp4, tl, layout, audio, float(cfg.get("audio", {}).get("loudness", -14)), seconds=secs)
    # traçabilité : le storyboard et la timeline, sans la liste des images de chaque rendu
    light = copy.deepcopy(tl)
    for m in light.get("media", {}).values():
        m["images"] = len(m.pop("srcs", []))
    (out_dir / f"{slug}.json").write_text(json.dumps({"storyboard": story, "timeline": light}, ensure_ascii=False, indent=1), encoding="utf-8")
    scenes = [{"type": s["type"], "t0": s["t0"], "t1": s["t1"], "mots": len(align.parse_say(sc["say"])[1])}
              for s, sc in zip(tl["scenes"], story["scenes"])]
    out = {"video": str(mp4), "thumb": str(thumb), "thumb_ms": int(built["thumb_t"] * 1000), "duration": built["duration"],
           "words": built["words"], "voice": providers, "voice_rate": vcfg.get("voice", {}).get("rate"), "audio": audio, "render": stats,
           "qa": report, "notes": notes, "story": story, "scenes": scenes, "layout": layout,
           "seconds_total": round(time.time() - t_start, 1)}
    log(f"vidéo : {mp4.name} — {built['duration']:.1f} s, {built['words']} mots, {report['facts']['size'] / 1e6:.1f} Mo, "
        f"contrôle qualité {'OK' if report['ok'] else 'ÉCHEC : ' + '; '.join(report['problems'])}")
    return out
