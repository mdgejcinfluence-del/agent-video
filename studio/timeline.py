"""Storyboard + voix horodatée -> « timeline » lue par le moteur de rendu (engine/player.js).

Tous les instants de la timeline sont absolus (secondes depuis le début de la vidéo).
Les éléments visuels apparaissent à l'instant où le mot correspondant est prononcé.
"""
from __future__ import annotations

from pathlib import Path

from . import align, voice
from .config import theme_vars

LEAD = 0.07          # l'image précède le mot de quelques centièmes : la synchro paraît plus nette
ICON_CYCLE = ["bulb", "gear", "rocket", "chart", "bolt", "pencil", "play"]


def _mono(xs: list[float], lo: float, hi: float, step: float = 0.14) -> list[float]:
    out, prev = [], lo - step
    for x in xs:
        x = min(max(x, prev + step), hi)
        out.append(round(x, 3)); prev = x
    return out


def build(story: dict, voices: list[dict], cfg: dict) -> dict:
    """Renvoie {timeline, voice_parts, sfx, duration, thumb_t, words}."""
    vcfg = cfg.get("video", {})
    gap = float(vcfg.get("scene_gap", 0.2))
    hold = float(vcfg.get("hold_end", 1.7))
    scenes_out, captions, sfx, parts = [], [], [], []
    icons: list[str | None] = []
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
        hl: set[int] = set()
        lo, hi = t0 + 0.3, t1 - 0.35
        o: dict = {"type": sc["type"], "t0": t0, "t1": t1}
        if i > 0:
            sfx.append((t0 - 0.2, "whoosh"))

        if sc["type"] == "hook":
            o.update({k: sc.get(k) for k in ("title", "kicker", "chips", "stamp", "pill") if sc.get(k)})
            dur = t1 - t0
            c = {"chips": at("chips") if at("chips") is not None else t0 + 0.5}
            if sc.get("stamp"):
                c["stamp"] = at("stamp") if at("stamp") is not None else t0 + dur * 0.5
                sfx.append((c["stamp"] + 0.05, "thud"))
            if sc.get("pill"):
                c["pill"] = at("pill") if at("pill") is not None else t0 + dur * 0.8
                sfx.append((c["pill"], "pop"))
            for j in range(len(sc.get("chips") or [])):
                sfx.append((c["chips"] + j * 0.1, "tick"))
            o["cues"] = {k: round(min(max(v, t0 + 0.2), hi), 3) for k, v in c.items()}
            hl |= {cues[m] for m in ("stamp", "pill") if m in cues and sc.get(m)}
            o["icon"] = sc.get("icon") or "star"

        elif sc["type"] == "section":
            o.update({"n": sc.get("n"), "title": sc["title"]})
            o["icon"] = sc.get("icon") or ICON_CYCLE[(sc.get("n") or i) % len(ICON_CYCLE)]
            blocks = []
            nb = len(sc["blocks"])
            for bi, b in enumerate(sc["blocks"]):
                nb_rows = len(b.get("rows") or b.get("items") or [])
                row_marks = [at(f"{b['id']}{k + 1}") for k in range(nb_rows)]
                b_at = at(b["id"])
                if b_at is None:
                    known = [x for x in row_marks if x is not None]
                    b_at = (known[0] - 0.22) if known else t0 + (t1 - t0) * (bi + 0.6) / (nb + 0.6)
                if b["id"] in cues:
                    hl.add(cues[b["id"]])
                for k in range(nb_rows):
                    if f"{b['id']}{k + 1}" in cues:
                        hl.add(cues[f"{b['id']}{k + 1}"])
                blocks.append((b, b_at, row_marks))
            # la pile se remplit de haut en bas dans l'ordre où la voix cite les blocs
            blocks.sort(key=lambda x: x[1])
            ats = _mono([x[1] for x in blocks], lo, hi, 0.3)
            for (b, _, row_marks), b_at in zip(blocks, ats):
                ob = {k: v for k, v in b.items() if k != "id"}
                ob["at"] = b_at
                nb_rows = len(row_marks)
                if nb_rows:
                    filled, prev = [], b_at
                    for k, r in enumerate(row_marks):
                        r = r if r is not None else prev + (0.3 if k else 0.26)
                        filled.append(r); prev = r
                    key = "rowAt" if b["kind"] in ("checklist", "compare") else "itemAt"
                    ob[key] = _mono(filled, b_at + 0.16, t1 - 0.25, 0.14)
                    for r in ob[key]:
                        sfx.append((r + 0.1, "tick"))
                sfx.append((b_at, "rise" if b["kind"] == "stat" else "pop"))
                if b["kind"] == "terminal":
                    sfx += [(b_at + 0.3 + 0.09 * q, "tick") for q in range(4)]
                blocks_out = ob
                o.setdefault("blocks", []).append(blocks_out)

        else:  # cta
            o.update({"keyword": sc["keyword"], "sub": sc.get("sub"), "verb": sc.get("verb", "Commente")})
            # le mot-clé s'écrit à l'instant exact où il est prononcé (prioritaire sur le repère [kw])
            idx = next((k for k, t in enumerate(toks) if align.norm(sc["keyword"]) and align.norm(sc["keyword"]) in align.norm(t)), None)
            kw_end = None
            if idx is not None:
                kw = a0 + times[idx][0] - LEAD
                kw_end = a0 + times[idx][1]
                hl.add(idx)
            elif at("kw") is not None:
                kw = at("kw"); hl.add(cues["kw"])
            else:
                kw = a0 + res["dur"] * 0.5
            o["kwAt"] = round(min(max(kw, t0 + 0.6), t1 - 1.0), 3)
            sub = at("sub")
            o["subAt"] = round(min(max(sub if sub is not None else o["kwAt"] + 0.9, o["kwAt"] + 0.5), t1 - 0.8), 3)
            # le « ding » (1,3–2,6 kHz, en pleine zone de la parole) attend que le mot-clé soit fini d'être prononcé
            ding = o["kwAt"] + 0.25 if kw_end is None else max(o["kwAt"] + 0.25, kw_end + 0.05)
            sfx.append((round(min(ding, t1 - 0.75), 3), "ding"))
            sfx += [(o["kwAt"] + 0.05 * q, "tick") for q in range(min(6, len(sc["keyword"])))]

        icons.append(o.get("icon"))
        scenes_out.append(o)
        captions += align.group_captions(toks, times, hl, a0)

    # les sous-titres ne se chevauchent jamais
    for g, nxt in zip(captions, captions[1:]):
        g["t1"] = round(min(g["t1"], nxt["t0"] - 0.02), 3)
    duration = scenes_out[-1]["t1"]
    tl = {"fps": int(vcfg.get("fps", 30)), "duration": round(duration, 3), "theme": theme_vars(cfg), "scenes": scenes_out,
          "captions": captions, "mascot": {"icons": [x for x in icons[:-1]]}}
    av = ((cfg.get("brand") or {}).get("avatar") or "").strip()
    if av:
        p = Path(av) if Path(av).is_absolute() else Path(cfg.get("_root", ".")) / av
        if p.exists():
            tl["avatar"] = p.resolve().as_uri()
    hook = scenes_out[0]
    return {"timeline": tl, "voice_parts": parts, "sfx": sorted(sfx), "duration": duration,
            "thumb_t": round(max(0.5, hook["t1"] - 0.45), 2),
            "words": sum(len(align.parse_say(s["say"])[1]) for s in story["scenes"])}
