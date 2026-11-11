"""Contrôle et réparation du storyboard écrit par le LLM.

Un modèle gratuit se trompe souvent sur la forme (texte trop long, repère inconnu, bloc en trop).
Plutôt que d'échouer, on répare ce qui est réparable (troncature, suppression) et on ne rejette
que ce qui rendrait la vidéo fausse ou vide. `check()` renvoie (storyboard propre, notes).
"""
from __future__ import annotations

import copy
import re

from .align import MARK, parse_say

ICONS = ["screen", "play", "pencil", "cursor", "bulb", "star", "bolt", "coin", "chat", "chart", "rocket", "check", "gear"]
KINDS = {"checklist", "compare", "stat", "pill", "terminal", "chips", "note"}
LIMITS = {"title": 36, "sec_title": 28, "chip": 22, "stamp": 14, "pill": 24, "kicker": 30, "row": 30, "label": 34,
          "unit": 18, "term": 36, "note": 90, "sub": 44, "keyword": 12, "item": 16}
WORDS_SCENE = 55
WORDS_TOTAL = (60, 190)


class StoryError(ValueError):
    pass


def plain(s) -> str:
    return re.sub(r"\s+", " ", str(s or "").replace("*", "")).strip()


def _cut(s, n: int, notes: list, what: str) -> str:
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    if len(plain(s)) <= n:
        return s
    words, out = s.split(), ""
    for w in words:
        if len(plain(out + " " + w)) > n:
            break
        out = (out + " " + w).strip()
    out = out or s[:n]
    if out.count("*") % 2:
        out = out.replace("*", "")
    notes.append(f"{what} raccourci : « {plain(s)[:40]}… »")
    return out.rstrip(" ,;:–-")


def block_height(b: dict) -> int:
    k = b["kind"]
    if k in ("checklist", "compare"):
        return 62 * len(b["rows"]) + (100 if b.get("label") else 64)
    return {"stat": 216 if b.get("label") else 180, "pill": 64, "terminal": 170, "chips": 86, "note": 190}[k]


def _strip_marks(say: str, keep: set[str]) -> str:
    return MARK.sub(lambda m: m.group(0) if m.group(1) in keep else "", say)


def check(story: dict, seconds: tuple[float, float] | None = None) -> tuple[dict, list[str]]:
    notes: list[str] = []
    st = copy.deepcopy(story)
    if not isinstance(st, dict) or not isinstance(st.get("scenes"), list):
        raise StoryError("le storyboard doit contenir une liste « scenes »")
    scenes = [s for s in st["scenes"] if isinstance(s, dict) and s.get("type") in ("hook", "section", "cta")]
    hooks = [s for s in scenes if s["type"] == "hook"]
    secs = [s for s in scenes if s["type"] == "section"]
    ctas = [s for s in scenes if s["type"] == "cta"]
    if not hooks or not secs or not ctas:
        raise StoryError("il faut 1 scène hook, au moins 1 section et 1 scène cta")
    if len(secs) > 5:
        notes.append(f"{len(secs) - 5} section(s) en trop supprimée(s)"); secs = secs[:5]
    scenes = [hooks[0]] + secs + [ctas[-1]]

    kw = re.sub(r"[^A-Z0-9]", "", plain(st.get("keyword") or ctas[-1].get("keyword") or "").upper())[: LIMITS["keyword"]]
    if not kw:
        raise StoryError("mot-clé (keyword) manquant")
    st["keyword"] = kw

    for s in scenes:
        say = str(s.get("say") or "").strip()
        if len(plain(MARK.sub("", say)).split()) < 3:
            raise StoryError(f"narration (say) manquante ou trop courte dans une scène {s['type']}")
        keep: set[str] = set()
        if s["type"] == "hook":
            s["title"] = _cut(s.get("title") or st.get("title") or "", LIMITS["title"], notes, "titre")
            if not plain(s["title"]):
                raise StoryError("titre du hook manquant")
            s["kicker"] = _cut(s.get("kicker") or "", LIMITS["kicker"], notes, "sur-titre") or None
            chips = [c for c in (s.get("chips") or []) if plain(c)][:8]
            s["chips"] = [_cut(c, LIMITS["chip"], notes, "puce") for c in chips]
            s["stamp"] = _cut(s.get("stamp") or "", LIMITS["stamp"], notes, "tampon") or None
            s["pill"] = _cut(s.get("pill") or "", LIMITS["pill"], notes, "pastille") or None
            keep = {"chips"} | ({"stamp"} if s["stamp"] else set()) | ({"pill"} if s["pill"] else set())
        elif s["type"] == "section":
            s["title"] = _cut(s.get("title") or "", LIMITS["sec_title"], notes, "titre de section")
            if not plain(s["title"]):
                raise StoryError("titre de section manquant")
            if s.get("icon") not in ICONS:
                s["icon"] = None
            blocks, used, height = [], set(), 0
            for bi, b in enumerate(s.get("blocks") or []):
                if not isinstance(b, dict) or b.get("kind") not in KINDS:
                    notes.append("bloc de type inconnu supprimé"); continue
                bid = re.sub(r"[^a-z]", "", str(b.get("id") or "").lower())[:1] or "abcdefgh"[bi % 8]
                while bid in used:
                    bid = "abcdefghij"[(ord(bid) - 96) % 10]
                b["id"] = bid
                k = b["kind"]
                if b.get("label"):
                    b["label"] = _cut(b["label"], LIMITS["label"], notes, "étiquette")
                if k in ("checklist", "compare"):
                    rows = []
                    for r in (b.get("rows") or [])[: (4 if k == "checklist" else 3)]:
                        r = {"text": r, "ok": True} if isinstance(r, str) else dict(r)
                        r["text"] = _cut(r.get("text") or "", LIMITS["row"], notes, "ligne")
                        r["ok"] = bool(r.get("ok", True))
                        if r["text"]:
                            rows.append(r)
                    if not rows:
                        notes.append("liste vide supprimée"); continue
                    b["rows"] = rows
                elif k == "stat":
                    v = b.get("value")
                    if isinstance(v, str):
                        m = re.fullmatch(r"\s*(-?\d[\d\s\u202f.,]*)\s*", v)
                        if m:
                            num = m.group(1).replace(" ", "").replace("\u202f", "").replace(",", ".")
                            try:
                                v = float(num) if "." in num else int(num)
                            except ValueError:
                                pass
                    if v is None or v == "":
                        notes.append("chiffre clé sans valeur supprimé"); continue
                    b["value"] = v if isinstance(v, (int, float)) else _cut(v, 10, notes, "chiffre")
                    b["unit"] = _cut(b.get("unit") or "", LIMITS["unit"], notes, "unité")
                elif k == "pill":
                    b["text"] = _cut(b.get("text") or "", LIMITS["pill"], notes, "pastille")
                    if not b["text"]:
                        continue
                elif k == "terminal":
                    b["text"] = str(b.get("text") or "").strip()[: LIMITS["term"]]
                    if not b["text"]:
                        continue
                elif k == "chips":
                    b["items"] = [_cut(c, LIMITS["item"], notes, "puce") for c in (b.get("items") or []) if plain(c)][:4]
                    if not b["items"]:
                        continue
                elif k == "note":
                    b["text"] = _cut(b.get("text") or "", LIMITS["note"], notes, "note")
                    if not b["text"]:
                        continue
                h = block_height(b) + 26
                if len(blocks) >= 3 or height + h > 800:
                    notes.append(f"bloc « {k} » supprimé (plus de place à l'écran)"); continue
                height += h; used.add(bid); blocks.append(b)
            if not blocks:
                raise StoryError(f"section « {plain(s['title'])} » sans bloc visuel")
            s["blocks"] = blocks
            for b in blocks:
                keep.add(b["id"])
                for i in range(len(b.get("rows") or b.get("items") or [])):
                    keep.add(f"{b['id']}{i + 1}")
        else:  # cta
            s["keyword"] = kw
            s["sub"] = _cut(s.get("sub") or "", LIMITS["sub"], notes, "sous-texte") or None
            s["verb"] = _cut(s.get("verb") or "Commente", 12, notes, "verbe")
            keep = {"kw", "sub"}
            if kw.lower() not in plain(say).lower():
                notes.append("le mot-clé n'est pas prononcé dans l'appel à l'action")
        before = set(MARK.findall(say))
        say = _strip_marks(say, keep)
        if before - keep:
            notes.append(f"repères inconnus retirés : {sorted(before - keep)}")
        words = plain(MARK.sub("", say)).split()
        if len(words) > WORDS_SCENE:
            notes.append(f"narration longue dans une scène {s['type']} ({len(words)} mots)")
        s["say"] = re.sub(r"\s+", " ", say).strip()
        parse_say(s["say"])     # vérifie que l'analyse des repères passe

    for i, s in enumerate(secs):
        s["n"] = i + 1
    st["scenes"] = scenes
    total = sum(len(plain(MARK.sub("", s["say"])).split()) for s in scenes)
    st["_words"] = total
    lo, hi = WORDS_TOTAL
    if seconds:
        lo, hi = max(lo, int(seconds[0] * 2.9)), min(hi, int(seconds[1] * 3.9) + 8)
    if total < lo:
        raise StoryError(f"narration trop courte ({total} mots, minimum {lo})")
    if total > hi:
        raise StoryError(f"narration trop longue ({total} mots, maximum {hi})")
    st["title"] = plain(st.get("title") or hooks[0]["title"])[:90]
    st["caption"] = re.sub(r"\s+", " ", str(st.get("caption") or st["title"])).strip()[:300]
    tags = [re.sub(r"[^0-9A-Za-zÀ-ÿ]", "", str(h)).lower() for h in (st.get("hashtags") or [])]
    st["hashtags"] = [h for h in dict.fromkeys(tags) if h][:8]
    st["links"] = [{"n": str(l.get("n", ""))[:60], "u": str(l["u"])} for l in (st.get("links") or [])
                   if isinstance(l, dict) and str(l.get("u", "")).startswith("https://")][:8]
    return st, notes


def numbers_in(story: dict) -> set[str]:
    """Tous les nombres affichés ou prononcés (pour le contrôle anti-invention)."""
    blob = []
    for s in story["scenes"]:
        blob += [s.get("say", ""), s.get("title", ""), s.get("stamp") or "", s.get("pill") or "", " ".join(s.get("chips") or [])]
        for b in s.get("blocks") or []:
            blob += [str(b.get("value", "")), b.get("unit", ""), b.get("text", ""), b.get("label", "")]
            blob += [r["text"] if isinstance(r, dict) else str(r) for r in (b.get("rows") or [])] + list(b.get("items") or [])
    return find_numbers(MARK.sub(" ", " | ".join(map(str, blob))))


NUMBER = re.compile(r"\d{1,3}(?:[ \u00a0\u202f]\d{3})+(?!\d)|\d+(?:[.,]\d+)?")


def find_numbers(text: str) -> set[str]:
    """Nombres d'un texte, normalisés : « 68 000 » -> 68000, « 3,5 » -> 3.5. Les milliers ne se lisent qu'avec une espace."""
    out = set()
    for m in NUMBER.finditer(text):
        raw = m.group(0)
        if re.search(r"[ \u00a0\u202f]", raw):
            out.add(re.sub(r"[ \u00a0\u202f]", "", raw))
        else:
            n = raw.replace(",", ".")
            out.add(n.rstrip("0").rstrip(".") if "." in n else n)
    return out
