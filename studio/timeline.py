"""Storyboard + voix horodatée -> « timeline » lue par le moteur de rendu (engine/player.js).

Tous les instants sont absolus (secondes depuis le début de la vidéo). Chaque élément visuel apparaît à
l'instant où le mot correspondant est prononcé ; sans repère dans le texte, les éléments d'un bloc sont
répartis sur le temps qui reste dans l'écran.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import align, schema, voice
from .config import theme_vars

LEAD = 0.07          # l'image précède le mot de quelques centièmes : la synchro paraît plus nette


def _mono(xs: list[float], lo: float, hi: float, step: float = 0.16) -> list[float]:
    out, prev = [], lo - step
    for x in xs:
        x = min(max(x, prev + step), max(hi, prev + step))
        out.append(round(x, 3)); prev = x
    return out


def avatar(cfg: dict) -> dict:
    root = Path(cfg.get("_root", "."))
    d = root / "engine" / "avatar"
    p = d / "poses.json"
    poses = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    return {"base": d.resolve().as_uri() + "/", "poses": poses}


def build(story: dict, voices: list[dict], cfg: dict) -> dict:
    """Renvoie {timeline, voice_parts, sfx, duration, thumb_t, words, rushs: {ref: durée à l'écran}}."""
    vcfg = cfg.get("video", {})
    gap = float(vcfg.get("scene_gap", 0.16))
    hold = float(vcfg.get("hold_end", 2.0))
    scenes_out, captions, sfx, parts = [], [], [], []
    rushs: dict[str, dict] = {}
    t_audio = 0.04
    starts = []
    for res in voices:
        starts.append(t_audio)
        t_audio += res["dur"] + gap
    n = len(story["scenes"])
    for i, (sc, res) in enumerate(zip(story["scenes"], voices)):
        a0 = starts[i]
        a1 = a0 + res["dur"]
        t0 = 0.0 if i == 0 else round(a0 - 0.1, 3)
        t1 = round(starts[i + 1] - 0.1, 3) if i + 1 < n else round(a1 + hold, 3)
        _clean, toks, cues = align.parse_say(sc["say"])
        times = voice.word_times(toks, res)
        parts.append((a0, res["audio"]))

        def at(mark: str) -> float | None:
            return None if mark not in cues else a0 + max(0.0, times[cues[mark]][0] - LEAD)

        def clamp(x: float, lo_: float, hi_: float) -> float:
            return round(min(max(x, lo_), max(lo_, hi_)), 3)
        o: dict = {"type": sc["type"], "t0": t0, "t1": t1}
        if i > 0:
            sfx.append((t0 - 0.12, "whoosh"))

        if sc["type"] == "fin":
            kw = sc["keyword"]

            def idx_of(word: str, start: int = 0) -> int | None:
                w = align.norm(word)
                return next((k for k in range(start, len(toks)) if w and w in align.norm(toks[k])), None)
            i_ab, i_co = idx_of("abonne"), idx_of("commente")
            i_kw = idx_of(kw, (i_co or 0))
            click = a0 + times[i_ab][1] + 0.12 if i_ab is not None else t0 + 0.9
            o["clickAt"] = clamp(click, t0 + 0.75, t1 - 2.2)
            o["boxAt"] = clamp(a0 + times[i_co][0] - 0.1 if i_co is not None else o["clickAt"] + 0.5, o["clickAt"] + 0.25, t1 - 2.0)
            k_at = a0 + times[i_kw][0] - LEAD if i_kw is not None else o["boxAt"] + 0.5
            o["kwAt"] = clamp(k_at, o["boxAt"] + 0.25, t1 - 1.6)
            k_end = a0 + times[i_kw][1] if i_kw is not None else o["kwAt"] + 0.5
            o.update({"keyword": kw, "pose": sc.get("pose") or "pouce"})
            if sc.get("promesse"):
                o["promesse"] = sc["promesse"]
                pr = at("p")
                o["promesseAt"] = clamp(pr if pr is not None else k_end + 0.25, o["kwAt"] + 0.45, t1 - 1.2)
            if sc.get("promo"):
                o["promo"] = sc["promo"]
                pm = at("promo")
                o["promoAt"] = clamp(pm if pm is not None else (o.get("promesseAt") or o["kwAt"]) + 0.9, (o.get("promesseAt") or o["kwAt"]) + 0.4, t1 - 0.8)
            sfx += [(t0, "rise"), (o["clickAt"], "tick"), (o["boxAt"], "pop"), (round(min(max(o["kwAt"] + 0.25, k_end + 0.05), t1 - 0.7), 3), "ding")]
            sfx += [(o["kwAt"] + 0.05 * q, "tick") for q in range(min(6, len(kw)))]
        else:
            o.update({"title": sc["title"], "pose": sc.get("pose") or "presente", "blocks": []})
            lo = t0 + 0.25
            if sc.get("tuile"):
                o["tuile"] = {**sc["tuile"], "at": round(t0 + 0.08, 3)}
                o["titleAt"] = round(t0 + 1.05, 3)
                o["poseAt"] = round(t0 + 0.85, 3)
                lo = t0 + 1.5
                sfx += [(t0 + 0.08, "thud"), (t0 + 0.85, "whoosh")]
            else:
                o["titleAt"] = round(t0 + 0.1, 3)
                o["poseAt"] = round(t0 + 0.12, 3)
                if i == 0:
                    sfx.append((0.05, "thud"))
            hi = t1 - 0.5
            blocks = sc.get("blocks") or []
            nb = len(blocks)
            raw = []
            for bi, b in enumerate(blocks):
                sub = schema.sub_cues(b)
                marks = [at(f"{b['id']}{k + 1}") for k in range(sub)]
                b_at = at(b["id"])
                if b_at is None:
                    known = [x for x in marks if x is not None]
                    b_at = (known[0] - 0.35) if known else lo + (hi - lo) * (bi + 0.25) / (nb + 0.6)
                raw.append((b, b_at, marks))
            ats = _mono([x[1] for x in raw], lo, hi - 0.6, 0.6)
            if i == 0 and ats:
                ats[0] = 0.0          # première image de la vidéo : le premier bloc est déjà là (rien à attendre pour comprendre)
            for k_, ((b, _, marks), b_at) in enumerate(zip(raw, ats)):
                ob = {k: v for k, v in b.items() if k not in ("id", "q", "voir")}
                ob["at"] = b_at
                nxt = ats[k_ + 1] if k_ + 1 < len(ats) else t1
                kind = b["kind"]

                def spread(count: int, first: float, last: float, step: float = 0.42) -> list[float]:
                    """Instants des éléments : le repère s'il existe, sinon régulièrement à partir du bloc."""
                    filled, prev = [], first - step
                    for q in range(count):
                        m_ = marks[q] if q < len(marks) else None
                        x = m_ if m_ is not None else prev + min(step, max(0.2, (last - first) / max(1, count)))
                        filled.append(x); prev = x
                    return _mono(filled, first, last, 0.16)
                if kind in ("liste", "check", "icones"):
                    ob["itemAt"] = spread(len(b["items"]), b_at + 0.1, min(nxt, t1) - 0.3)
                    sfx += [(x, "tick" if kind != "icones" else "pop") for x in ob["itemAt"]]
                elif kind == "cartes":
                    ob["cardAt"] = spread(2, b_at, min(nxt, t1) - 0.9, 0.9)
                    ob["noteAt"] = [x + 0.55 for x in ob["cardAt"]]
                    sfx += [(x, "pop") for x in ob["cardAt"]]
                elif kind == "fenetre":
                    q = spread(2 if b.get("reponse") else 1, b_at + 0.45, min(nxt, t1) - 1.0, 1.3)
                    ob["qAt"] = q[0]
                    if b.get("reponse"):
                        ob["rAt"] = max(q[1], q[0] + 0.9)
                    sfx += [(b_at, "pop")] + [(ob["qAt"] + 0.09 * z, "tick") for z in range(5)]
                elif kind == "mot":
                    if b.get("sous"):
                        ob["sousAt"] = clamp(marks[0] if marks and marks[0] is not None else b_at + 0.5, b_at + 0.3, t1 - 0.3)
                    sfx.append((b_at, "thud"))
                elif kind == "avant_apres":
                    ne = len(b.get("effets") or [])
                    w_at = marks[0] if marks and marks[0] is not None else b_at + 1.3
                    ob["wipeAt"] = clamp(w_at, b_at + 0.9, t1 - 1.2 - 0.35 * ne)
                    fx, prev = [], ob["wipeAt"] + 0.35
                    for q in range(ne):
                        m_ = marks[q + 1] if q + 1 < len(marks) else None
                        x = m_ if m_ is not None else prev + min(0.55, max(0.3, (t1 - 0.6 - ob["wipeAt"]) / (ne + 1)))
                        fx.append(x); prev = x
                    ob["fxAt"] = _mono(fx, ob["wipeAt"] + 0.5, t1 - 0.5, 0.28)
                    sfx += [(b_at, "pop"), (ob["wipeAt"], "whoosh")] + [(x, "pop") for x in ob["fxAt"]]
                    rushs[b["ref"]] = {"duree": round(t1 - b_at + 0.4, 2), "cadre": b.get("cadre") or "portrait"}
                elif kind == "rush":
                    sfx.append((b_at, "rise"))
                    rushs[b["ref"]] = {"duree": round(t1 - b_at + 0.4, 2), "cadre": b.get("cadre") or "portrait"}
                else:
                    sfx.append((b_at, "pop"))
                o["blocks"].append(ob)

        scenes_out.append(o)
        captions += align.group_captions(toks, times, set(), a0, max_words=3, max_chars=22)

    # les sous-titres ne se chevauchent jamais
    for g, nxt in zip(captions, captions[1:]):
        g["t1"] = round(min(g["t1"], nxt["t0"] - 0.02), 3)
    for g in captions:
        for w in g["words"]:
            w["w"] = w["w"].strip(" ,;:.!?…«»\"()").strip("\u00a0") or w["w"]
            w.pop("hl", None)
    duration = scenes_out[-1]["t1"]
    brand = cfg.get("brand") or {}
    tl = {"fps": int(vcfg.get("fps", 30)), "duration": round(duration, 3), "theme": theme_vars(cfg), "scenes": scenes_out,
          "captions": captions, "media": {}, "avatar": avatar(cfg), "mention": str(brand.get("mention_fin") or "").strip(),
          "handle": str(brand.get("handle") or "").strip(),
          "cover": {"lines": story.get("couverture") or [], "pose": (story.get("scenes") or [{}])[0].get("pose") or "pointe"}}
    first = scenes_out[0]
    return {"timeline": tl, "voice_parts": parts, "sfx": sorted(sfx), "duration": duration, "rushs": rushs,
            "thumb_t": round(max(0.5, first["t1"] - 0.4), 2),
            "words": sum(len(align.parse_say(s["say"])[1]) for s in story["scenes"])}
