"""Le stratège : lit les statistiques, note chaque vidéo, et décide de la suivante.

Deux étages :
  1. un calcul simple et vérifiable (bandit de Thompson) choisit le FORMAT, le type d'accroche,
     la longueur et les créneaux horaires : il favorise ce qui a marché, tout en gardant une
     part d'essais (sinon il ne découvrirait jamais mieux) ;
  2. le LLM choisit le SUJET et l'angle parmi les candidats de la veille, en lisant un mémo des
     meilleures et des pires vidéos. S'il est indisponible, un classement déterministe prend le relais.

Les « a priori » de départ viennent de l'observation de comptes de la même niche (petit
échantillon) : ils sont volontairement faibles et sont écrasés par tes propres statistiques.
"""
from __future__ import annotations

import datetime as dt
import math
import random
import re
import statistics as st

from .state import State, now

FORMATS = {
    "liste": "liste chiffrée d'outils/ressources (« 5 skills pour… ») : une section par élément",
    "transforme": "transformation (« Transforme X en Y ») : un seul outil, bénéfice concret, étapes",
    "tuto": "mini-tutoriel en 3 étapes : résultat promis au début, puis les étapes",
    "mythe": "idée reçue ou piège (« X est nul en Y ? ») : on démonte, puis on donne la bonne méthode",
    "comparatif": "deux options comparées, verdict net",
    "offre": "présentation directe de la formation : pour qui, ce qu'on y apprend, comment y accéder",
}
HOOKS = {
    "chiffre": "accroche par un chiffre précis (« 5 outils », « 40 requêtes par minute »)",
    "promesse": "accroche par le résultat (« Tu peux… sans… »)",
    "question": "accroche par une question que la cible se pose",
    "alerte": "accroche par une erreur ou un piège à éviter",
}
LENGTHS = {"court": (26, 36), "moyen": (36, 48)}

# a priori (en « points de score », 0 = vidéo médiane) : hypothèses de départ, corrigées par tes statistiques
PRIOR = {
    "format": {"liste": 0.25, "transforme": 0.35, "tuto": 0.0, "mythe": 0.0, "comparatif": -0.1},
    "hook": {"chiffre": 0.2, "promesse": 0.15, "question": 0.0, "alerte": 0.0},
    "length": {"court": 0.2, "moyen": 0.0},
    "slot": {"soir": 0.15},
}
N0 = 2.0     # poids de l'a priori, en « nombre de vidéos »


def slot_bucket(hhmm: str) -> str:
    h = int(hhmm.split(":")[0])
    return "matin" if h < 11 else "midi" if h < 16 else "soir"


# --------------------------------------------------------------------------- notation
def _latest(snaps: list[dict], min_h: float = 20) -> dict | None:
    ok = [s for s in snaps or [] if s.get("h", 0) >= min_h and s.get("views") is not None]
    return max(ok, key=lambda s: s["h"]) if ok else None


def score_posts(state: State, cfg: dict) -> None:
    """Calcule post['score'] : 0 = médiane du compte, +1 = deux fois mieux, -1 = deux fois moins bien."""
    w = (cfg.get("stats") or {}).get("weights") or {"views": 0.5, "comments": 0.2, "shares": 0.15, "saves": 0.15}
    posts = state.posts
    per_net: dict[str, list[tuple[dict, dict]]] = {}
    for p in posts:
        for net, snaps in (p.get("stats") or {}).items():
            s = _latest(snaps)
            if s:
                per_net.setdefault(net, []).append((p, s))
    parts: dict[str, list[float]] = {}
    for net, rows in per_net.items():
        if len(rows) < 3:
            continue

        def rate(s, k):
            return (s.get(k) or 0) / max(1, s.get("views") or 0)
        med = {"views": st.median([s["views"] for _, s in rows]) or 1}
        for k in ("comments", "shares", "saves"):
            vals = [rate(s, k) for _, s in rows if s.get(k) is not None]
            med[k] = (st.median(vals) if vals else 0) or 1e-4
        for p, s in rows:
            tot, wsum = 0.0, 0.0
            for k, wk in w.items():
                if k == "views":
                    r = max(1, s["views"]) / med["views"]
                elif s.get(k) is None:
                    continue
                else:
                    # taux « lissé » : avec peu de vues, un taux est très bruité, on le rapproche de la médiane
                    m = med["views"]
                    r = ((s.get(k) or 0) + m * med[k]) / ((s.get("views") or 0) + m) / med[k]
                tot += wk * max(-3.0, min(3.0, math.log2(r))); wsum += wk
            if wsum:
                parts.setdefault(p["id"], []).append(tot / wsum)
    for p in posts:
        if p["id"] in parts:
            p["score"] = round(sum(parts[p["id"]]) / len(parts[p["id"]]), 3)
            p["score_at"] = now().isoformat(timespec="seconds")
    state.save_posts()


# --------------------------------------------------------------------------- bandit
def arm_stats(state: State, dim: str) -> dict[str, list[float]]:
    out: dict[str, list[float]] = {}
    for p in state.posts:
        if p.get("score") is None:
            continue
        v = (p.get("brief") or {}).get(dim)
        if v:
            out.setdefault(v, []).append(p["score"])
    return out


def length_bucket(seconds: float) -> str:
    """Catégorie de longueur réellement obtenue : c'est elle qui sert à l'apprentissage, pas celle qui était demandée."""
    for name, (_lo, hi) in LENGTHS.items():
        if seconds < hi:
            return name
    return list(LENGTHS)[-1]


def posterior(values: list[str], dim: str, state: State) -> dict[str, tuple[float, float]]:
    obs = arm_stats(state, dim)
    out = {}
    for v in values:
        r = obs.get(v, [])
        mu0 = PRIOR.get(dim, {}).get(v, 0.0)
        n = len(r)
        out[v] = ((N0 * mu0 + sum(r)) / (N0 + n), 1.0 / math.sqrt(N0 + n))
    return out


def sample(values: list[str], dim: str, state: State, rng: random.Random, explore: float, k: int = 1) -> list[str]:
    post = posterior(values, dim, state)
    draws = sorted(((rng.gauss(m, s * (0.6 + 2.0 * explore)), v) for v, (m, s) in post.items()), reverse=True)
    return [v for _, v in draws[:k]]


def plan_day(state: State, cfg: dict, date: str, rng: random.Random) -> dict:
    days = state.load("day", {})
    if date in days:
        return days[date]
    sch = cfg.get("schedule", {})
    slots = list(sch.get("slots") or ["07:30", "18:30"])
    k = min(int(sch.get("videos_per_day", 2)), len(slots))
    explore = float((cfg.get("strategy") or {}).get("explore", 0.2))
    # on tire des « tranches » (matin/midi/soir) puis on garde au plus un créneau par tranche si possible
    order = sample(slots, "slot_exact", state, rng, explore, len(slots))
    buckets = posterior(sorted({slot_bucket(s) for s in slots}), "slot", state)
    order.sort(key=lambda s: -(buckets[slot_bucket(s)][0] + rng.gauss(0, buckets[slot_bucket(s)][1] * (0.6 + 2 * explore))))
    chosen: list[str] = []
    for s in order:
        if len(chosen) < k and slot_bucket(s) not in {slot_bucket(c) for c in chosen}:
            chosen.append(s)
    for s in order:
        if len(chosen) < k and s not in chosen:
            chosen.append(s)
    days[date] = {"slots": sorted(chosen), "done": {}}
    for d in sorted(days)[:-45]:
        del days[d]
    state.save("day", days)
    return days[date]


def sample_brief(state: State, cfg: dict, rng: random.Random, slot: str) -> dict:
    scfg = cfg.get("strategy") or {}
    explore = float(scfg.get("explore", 0.2))
    formats = [f for f in (scfg.get("formats") or list(PRIOR["format"])) if f in FORMATS and f != "offre"]
    n_posts = len(state.posts)
    offer = cfg.get("offer") or {}
    every = int(offer.get("pitch_every") or 0)
    since = 0
    for p in reversed(state.posts):
        if (p.get("brief") or {}).get("format") == "offre":
            break
        since += 1
    brief = {"slot": slot_bucket(slot), "slot_exact": slot}
    if every and n_posts >= every - 1 and since >= every - 1 and offer.get("name") and offer.get("points"):
        brief["format"] = "offre"
    else:
        brief["format"] = sample(formats, "format", state, rng, explore)[0]
    brief["hook"] = sample(list(HOOKS), "hook", state, rng, explore)[0]
    brief["length"] = sample(list(LENGTHS), "length", state, rng, explore)[0]
    rem = int(scfg.get("remake_every") or 0)
    if rem and brief["format"] != "offre" and n_posts and (n_posts + 1) % rem == 0:
        scored = [p for p in state.posts if p.get("score") is not None and not p.get("remade")
                  and (now() - dt.datetime.fromisoformat(p["created"])).days >= 4]
        if scored:
            best = max(scored, key=lambda p: p["score"])
            if best["score"] >= 0.5:
                brief["remake_of"] = best["id"]
    return brief


# --------------------------------------------------------------------------- sujet
def _tok(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-zà-ÿ0-9]{3,}", s.lower())}


def novelty_filter(cands: list[dict], state: State) -> list[dict]:
    seen = state.load("seen", {"ids": [], "titles": []})
    ids = set(seen["ids"])
    recent = [_tok(t) for t in seen["titles"][-60:]]
    out = []
    for c in cands:
        if c["id"] in ids:
            continue
        tk = _tok(c["title"])
        if tk and any(len(tk & r) / max(1, len(tk | r)) > 0.6 for r in recent):
            continue
        out.append(c)
    return out


def rank(cands: list[dict], cfg: dict) -> list[dict]:
    kws = [k.lower() for k in (cfg.get("niche") or {}).get("keywords", [])]

    def s(c):
        blob = (c["title"] + " " + " ".join(c["facts"])).lower()
        hit = sum(1 for k in kws if all(w in blob for w in k.split()))
        return (2.0 * hit + math.log10(max(10, c.get("stars") or 10)) + (1.0 if c["source"] == "github" else 0.3))
    return sorted(cands, key=s, reverse=True)


def memo(state: State, n: int = 5) -> str:
    """Résumé des performances, donné au LLM pour qu'il raisonne sur de vraies données."""
    scored = [p for p in state.posts if p.get("score") is not None]
    if len(scored) < 3:
        return "Pas encore assez de statistiques : appuie-toi sur les a priori (listes chiffrées, « Transforme… », vidéos courtes)."

    def line(p):
        tot = {}
        for net, snaps in (p.get("stats") or {}).items():
            s = _latest(snaps)
            if s:
                for k in ("views", "comments", "shares", "saves"):
                    tot[k] = tot.get(k, 0) + (s.get(k) or 0)
        b = p.get("brief") or {}
        return (f"- « {p.get('title', '')[:70]} » [{b.get('format')}, accroche {b.get('hook')}, {int(p.get('duration', 0))} s, {b.get('slot')}] "
                f"score {p['score']:+.2f} — {tot.get('views', 0)} vues, {tot.get('comments', 0)} commentaires, {tot.get('shares', 0)} partages, {tot.get('saves', 0)} enregistrements")
    top = sorted(scored, key=lambda p: -p["score"])
    out = ["MEILLEURES VIDÉOS :"] + [line(p) for p in top[:n]] + ["MOINS BONNES :"] + [line(p) for p in top[-min(n, max(0, len(top) - n)):]]
    for dim, label in (("format", "format"), ("hook", "accroche"), ("length", "longueur"), ("slot", "créneau")):
        a = arm_stats(state, dim)
        if a:
            out.append(f"Score moyen par {label} : " + ", ".join(f"{k} {sum(v) / len(v):+.2f} (n={len(v)})" for k, v in sorted(a.items(), key=lambda kv: -sum(kv[1]) / len(kv[1]))))
    return "\n".join(out)


def pick_topic(state: State, cfg: dict, cands: list[dict], brief: dict, brain=None, log=print) -> dict:
    """Choisit le(s) candidat(s) et l'angle. Renvoie {items, angle, why}."""
    if brief["format"] == "offre":
        return {"items": [], "angle": "présenter la formation", "why": "vidéo d'offre programmée"}
    if brief.get("remake_of"):
        old = next((p for p in state.posts if p["id"] == brief["remake_of"]), None)
        if old and old.get("facts"):
            return {"items": old["facts"], "angle": f"refaire « {old['title']} » avec une accroche et un angle différents",
                    "why": f"reprise d'une vidéo gagnante (score {old['score']:+.2f})", "remake": True}
    pool = rank(novelty_filter(cands, state), cfg)
    if not pool:
        return {"items": [], "angle": "", "why": "aucun candidat nouveau"}
    want = 4 if brief["format"] == "liste" else 2 if brief["format"] == "comparatif" else 1
    short = pool[:14]
    if brain is not None:
        listing = "\n".join(f"{i + 1}. [{c['source']}] {c['title']} — {' | '.join(c['facts'][1:3])[:230]}" for i, c in enumerate(short))
        niche = cfg.get("niche") or {}
        sys_ = ("Tu es le stratège éditorial d'un compte de vidéos courtes. Tu choisis le prochain sujet en t'appuyant sur les statistiques "
                "du compte. Tu réponds uniquement par un objet JSON.")
        line = f"LIGNE ÉDITORIALE (à respecter absolument) : {niche['line']}\n" if niche.get("line") else ""
        usr = (f"NICHE : {niche.get('description')}\nCIBLE : {niche.get('audience')}\n{line}\nSTATISTIQUES DU COMPTE\n{memo(state)}\n\n"
               f"FORMAT IMPOSÉ : {brief['format']} — {FORMATS[brief['format']]}\nACCROCHE IMPOSÉE : {HOOKS[brief['hook']]}\n\n"
               f"CANDIDATS (issus de la veille du jour)\n{listing}\n\n"
               f"Choisis exactement {want} candidat(s) qui intéresseront la cible et qui entrent dans la ligne éditoriale "
               "(s'il y en a plusieurs, ils doivent aller ensemble). "
               "L'angle ne contient AUCUN chiffre, aucune durée, aucune promesse de résultat, et n'affirme aucun lien entre deux outils "
               "qui ne figure pas dans leurs descriptions. "
               'Réponds : {"choix": [numéros], "angle": "l\'angle en une phrase", "pourquoi": "le lien avec les statistiques, en une phrase"}')
        try:
            def val(o):
                idx = [int(x) for x in o.get("choix", []) if str(x).strip().isdigit() and 1 <= int(x) <= len(short)]
                if not idx:
                    raise ValueError("« choix » doit contenir des numéros de la liste")
                return {"items": [short[i - 1] for i in dict.fromkeys(idx)][:want], "angle": str(o.get("angle", ""))[:240],
                        "why": str(o.get("pourquoi", ""))[:300]}
            return brain.ask_json(sys_, usr, validate=val, retries=1, temperature=0.5, max_tokens=1200, purpose="sujet")
        except Exception as e:  # noqa: BLE001 — pas de LLM : classement déterministe
            log(f"stratège : choix du sujet par le LLM impossible ({str(e)[:120]}), classement automatique")
    if brief["format"] == "liste":
        by_kw: dict[str, list[dict]] = {}
        for c in pool:
            if c["source"] == "github":
                by_kw.setdefault(c["kw"], []).append(c)
        if by_kw:
            kw, items = max(by_kw.items(), key=lambda kv: len(kv[1]))
            if len(items) >= 3:
                return {"items": items[:want], "angle": f"les meilleurs outils « {kw} » du moment", "why": "classement automatique"}
    return {"items": pool[:want], "angle": "", "why": "classement automatique"}


def mark_seen(state: State, items: list[dict], title: str) -> None:
    seen = state.load("seen", {"ids": [], "titles": []})
    seen["ids"] = (seen["ids"] + [c["id"] for c in items if c.get("id")])[-600:]
    seen["titles"] = (seen["titles"] + [title])[-200:]
    state.save("seen", seen)
