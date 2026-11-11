"""Storyboard + voix horodatée -> « timeline » lue par le moteur de rendu (engine/player.js).

Tous les instants de la timeline sont absolus (secondes depuis le début de la vidéo).
Les éléments visuels apparaissent à l'instant où le mot correspondant est prononcé.
"""
from __future__ import annotations

from pathlib import Path

from . import align, schema, voice
from .config import segment_cfg, theme_vars

LEAD = 0.07          # l'image précède le mot de quelques centièmes : la synchro paraît plus nette
FICTIF = "Exemple fictif"


def _mono(xs: list[float], lo: float, hi: float, step: float = 0.14) -> list[float]:
    out, prev = [], lo - step
    for x in xs:
        x = min(max(x, prev + step), hi)
        out.append(round(x, 3)); prev = x
    return out


def build(story: dict, voices: list[dict], cfg: dict, media: dict | None = None, fictif: bool = False) -> dict:
    """Renvoie {timeline, voice_parts, sfx, duration, thumb_t, words}."""
    vcfg = cfg.get("video", {})
    media = media or {}
    gap = float(vcfg.get("scene_gap", 0.2))
    hold = float(vcfg.get("hold_end", 2.2))
    scenes_out, captions, sfx, parts = [], [], [], []
    t_audio = 0.05
    starts = []
    for res in voices:
        starts.append(t_audio)
        t_audio += res["dur"] + gap
    n = len(story["scenes"])
    for i, (sc, res) in enumerate(zip(story["scenes"], voices)):
        a0 = starts[i]
        a1 = a0 + res["dur"]
        t0 = 0.0 if i == 0 else round(a0 - 0.13, 3)
        t1 = round(starts[i + 1] - 0.13, 3) if i + 1 < n else round(a1 + hold, 3)
        _clean, toks, cues = align.parse_say(sc["say"])
        times = voice.word_times(toks, res)
        parts.append((a0, res["audio"]))

        def at(mark: str) -> float | None:
            return None if mark not in cues else a0 + max(0.0, times[cues[mark]][0] - LEAD)

        def clamp(x: float, lo_: float, hi_: float) -> float:
            return round(min(max(x, lo_), max(lo_, hi_)), 3)
        hl: set[int] = set()
        lo, hi = t0 + 0.3, t1 - 0.35
        o: dict = {"type": sc["type"], "t0": t0, "t1": t1}
        if i > 0:
            sfx.append((t0 - 0.2, "whoosh"))

        if sc["type"] == "resultat":
            o.update({"title": sc["title"], "public": sc["public"], "visuel": sc["visuel"]})
            p = at("public")
            o["publicAt"] = clamp(p if p is not None else t0 + (t1 - t0) * 0.45, t0 + 0.9, t1 - 0.8)
            if "public" in cues:
                hl.add(cues["public"])
            sfx += [(0.06, "thud"), (o["publicAt"], "pop")]

        elif sc["type"] == "etape":
            o.update({"n": sc["n"], "title": sc["title"]})
            blocks = []
            nb = len(sc["blocks"])
            for bi, b in enumerate(sc["blocks"]):
                sub = schema.sub_cues(b)
                marks = [at(f"{b['id']}{k + 1}") for k in range(sub)]
                b_at = at(b["id"])
                if b_at is None:
                    known = [x for x in marks if x is not None]
                    b_at = (known[0] - 0.4) if known else t0 + (t1 - t0) * (bi + 0.35) / (nb + 0.35)
                for m_ in [b["id"]] + [f"{b['id']}{k + 1}" for k in range(sub)]:
                    if m_ in cues:
                        hl.add(cues[m_])
                blocks.append((b, b_at, marks))
            # la pile se remplit de haut en bas : l'ordre du storyboard est celui de l'écran
            ats = _mono([x[1] for x in blocks], lo, hi - 0.4, 0.5)
            for k_, ((b, _, marks), b_at) in enumerate(zip(blocks, ats)):
                ob = {k: v for k, v in b.items() if k != "id"}
                ob["at"] = b_at
                nxt = ats[k_ + 1] if k_ + 1 < len(ats) else t1
                kind = b["kind"]
                if kind == "brief":
                    ob["dur"] = round(min(1.7, max(0.7, nxt - b_at - 0.5)), 3)
                    ob["hlAt"] = [None if m_ is None else clamp(m_, b_at + 0.3, t1 - 0.4) for m_ in marks]
                    sfx += [(b_at, "pop")] + [(b_at + 0.25 + 0.11 * q, "tick") for q in range(5)]
                elif kind == "code":
                    if b.get("hl"):
                        ob["hlAt"] = clamp(marks[0] if marks and marks[0] is not None else b_at + 0.4 + 0.16 * len(b["lines"]), b_at + 0.4, t1 - 0.4)
                        sfx.append((ob["hlAt"], "pop"))
                    sfx += [(b_at, "pop")] + [(b_at + 0.25 + 0.16 * q, "tick") for q in range(len(b["lines"]))]
                elif kind == "media":
                    sfx.append((b_at, "rise"))
                elif kind == "avant_apres":
                    ob["wipeAt"] = clamp(marks[0] if marks[0] is not None else b_at + 1.0, b_at + 0.6, t1 - 1.3)
                    sfx += [(b_at, "pop"), (ob["wipeAt"], "whoosh")]
                elif kind == "erreur":
                    ob["zoneAt"] = clamp(marks[0] if marks[0] is not None else b_at + 0.7, b_at + 0.45, t1 - 1.6)
                    if b.get("fix"):
                        ob["fixAt"] = clamp(marks[1] if len(marks) > 1 and marks[1] is not None else ob["zoneAt"] + 1.5, ob["zoneAt"] + 0.9, t1 - 0.8)
                        sfx.append((ob["fixAt"] + 0.1, "ding"))
                    z = (media.get(b["ref"]) or {}).get("zone")
                    if z:
                        ob["zone"] = z
                    sfx += [(b_at, "pop"), (ob["zoneAt"], "thud")]
                elif marks:
                    filled, prev = [], b_at
                    for k, r in enumerate(marks):
                        r = r if r is not None else prev + (0.3 if k else 0.26)
                        filled.append(r); prev = r
                    ob["rowAt" if kind in ("checklist", "compare") else "itemAt"] = _mono(filled, b_at + 0.16, t1 - 0.25, 0.14)
                    sfx += [(b_at, "pop")] + [(r + 0.1, "tick") for r in ob.get("rowAt") or ob.get("itemAt")]
                else:
                    sfx.append((b_at, "rise" if kind == "stat" else "pop"))
                    if kind == "terminal":
                        sfx += [(b_at + 0.3 + 0.09 * q, "tick") for q in range(4)]
                o.setdefault("blocks", []).append(ob)

        elif sc["type"] == "verif":
            o.update({k: sc.get(k) for k in ("title", "rows", "limite", "source", "visuel") if sc.get(k)})
            rows = [at(f"r{k + 1}") for k in range(len(sc["rows"]))]
            filled, prev = [], t0 + 0.2
            for k, r in enumerate(rows):
                r = r if r is not None else prev + (t1 - t0 - 2.4) / (len(rows) + 0.5)
                filled.append(r); prev = r
                if f"r{k + 1}" in cues:
                    hl.add(cues[f"r{k + 1}"])
            o["rowAt"] = _mono(filled, t0 + 0.45, t1 - 1.9, 0.3)
            lim = at("limite")
            o["limiteAt"] = clamp(lim if lim is not None else t1 - 2.0, o["rowAt"][-1] + 0.4, t1 - 0.9)
            if "limite" in cues:
                hl.add(cues["limite"])
            if sc.get("source"):
                s_ = at("source")
                o["sourceAt"] = clamp(s_ if s_ is not None else o["limiteAt"] + 0.6, o["limiteAt"] + 0.3, t1 - 0.5)
            sfx += [(r + 0.1, "tick") for r in o["rowAt"]] + [(o["limiteAt"], "pop")]

        else:  # cta — texte imposé
            kw_word = sc["keyword"]
            o.update({"keyword": kw_word, "verb": sc.get("verb", "Commente"), "l2": sc.get("l2", ""), "l3": sc.get("l3", "")})
            # le mot-clé s'écrit à l'instant exact où il est prononcé
            idx = next((k for k, t in enumerate(toks) if align.norm(kw_word) and align.norm(kw_word) == align.norm(t)), None)
            if idx is None:
                idx = next((k for k, t in enumerate(toks) if align.norm(kw_word) and align.norm(kw_word) in align.norm(t)), None)
            kw_end = None
            if idx is not None:
                kw = a0 + times[idx][0] - LEAD
                kw_end = a0 + times[idx][1]
                hl.add(idx)
            else:
                kw = a0 + res["dur"] * 0.2
            o["kwAt"] = clamp(kw, t0 + 0.5, t1 - 2.0)
            nxt_word = a0 + times[idx + 1][0] - LEAD if idx is not None and idx + 1 < len(toks) else o["kwAt"] + 0.5
            o["l2At"] = clamp(nxt_word, o["kwAt"] + 0.3, t1 - 1.6)
            sub = at("sub")
            o["subAt"] = clamp(sub if sub is not None else o["l2At"] + 0.9, o["l2At"] + 0.4, t1 - 1.2)
            # le « ding » (1,3–2,6 kHz, en pleine zone de la parole) attend que le mot-clé soit fini d'être prononcé
            ding = o["kwAt"] + 0.25 if kw_end is None else max(o["kwAt"] + 0.25, kw_end + 0.05)
            sfx.append((round(min(ding, t1 - 0.75), 3), "ding"))
            sfx += [(o["kwAt"] + 0.05 * q, "tick") for q in range(min(6, len(kw_word)))]

        scenes_out.append(o)
        captions += align.group_captions(toks, times, hl, a0)

    # les sous-titres ne se chevauchent jamais
    for g, nxt in zip(captions, captions[1:]):
        g["t1"] = round(min(g["t1"], nxt["t0"] - 0.02), 3)
    duration = scenes_out[-1]["t1"]
    seg = story.get("segment", "createur_freelance")
    tl = {"fps": int(vcfg.get("fps", 30)), "duration": round(duration, 3), "theme": theme_vars(cfg, seg), "scenes": scenes_out,
          "captions": captions, "media": media, "serie": str(segment_cfg(cfg, seg).get("serie") or "").strip(),
          "fictif": FICTIF if fictif else ""}
    av = ((cfg.get("brand") or {}).get("avatar") or "").strip()
    if av:
        p = Path(av) if Path(av).is_absolute() else Path(cfg.get("_root", ".")) / av
        if p.exists():
            tl["avatar"] = p.resolve().as_uri()
    first = scenes_out[0]
    return {"timeline": tl, "voice_parts": parts, "sfx": sorted(sfx), "duration": duration,
            "thumb_t": round(max(0.5, first["t1"] - 0.45), 2),
            "words": sum(len(align.parse_say(s["say"])[1]) for s in story["scenes"])}
