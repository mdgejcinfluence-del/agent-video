"""Chaîne de fabrication : storyboard -> voix -> timeline -> son -> rendu -> contrôle qualité."""
from __future__ import annotations

import json
import time
import zlib
from pathlib import Path

from . import align, mix, qa, render, schema, timeline, voice


def make_video(story: dict, cfg: dict, out_dir: str | Path, slug: str, log=print, workers: int | None = None) -> dict:
    """Fabrique out_dir/slug.mp4 (+ .jpg miniature, + .json traçabilité). Renvoie un compte rendu."""
    t_start = time.time()
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    secs = tuple(cfg.get("video", {}).get("seconds", [28, 48]))
    story, notes = schema.check(story, secs)
    for n_ in notes:
        log(f"storyboard : {n_}")
    seed = zlib.crc32(slug.encode()) % (2 ** 31)

    voices = []
    for i, sc in enumerate(story["scenes"]):
        clean, _toks, _cues = align.parse_say(sc["say"])
        res = voice.speak(clean, cfg, log, stress_word=story.get("keyword") if sc.get("type") == "cta" else None)
        voices.append(res)
    providers = sorted({v["provider"] for v in voices})
    log(f"voix : {len(voices)} scènes, {sum(v['dur'] for v in voices):.1f} s, moteur {'+'.join(providers)}")

    built = timeline.build(story, voices, cfg)
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

    report = qa.check(mp4, tl, layout, audio, float(cfg.get("audio", {}).get("loudness", -14)))
    (out_dir / f"{slug}.json").write_text(json.dumps({"storyboard": story, "timeline": tl}, ensure_ascii=False, indent=1), encoding="utf-8")
    out = {"video": str(mp4), "thumb": str(thumb), "thumb_ms": int(built["thumb_t"] * 1000), "duration": built["duration"],
           "words": built["words"], "voice": providers, "audio": audio, "render": stats, "qa": report, "notes": notes,
           "story": story, "seconds_total": round(time.time() - t_start, 1)}
    log(f"vidéo : {mp4.name} — {built['duration']:.1f} s, {report['facts']['size'] / 1e6:.1f} Mo, "
        f"contrôle qualité {'OK' if report['ok'] else 'ÉCHEC : ' + '; '.join(report['problems'])}")
    return out
