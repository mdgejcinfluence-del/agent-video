"""Contrôle et réparation de la FORME d'un storyboard (le fond est contrôlé par studio/garde.py).

Une vidéo suit toujours le même fil :
    resultat  -> ce qui a été produit, à l'image dès la première seconde, puis pour qui et pour quoi
    etape ×3  -> trois étapes liées, chacune avec sa preuve (demande écrite, code, rendu, avant/après, erreur corrigée)
    verif     -> ce qui a été vérifié, et une limite utile à connaître
    cta       -> la phrase de fin imposée (écrite par l'agent, jamais par le modèle)

Un modèle gratuit se trompe souvent sur la forme (texte trop long, repère inconnu, bloc en trop).
On répare ce qui est réparable et on ne rejette que ce qui rendrait la vidéo fausse ou vide.
`check()` renvoie (storyboard propre, notes).
"""
from __future__ import annotations

import copy
import math
import re

from .align import MARK, parse_say

SEGMENTS = ("commercant", "createur_freelance")
HOOK_TYPES = ("resultat", "probleme", "contraste")
PROOF_KINDS = {"brief", "code", "media", "avant_apres", "erreur"}           # ce qui montre quelque chose de réel
TEXT_KINDS = {"checklist", "compare", "stat", "pill", "terminal", "chips", "note", "source"}
KINDS = PROOF_KINDS | TEXT_KINDS
MEDIA_KINDS = {"media", "avant_apres", "erreur"}
LIMITS = {"title": 40, "public": 40, "step_title": 40, "brief": 190, "hl": 60, "code_line": 64, "code_lines": 5, "label": 26,
          "mini": 16, "row": 34, "vrow": 60, "limite": 84, "source": 46, "note": 90, "pill": 26, "item": 18, "unit": 18,
          "term": 46, "keyword": 12, "cover": 30}
WORDS_SCENE = 34
WORDS_TOTAL = (70, 135)
STEPS = 3
COL_HEIGHT = 814          # hauteur utile d'une étape quand le titre tient sur deux lignes (voir engine/player.js)
MEDIA_MIN = 400           # en dessous, un rendu n'est plus lisible sur un téléphone


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
    """Hauteur approximative d'un bloc (px), pour refuser une étape qui ne tiendrait pas à l'écran."""
    k = b["kind"]
    if k == "brief":
        return 116 + 63 * max(1, math.ceil(len(b["text"]) / 34))
    if k == "code":
        return 106 + 62 * len(b["lines"])
    if k in ("checklist", "compare"):
        return 62 + 64 * len(b["rows"]) + (54 if b.get("label") else 0)
    if k == "note":
        return 62 + 51 * max(1, math.ceil(len(plain(b["text"])) / 36))
    if k in MEDIA_KINDS:
        return MEDIA_MIN
    return {"stat": 216 if b.get("label") else 180, "pill": 64, "terminal": 170, "chips": 86, "source": 30}[k]


def sub_cues(b: dict) -> int:
    """Nombre de repères de détail d'un bloc : [a1], [a2]…"""
    k = b["kind"]
    if k == "brief":
        return len(b.get("hl") or [])
    if k == "code":
        return 1 if b.get("hl") else 0
    if k == "avant_apres":
        return 1
    if k == "erreur":
        return 2 if b.get("fix") else 1
    return len(b.get("rows") or b.get("items") or [])


def _strip_marks(say: str, keep: set[str]) -> str:
    return MARK.sub(lambda m: m.group(0) if m.group(1) in keep else "", say)


def _visuel(v, notes: list, where: str):
    """{"ref": "..."}  ou  {"avant": {...}, "apres": {...}}"""
    if not isinstance(v, dict):
        return None
    def one(x):
        if isinstance(x, str):
            x = {"ref": x}
        if not isinstance(x, dict) or not str(x.get("ref") or "").strip():
            return None
        o = {"ref": str(x["ref"]).strip()}
        if x.get("label"):
            o["label"] = _cut(x["label"], LIMITS["mini"], notes, "étiquette")
        if x.get("cadre") in ("telephone", "photo", "plein"):
            o["cadre"] = x["cadre"]
        return o
    if v.get("avant") is not None or v.get("apres") is not None:
        a, b = one(v.get("avant")), one(v.get("apres"))
        if not a or not b:
            notes.append(f"{where} : contraste incomplet, visuel ignoré")
            return None
        return {"kind": "contraste", "avant": a, "apres": b}
    o = one(v)
    return o and {"kind": "media", **o}


def _block(b: dict, bid: str, notes: list) -> dict | None:
    k = b["kind"]
    o: dict = {"id": bid, "kind": k}
    if b.get("label") and k not in ("avant_apres",):
        o["label"] = _cut(b["label"], LIMITS["label"], notes, "étiquette")
    if k == "brief":
        text = re.sub(r"[ \t]+", " ", str(b.get("text") or "")).strip()
        if len(text) > LIMITS["brief"]:
            raise StoryError(f"extrait de la demande trop long ({len(text)} caractères, maximum {LIMITS['brief']}) : choisis un passage plus court, mot pour mot")
        if len(text) < 12:
            return None
        o["text"] = text
        o["source"] = "correction" if str(b.get("source") or "").lower().startswith("corr") else "demande"
        o["hl"] = [h for h in (str(x).strip() for x in (b.get("hl") or [])) if h and h in text and len(h) <= LIMITS["hl"]][:2]
        o.setdefault("label", "Correction demandée" if o["source"] == "correction" else "Demande écrite")
    elif k == "code":
        lines = [str(x).rstrip() for x in (b.get("lines") or []) if str(x).strip()][: LIMITS["code_lines"]]
        if not lines:
            return None
        if any(len(x) > LIMITS["code_line"] for x in lines):
            raise StoryError(f"ligne de code trop longue (maximum {LIMITS['code_line']} caractères) : montre des lignes plus courtes, telles quelles")
        o["lines"] = lines
        o["file"] = str(b.get("file") or "").strip()[:40]
        if not o["file"]:
            raise StoryError("bloc « code » sans nom de fichier (file)")
        try:
            hl = int(b.get("hl") or 0)
        except (TypeError, ValueError):
            hl = 0
        if 1 <= hl <= len(lines):
            o["hl"] = hl
    elif k == "media":
        ref = str(b.get("ref") or "").strip()
        if not ref:
            return None
        o["ref"] = ref
        if b.get("cadre") in ("telephone", "photo", "plein"):
            o["cadre"] = b["cadre"]
    elif k == "avant_apres":
        v = _visuel({"avant": b.get("avant"), "apres": b.get("apres")}, notes, "avant/après")
        if not v:
            return None
        o["avant"], o["apres"] = v["avant"], v["apres"]
    elif k == "erreur":
        ref = str(b.get("ref") or "").strip()
        if not ref:
            return None
        o["ref"] = ref
        o["label"] = _cut(b.get("label") or "défaut", 22, notes, "diagnostic")
        fx = b.get("fix")
        if isinstance(fx, dict) and str(fx.get("ref") or "").strip():
            o["fix"] = {"ref": str(fx["ref"]).strip(), "label": _cut(fx.get("label") or "corrigé", LIMITS["mini"], notes, "étiquette")}
    elif k in ("checklist", "compare"):
        rows = []
        for r in (b.get("rows") or [])[: (4 if k == "checklist" else 3)]:
            r = {"text": r, "ok": True} if isinstance(r, str) else dict(r)
            r = {"text": _cut(r.get("text") or "", LIMITS["row"], notes, "ligne"), "ok": bool(r.get("ok", True))}
            if r["text"]:
                rows.append(r)
        if not rows:
            return None
        o["rows"] = rows
    elif k == "stat":
        v = b.get("value")
        if isinstance(v, str):
            m = re.fullmatch(r"\s*(-?\d[\d\s\u202f\u00a0.,]*)\s*", v)
            if m:
                num = re.sub(r"[\s\u202f\u00a0]", "", m.group(1)).replace(",", ".")
                try:
                    v = float(num) if "." in num else int(num)
                except ValueError:
                    pass
        if v is None or v == "":
            return None
        o["value"] = v if isinstance(v, (int, float)) else _cut(v, 10, notes, "chiffre")
        o["unit"] = _cut(b.get("unit") or "", LIMITS["unit"], notes, "unité")
    elif k == "chips":
        o["items"] = [_cut(c, LIMITS["item"], notes, "puce") for c in (b.get("items") or []) if plain(c)][:4]
        if not o["items"]:
            return None
    else:  # pill, terminal, note, source
        lim = {"pill": LIMITS["pill"], "terminal": LIMITS["term"], "note": LIMITS["note"], "source": LIMITS["source"]}[k]
        o["text"] = str(b.get("text") or "").strip()[:lim] if k == "terminal" else _cut(b.get("text") or "", lim, notes, k)
        if not o["text"]:
            return None
    return o


def check(story: dict, seconds: tuple[float, float] | None = None) -> tuple[dict, list[str]]:
    notes: list[str] = []
    st = copy.deepcopy(story)
    if not isinstance(st, dict) or not isinstance(st.get("scenes"), list):
        raise StoryError("le storyboard doit contenir une liste « scenes »")
    if st.get("segment") not in SEGMENTS:
        raise StoryError(f"« segment » doit valoir {' ou '.join(SEGMENTS)} : une vidéo s'adresse à un seul public")
    if not str(st.get("preuve") or "").strip():
        raise StoryError("« preuve » manquant : pas de dossier de preuve, pas de vidéo")
    scenes = [s for s in st["scenes"] if isinstance(s, dict)]
    res = [s for s in scenes if s.get("type") == "resultat"]
    steps = [s for s in scenes if s.get("type") == "etape"]
    ver = [s for s in scenes if s.get("type") == "verif"]
    if not res or not ver:
        raise StoryError("il faut, dans l'ordre : 1 scène resultat, 3 scènes etape, 1 scène verif (la scène cta est ajoutée par l'agent)")
    if len(steps) != STEPS:
        raise StoryError(f"il faut exactement {STEPS} scènes « etape » liées par une progression (reçu : {len(steps)})")
    cta = next((s for s in scenes if s.get("type") == "cta"), None) or {"type": "cta"}
    scenes = [res[0]] + steps + [ver[0], cta]

    kw = re.sub(r"[^A-Z0-9]", "", plain(st.get("keyword") or cta.get("keyword") or "").upper())[: LIMITS["keyword"]]
    if len(kw) < 2:
        raise StoryError("mot-clé (keyword) manquant")
    st["keyword"] = kw
    stats_seen = 0
    for s in scenes:
        t = s["type"]
        keep: set[str] = set()
        if t == "cta":
            s.clear(); s.update({"type": "cta", "keyword": kw, "say": cta.get("say") or ""})      # la fin est imposée par writer.apply_cta
            continue
        say = str(s.get("say") or "").strip()
        if len(plain(MARK.sub("", say)).split()) < 4:
            raise StoryError(f"narration (say) manquante ou trop courte dans la scène « {t} »")
        if t == "resultat":
            s["title"] = _cut(s.get("title") or st.get("title") or "", LIMITS["title"], notes, "titre")
            if not plain(s["title"]):
                raise StoryError("titre de la scène resultat manquant")
            s["public"] = _cut(s.get("public") or "", LIMITS["public"], notes, "public")
            if not plain(s["public"]):
                raise StoryError("« public » manquant dans la scène resultat : nomme la personne à qui la vidéo s'adresse (ex. « Si tu vends tes produits »)")
            s["visuel"] = _visuel(s.get("visuel"), notes, "resultat")
            if not s["visuel"]:
                raise StoryError("« visuel » manquant dans la scène resultat : la première image montre ce qui a été réellement produit")
            keep = {"public"}
        elif t == "etape":
            s["title"] = _cut(s.get("title") or "", LIMITS["step_title"], notes, "titre d'étape")
            if not plain(s["title"]):
                raise StoryError("titre d'étape manquant")
            blocks, used, height = [], set(), 0
            for bi, b in enumerate(s.get("blocks") or []):
                if not isinstance(b, dict) or b.get("kind") not in KINDS:
                    notes.append("bloc de type inconnu supprimé"); continue
                bid = re.sub(r"[^a-z]", "", str(b.get("id") or "").lower())[:1] or "abcdefgh"[bi % 8]
                while bid in used:
                    bid = "abcdefghij"[(ord(bid) - 96) % 10]
                ob = _block(b, bid, notes)
                if ob is None:
                    notes.append(f"bloc « {b.get('kind')} » vide supprimé"); continue
                if ob["kind"] == "stat":
                    stats_seen += 1
                    if stats_seen > 1:
                        notes.append("deuxième chiffre clé supprimé (une statistique au plus par vidéo)"); continue
                h = block_height(ob) + 26
                if len(blocks) >= 2 or height + h > COL_HEIGHT + 26:
                    notes.append(f"bloc « {ob['kind']} » supprimé (plus de place à l'écran)"); continue
                height += h; used.add(bid); blocks.append(ob)
            if not blocks:
                raise StoryError(f"étape « {plain(s['title'])} » sans rien à montrer : ajoute un bloc (demande écrite, code, rendu, avant/après, erreur corrigée)")
            s["blocks"] = blocks
            for b in blocks:
                keep.add(b["id"])
                keep |= {f"{b['id']}{i + 1}" for i in range(sub_cues(b))}
        else:  # verif
            s["title"] = _cut(s.get("title") or "Ce que j'ai *vérifié*", LIMITS["step_title"], notes, "titre")
            rows = []
            for r in (s.get("rows") or [])[:3]:
                r = {"text": r, "ok": True} if isinstance(r, str) else dict(r)
                r = {"text": _cut(r.get("text") or "", LIMITS["vrow"], notes, "vérification"), "ok": bool(r.get("ok", True))}
                if r["text"]:
                    rows.append(r)
            if len(rows) < 2:
                raise StoryError("scène verif : il faut 2 ou 3 vérifications réellement faites (rows)")
            s["rows"] = rows
            s["limite"] = _cut(s.get("limite") or "", LIMITS["limite"], notes, "limite")
            if not plain(s["limite"]):
                raise StoryError("scène verif : « limite » manquante (une limite, un prérequis ou un coût utile à connaître)")
            s["source"] = _cut(s.get("source") or "", LIMITS["source"], notes, "source") or None
            s["visuel"] = _visuel(s.get("visuel"), notes, "verif")
            if s["visuel"] and s["visuel"]["kind"] != "media":
                s["visuel"] = {"kind": "media", **s["visuel"]["apres"]}
            keep = {f"r{i + 1}" for i in range(len(rows))} | {"limite"} | ({"source"} if s["source"] else set())
        before = set(MARK.findall(say))
        say = _strip_marks(say, keep)
        if before - keep:
            notes.append(f"repères inconnus retirés : {sorted(before - keep)}")
        words = plain(MARK.sub("", say)).split()
        if len(words) > WORDS_SCENE:
            notes.append(f"narration longue dans la scène « {t} » ({len(words)} mots)")
        s["say"] = re.sub(r"\s+", " ", say).strip()
        parse_say(s["say"])     # vérifie que l'analyse des repères passe

    for i, s in enumerate(steps):
        s["n"] = i + 1
    st["scenes"] = scenes
    kinds = [b["kind"] for s in steps for b in s["blocks"]]
    if "brief" not in kinds:
        raise StoryError("la demande écrite doit apparaître dans la vidéo : ajoute un bloc « brief » (extrait mot pour mot) dans une étape")
    if sum(1 for s in steps if any(b["kind"] in PROOF_KINDS for b in s["blocks"])) < 2:
        raise StoryError("au moins 2 étapes sur 3 doivent montrer une preuve (demande écrite, code, rendu, avant/après, erreur corrigée)")
    total = sum(len(plain(MARK.sub("", s.get("say") or "")).split()) for s in scenes)
    st["_words"] = total
    lo, hi = WORDS_TOTAL
    if seconds:
        lo, hi = max(lo, int(seconds[0] * 2.0)), min(hi, int(seconds[1] * 3.0))
    if total < lo - 17:           # la phrase de fin (17 mots) est ajoutée ensuite
        raise StoryError(f"narration trop courte ({total} mots hors phrase de fin, minimum {lo - 17})")
    if total > hi:
        raise StoryError(f"narration trop longue ({total} mots, maximum {hi})")
    st["version"] = 2
    st["title"] = plain(st.get("title") or res[0]["title"])[:90]
    st["caption"] = re.sub(r"\s+", " ", str(st.get("caption") or st["title"])).strip()[:300]
    st["couverture"] = _cut(st.get("couverture") or plain(res[0]["title"]), LIMITS["cover"], [], "couverture")
    tags = [re.sub(r"[^0-9A-Za-zÀ-ÿ]", "", str(h)).lower() for h in (st.get("hashtags") or [])]
    st["hashtags"] = [h for h in dict.fromkeys(tags) if h][:5]
    st["hook_type"] = st.get("hook_type") if st.get("hook_type") in HOOK_TYPES else "resultat"
    hooks = []
    for h in st.get("hooks") or []:
        if isinstance(h, dict) and h.get("type") in HOOK_TYPES and plain(h.get("text")):
            hooks.append({"type": h["type"], "text": plain(h["text"])[:120]})
    st["hooks"] = hooks[:3]
    st["hook_pourquoi"] = plain(st.get("hook_pourquoi"))[:240]
    st["faits"] = [str(x) for x in (st.get("faits") or []) if str(x).strip()][:6]
    try:
        st["sujet"] = int(st.get("sujet"))
    except (TypeError, ValueError):
        raise StoryError("« sujet » doit être un numéro de la banque de sujets (data/sujets.yaml)") from None
    return st, notes


def refs_in(story: dict) -> set[str]:
    """Tous les médias cités par le storyboard."""
    out = set()
    def vis(v):
        if not v:
            return
        if v.get("kind") == "contraste":
            out.update({v["avant"]["ref"], v["apres"]["ref"]})
        elif v.get("ref"):
            out.add(v["ref"])
    for s in story["scenes"]:
        vis(s.get("visuel"))
        for b in s.get("blocks") or []:
            if b.get("ref"):
                out.add(b["ref"])
            for k in ("avant", "apres", "fix"):
                if isinstance(b.get(k), dict) and b[k].get("ref"):
                    out.add(b[k]["ref"])
    return out


def texts_in(story: dict, with_code: bool = False) -> list[str]:
    """Tous les textes affichés ou prononcés (hors phrase de fin imposée), un par unité de sens."""
    out = [story.get("title", ""), story.get("caption_corps", story.get("caption", "")), story.get("couverture", "")]
    for s in story["scenes"]:
        if s["type"] == "cta":
            continue
        out += [MARK.sub(" ", s.get("say", "")), s.get("title", ""), s.get("public") or "", s.get("limite") or "", s.get("source") or ""]
        out += [r["text"] for r in s.get("rows") or []]
        for k in ("visuel",):
            v = s.get(k) or {}
            out += [v.get("label") or "", (v.get("avant") or {}).get("label") or "", (v.get("apres") or {}).get("label") or ""]
        for b in s.get("blocks") or []:
            out += [b.get("label") or "", str(b.get("unit") or "")]
            if b["kind"] == "stat":
                out.append(f"{b.get('value')} {b.get('unit') or ''}")
            if b["kind"] not in ("brief", "code") or with_code:
                out += [b.get("text") or ""] + list(b.get("lines") or [])
            out += [r["text"] for r in b.get("rows") or []] + list(b.get("items") or [])
            for k in ("avant", "apres", "fix"):
                if isinstance(b.get(k), dict):
                    out.append(b[k].get("label") or "")
    return [plain(x) for x in out if plain(x)]


NUMBER = re.compile(r"\d{1,3}(?:[ \u00a0\u202f]\d{3})+(?!\d)|\d+(?:[.,]\d+)?")


def find_numbers(text: str) -> set[str]:
    """Nombres d'un texte, normalisés : « 68 000 » -> 68000, « 3,5 » -> 3.5. Les milliers ne se lisent qu'avec une espace."""
    out = set()
    for m in NUMBER.finditer(text):
        out.add(_num(m.group(0)))
    return out


def _num(raw: str) -> str:
    if re.search(r"[ \u00a0\u202f]", raw):
        return re.sub(r"[ \u00a0\u202f]", "", raw)
    n = raw.replace(",", ".")
    return n.rstrip("0").rstrip(".") if "." in n else n


def numbers_in(story: dict) -> set[str]:
    """Tous les nombres affichés ou prononcés hors extraits (pour le contrôle anti-invention)."""
    return find_numbers(" | ".join(texts_in(story)))
