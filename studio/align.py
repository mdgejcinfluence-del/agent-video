"""Texte parlé -> mots affichés, repères visuels et sous-titres.

Le scénariste écrit la narration d'une scène avec des repères entre crochets :

    "Tu crées [a1]un compte gratuit, [a2]sans carte bancaire."

Le repère [a1] veut dire : « à l'instant où ce mot est prononcé, affiche la
ligne 1 du bloc a ». Le mot qui suit le repère est encadré dans les
sous-titres (comme dans la vidéo de référence).
"""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

MARK = re.compile(r"\[([A-Za-z_]+\d*)\]")
PUNCT_END = tuple(".,;:!?…")
WEAK = {"le", "la", "les", "l", "de", "des", "du", "d", "un", "une", "et", "à", "a", "en", "ton", "ta", "tes", "ce", "ces",
        "que", "qui", "pour", "avec", "sur", "dans", "il", "tu", "je", "on", "va", "est", "c'est", "ne", "se", "te", "me", "y",
        "au", "aux", "mon", "ma", "mes", "son", "sa", "ses", "ou", "mais", "donc", "si", "par", "the", "of", "to", "and", "in"}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in s if c.isalnum())


def tokens(text: str) -> list[str]:
    """Découpe en mots affichables ; la ponctuation isolée (« : », « ? », « € ») se colle au mot précédent."""
    out: list[str] = []
    for raw in text.replace("\u00a0", " ").split():
        if out and (not norm(raw) or (re.fullmatch(r"\d{3}[.,;:!?…]*", raw) and re.fullmatch(r"\d{1,3}(\u00a0\d{3})*", out[-1]))):
            out[-1] = out[-1] + "\u00a0" + raw      # « : », « € », et les milliers « 68 000 »
        else:
            out.append(raw)
    return out


def parse_say(say: str) -> tuple[str, list[str], dict[str, int]]:
    """Renvoie (texte sans repères, mots, {repère: index du mot qui suit})."""
    cues: dict[str, int] = {}
    toks: list[str] = []
    pos = 0
    clean_parts: list[str] = []
    for m in MARK.finditer(say):
        piece = say[pos:m.start()]
        clean_parts.append(piece)
        toks = tokens("".join(clean_parts))
        cues.setdefault(m.group(1), len(toks))
        # un repère collé à la fin d'un mot ne doit pas souder deux mots
        if piece and not piece[-1].isspace() and m.end() < len(say) and not say[m.end()].isspace():
            pass
        pos = m.end()
    clean_parts.append(say[pos:])
    clean = re.sub(r"\s+", " ", "".join(clean_parts)).strip()
    toks = tokens(clean)
    n = len(toks)
    cues = {k: min(v, max(0, n - 1)) for k, v in cues.items()}
    return clean, toks, cues


def map_times(toks: list[str], spoken: list[dict], total: float) -> list[tuple[float, float]]:
    """Associe chaque mot affiché à un intervalle [début, fin] à partir des mots horodatés par la voix.

    `spoken` : [{"w": "mot", "t0": s, "t1": s}], dans l'ordre. Les mots qui ne correspondent pas
    exactement (nombres, prononciations forcées) sont interpolés entre leurs voisins.
    """
    sp: list[tuple[str, float, float]] = []
    for s in spoken:
        parts = [p for p in s["w"].split() if p] or [s["w"]]
        tot = sum(max(1, len(norm(p))) for p in parts)
        t = s["t0"]
        for p in parts:
            d = (s["t1"] - s["t0"]) * max(1, len(norm(p))) / tot
            sp.append((norm(p), t, t + d))
            t += d
    a = [norm(t) for t in toks]
    b = [x[0] for x in sp]
    times: list[tuple[float, float] | None] = [None] * len(toks)
    for blk in SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks():
        for k in range(blk.size):
            times[blk.a + k] = (sp[blk.b + k][1], sp[blk.b + k][2])
    # interpolation des trous
    i = 0
    while i < len(toks):
        if times[i] is not None:
            i += 1
            continue
        j = i
        while j < len(toks) and times[j] is None:
            j += 1
        left = times[i - 1][1] if i > 0 else (sp[0][1] if sp else 0.0)
        right = times[j][0] if j < len(toks) else (sp[-1][2] if sp else total)
        if right <= left:
            right = left + 0.12 * (j - i)
        w = [max(1, len(a[k])) for k in range(i, j)]
        acc = left
        for k in range(i, j):
            d = (right - left) * w[k - i] / sum(w)
            times[k] = (acc, acc + d)
            acc += d
        i = j
    return [t for t in times]  # type: ignore[misc]


def estimate_times(toks: list[str], total: float, lead: float = 0.05, tail: float = 0.1) -> list[tuple[float, float]]:
    """Secours quand la voix ne fournit aucun horodatage : répartition proportionnelle à la longueur."""
    w = []
    for t in toks:
        base = max(1, len(norm(t))) + 1.2
        if t.rstrip().endswith((".", "!", "?", ":", "…")):
            base += 4.5
        elif t.rstrip().endswith((",", ";")):
            base += 2.2
        w.append(base)
    span = max(0.2, total - lead - tail)
    out, acc = [], lead
    for t, x in zip(toks, w):
        d = span * x / sum(w)
        spoken = d * (max(1, len(norm(t))) + 1.2) / x
        out.append((acc, acc + spoken))
        acc += d
    return out


def group_captions(toks: list[str], times: list[tuple[float, float]], hl: set[int], offset: float,
                   max_words: int = 3, max_chars: int = 19) -> list[dict]:
    """Regroupe les mots en sous-titres courts (1 à 3 mots), coupés à la ponctuation."""
    groups: list[list[int]] = []
    cur: list[int] = []
    chars = 0
    for i, t in enumerate(toks):
        ln = len(t)
        if cur and (len(cur) >= max_words or chars + 1 + ln > max_chars):
            groups.append(cur); cur = []; chars = 0
        cur.append(i); chars += ln + (1 if chars else 0)
        if t.rstrip("\u00a0 ").endswith(PUNCT_END):
            groups.append(cur); cur = []; chars = 0
    if cur:
        groups.append(cur)
    # pas de petit mot orphelin en fin de groupe (« … le » | « script »)
    for g, nxt in zip(groups, groups[1:]):
        last = toks[g[-1]]
        if len(g) > 1 and norm(last) in {norm(w) for w in WEAK} and not last.endswith(PUNCT_END):
            if sum(len(toks[k]) for k in nxt) + len(last) + len(nxt) <= max_chars + 4 and len(nxt) < max_words + 1:
                nxt.insert(0, g.pop())
    groups = [g for g in groups if g]
    out = []
    for gi, g in enumerate(groups):
        t0 = times[g[0]][0] - 0.03
        end_last = times[g[-1]][1]
        t1 = (times[groups[gi + 1][0]][0] - 0.05) if gi + 1 < len(groups) else end_last + 0.45
        t1 = max(t1, t0 + 0.2)
        if gi + 1 < len(groups):
            t1 = min(t1, end_last + 0.6) if t1 - end_last > 0.6 else t1
        out.append({"t0": round(offset + max(0.0, t0), 3), "t1": round(offset + t1, 3),
                    "words": [{"w": toks[k], "t": round(offset + max(0.0, times[k][0] - 0.03), 3), **({"hl": True} if k in hl else {})} for k in g]})
    return out
