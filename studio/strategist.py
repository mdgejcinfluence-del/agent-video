"""Le stratège : quoi produire, quand, et ce que disent les mesures.

  1. La SUITE promise par une vidéo publiée passe avant tout (c'est ce qui rend vraie la phrase de fin).
  2. Sinon : une famille de sujets tirée au sort selon ses poids (corrigés par le bilan), puis une idée
     jamais traitée, ou la plus ancienne.
  3. Le type d'accroche est tiré selon ce qui a retenu le public jusqu'ici (essais permanents inclus).
Sans modèle d'écriture, seules les idées qui ont un storyboard de réserve sont possibles.
En mode essai, rien n'est consommé : les réserves tournent pour que tu voies chaque format.
"""
from __future__ import annotations

import datetime as dt
import math
import random
import statistics as st
from pathlib import Path

import yaml

from . import schema
from .state import State, now

HOOKS = schema.HOOKS
N0 = 2.0     # poids de l'a priori (neutre), en « nombre de vidéos »


def slot_bucket(hhmm: str) -> str:
    h = int(hhmm.split(":")[0])
    return "matin" if h < 12 else "midi" if h < 16 else "soir"


def duree_bucket(sec: float) -> str:
    return "moins de 45 s" if sec < 45 else "45 à 60 s" if sec <= 60 else "plus de 60 s"


# --------------------------------------------------------------------------- banque
def banque(root: str | Path) -> dict:
    d = yaml.safe_load((Path(root) / "data" / "sujets.yaml").read_text(encoding="utf-8")) or {}
    toutes = {f["id"]: dict(f) for f in d.get("familles") or []}
    fam = {k: f for k, f in toutes.items() if f.get("actif", True)}           # une famille « actif: false » attend un moyen technique (ex. images)
    return {"familles": fam, "en_attente": {k: f for k, f in toutes.items() if k not in fam},
            "idees": [dict(i) for i in d.get("idees") or [] if i.get("famille") in fam and not i.get("a_verifier")],
            "plancher": float(d.get("plancher", 0.03))}


def idees(root: str | Path, state: State) -> list[dict]:
    """Les idées de la banque, puis celles que le modèle a proposées (state/idees.json)."""
    bq = banque(root)
    out = [dict(i, origine="banque") for i in bq["idees"]]
    seen = {i["id"] for i in out}
    for i in state.load("idees", []):
        if i.get("id") and i["id"] not in seen and i.get("famille") in bq["familles"]:
            out.append(dict(i, origine=i.get("origine") or "modele"))
    return out


def poids(root: str | Path, state: State) -> dict[str, float]:
    bq = banque(root)
    base = {k: float(f.get("poids", 0.1)) for k, f in bq["familles"].items()}
    over = (state.load("bilan", {}) or {}).get("poids") or {}
    w = {k: float(over.get(k, v)) for k, v in base.items()}
    w = {k: max(bq["plancher"], v) for k, v in w.items()}
    tot = sum(w.values()) or 1.0
    return {k: v / tot for k, v in w.items()}


def _used(state: State, days: int) -> list[dict]:
    limit = now() - dt.timedelta(days=days)
    out = []
    for p in state.posts:
        try:
            if dt.datetime.fromisoformat(p["created"]) >= limit:
                out.append(p)
        except (KeyError, ValueError):
            continue
    return out


# --------------------------------------------------------------------------- suites promises
def noter_suite(state: State, post: dict, story: dict) -> None:
    """Chaque vidéo publiée annonce une suite : on l'inscrit, elle sera produite en priorité."""
    s = story.get("suite") or {}
    if not (s.get("sujet") or s.get("reserve")):
        return
    q = state.load("suites", [])
    q.append({"de": post["id"], "title": post.get("title"), "keyword": post.get("keyword"), "promesse": story.get("promesse"),
              "famille": story.get("famille"), "suite": s, "cree": now().isoformat(timespec="seconds"), "faite": None})
    state.save("suites", q[-40:])


def suite_due(state: State, cfg: dict, avec_modele: bool, recents: set[str]) -> dict | None:
    for s in state.load("suites", []):
        if s.get("faite"):
            continue
        if avec_modele and (s["suite"].get("sujet") or s["suite"].get("reserve")):
            return s
        if not avec_modele and s["suite"].get("reserve") and s["suite"]["reserve"] not in recents:
            return s
    return None


def marquer_suite(state: State, de: str, par: str) -> None:
    q = state.load("suites", [])
    for s in q:
        if s.get("de") == de and not s.get("faite"):
            s["faite"] = par
    state.save("suites", q)


# --------------------------------------------------------------------------- choix
def hook_stats(state: State) -> dict[str, list[float]]:
    out: dict[str, list[float]] = {h: [] for h in HOOKS}
    for p in state.posts:
        h = (p.get("brief") or {}).get("hook_type")
        if h in out and p.get("score") is not None:
            out[h].append(p["score"])
    return out


def choisir(root: str | Path, state: State, cfg: dict, faits_ok: dict[str, dict], rng: random.Random, essai: bool = False,
            avec_modele: bool = False, reserves: list[str] | None = None, exclure: set[str] | None = None, sans_suite: bool = False) -> dict | None:
    """La prochaine vidéo : {idee, famille, hook_type, pourquoi, reserve?, suite_de?} — ou None s'il n'y a rien à produire."""
    scfg = cfg.get("strategy") or {}
    bq = banque(root)
    allid = idees(root, state)
    reserves = list(reserves or [])
    if essai:
        # les réserves tournent, dans l'ordre ; rien n'est compté
        pool = [i for i in allid if i.get("reserve") in reserves] or [{"id": r, "famille": "prompts", "sujet": r, "reserve": r} for r in reserves]
        if not pool:
            return None
        k = int(state.load("essais", {"n": 0}).get("n", 0))
        i = pool[k % len(pool)]
        return {"idee": i, "famille": i["famille"], "hook_type": None, "reserve": i.get("reserve"),
                "pourquoi": "mode essai : les réserves tournent pour te montrer chaque format"}
    days = int(scfg.get("repeat_days", 21))
    used = _used(state, days)
    faites = {(p.get("brief") or {}).get("idee") for p in used}
    res_recentes = {(p.get("brief") or {}).get("reserve") for p in used if (p.get("brief") or {}).get("reserve")}
    # 1. la suite promise
    due = None if sans_suite else suite_due(state, cfg, avec_modele, res_recentes)
    if due:
        s = due["suite"]
        idee = {"id": f"suite-{due['de']}", "famille": due.get("famille") if due.get("famille") in bq["familles"] else "prompts", "sujet": s.get("sujet") or due.get("promesse"),
                "suite_de": {"id": due["de"], "title": due.get("title"), "keyword": due.get("keyword")}}
        prevue = next((i for i in allid if s.get("idee") and i["id"] == s["idee"]), None)
        if prevue is not None and all(f in faits_ok for f in (prevue.get("faits") or [])):
            # la vidéo précédente a annoncé CE sujet de la banque : il garde sa famille, son outil, son angle
            idee = {**prevue, "suite_de": idee["suite_de"]}
        if s.get("reserve") and (not avec_modele or not s.get("sujet")):
            idee["reserve"] = s["reserve"]
            match = next((i for i in allid if i.get("reserve") == s["reserve"]), None)
            if match:
                idee.update({"famille": match["famille"], "sujet": match["sujet"], "id": match["id"]})
        return {"idee": idee, "famille": idee["famille"], "hook_type": None if idee.get("reserve") else _hook(state, scfg, rng),
                "reserve": idee.get("reserve"), "suite_de": due["de"],
                "pourquoi": f"suite promise par « {due.get('title')} » (mot {due.get('keyword')})"}

    def possible(i: dict) -> bool:
        if i["id"] in faites or (exclure and i["id"] in exclure):
            return False
        if any(f not in faits_ok for f in (i.get("faits") or [])):
            return False
        if avec_modele:
            return True
        return bool(i.get("reserve")) and i["reserve"] in reserves and i["reserve"] not in res_recentes
    dispo = [i for i in allid if possible(i)]
    if not dispo:
        return None
    if scfg.get("pilotes_d_abord", True) and any(i.get("pilote") for i in dispo):
        dispo = [i for i in dispo if i.get("pilote")]              # la série pilote d'abord ; la famille est tirée parmi ses sujets
    w = poids(root, state)
    fams = sorted({i["famille"] for i in dispo})
    explore = float(scfg.get("explore", 0.25))
    tirage = rng.random()
    if tirage < explore:
        fam = rng.choice(fams)
        why = f"essai : famille « {bq['familles'][fam].get('nom', fam)} » tirée sans tenir compte des poids (part d'essais {explore:.0%})"
    else:
        tot = sum(w.get(f, 0.05) for f in fams)
        x, acc, fam = rng.random() * tot, 0.0, fams[0]
        for f in fams:
            acc += w.get(f, 0.05)
            if x <= acc:
                fam = f
                break
        why = f"famille « {bq['familles'][fam].get('nom', fam)} » (poids {w.get(fam, 0):.0%})"
    cands = [i for i in dispo if i["famille"] == fam]
    cands.sort(key=lambda i: (0 if i.get("origine") == "bilan" else 1, i["id"]))        # les idées nées d'une vidéo qui a marché passent devant
    i = cands[0]
    return {"idee": i, "famille": fam, "hook_type": None if (not avec_modele and i.get("reserve")) else _hook(state, scfg, rng),
            "reserve": i.get("reserve") if not avec_modele else None, "pourquoi": why}


def prochaine(root: str | Path, state: State, cfg: dict, faits_ok: dict[str, dict], rng: random.Random, avec_modele: bool,
              reserves: list[str] | None, exclure: set[str]) -> dict | None:
    """Le sujet de la vidéo SUIVANTE, choisi dès maintenant selon la répartition des familles : la vidéo en cours l'annonce
    dans sa phrase de fin, et l'agent le produit ensuite. Ainsi chaque promesse est tenue ET la répartition est respectée."""
    c = choisir(root, state, cfg, faits_ok, rng, False, avec_modele, reserves, exclure=exclure, sans_suite=True)
    return (c or {}).get("idee")


def _hook(state: State, scfg: dict, rng: random.Random) -> str:
    """Tirage de Thompson avec un a priori neutre : ce qui a mieux retenu le public revient plus souvent, sans exclure le reste."""
    explore = float(scfg.get("explore", 0.25))
    obs = hook_stats(state)
    draws = []
    for h in HOOKS:
        r = obs[h]
        draws.append((rng.gauss(sum(r) / (N0 + len(r)), (1.0 / math.sqrt(N0 + len(r))) * (0.6 + 2.0 * explore)), h))
    return max(draws)[1]


def reste(root: str | Path, state: State, cfg: dict, faits_ok: dict, avec_modele: bool, reserves: list[str]) -> int:
    """Nombre d'idées encore disponibles (pour savoir quand en demander de nouvelles)."""
    days = int((cfg.get("strategy") or {}).get("repeat_days", 21))
    used = _used(state, days)
    faites = {(p.get("brief") or {}).get("idee") for p in used}
    res = {(p.get("brief") or {}).get("reserve") for p in used}
    n = 0
    for i in idees(root, state):
        if i["id"] in faites or any(f not in faits_ok for f in (i.get("faits") or [])):
            continue
        if avec_modele or (i.get("reserve") in reserves and i["reserve"] not in res):
            n += 1
    return n


# --------------------------------------------------------------------------- calendrier
def posterior(values: list[str], dim: str, state: State) -> dict[str, tuple[float, float]]:
    out = {}
    for v in values:
        r = [p["score"] for p in state.posts if (p.get("brief") or {}).get(dim) == v and p.get("score") is not None]
        out[v] = (sum(r) / (N0 + len(r)), 1.0 / math.sqrt(N0 + len(r)))
    return out


def plan_day(state: State, cfg: dict, date: str, rng: random.Random) -> dict:
    days = state.load("day", {})
    if date in days and "slots" in days[date]:
        return days[date]
    sch = cfg.get("schedule", {})
    slots = list(sch.get("slots") or ["10:00", "18:00"])
    jours = [int(x) for x in (sch.get("jours") or [1, 2, 3, 4, 5, 6, 7])]
    try:
        actif = dt.date.fromisoformat(date).isoweekday() in jours
    except ValueError:
        actif = True
    k = min(int(sch.get("videos_per_day", 2)), len(slots)) if actif else 0
    explore = float((cfg.get("strategy") or {}).get("explore", 0.25))
    buckets = posterior(sorted({slot_bucket(s) for s in slots}), "slot", state)
    order = sorted(slots, key=lambda s: -(buckets[slot_bucket(s)][0] + rng.gauss(0, buckets[slot_bucket(s)][1] * (0.6 + 2 * explore))))
    chosen: list[str] = []
    for s in order:                       # au plus un créneau par tranche (matin, midi, soir) si possible
        if len(chosen) < k and slot_bucket(s) not in {slot_bucket(c) for c in chosen}:
            chosen.append(s)
    for s in order:
        if len(chosen) < k and s not in chosen:
            chosen.append(s)
    chosen.sort()
    old = days.get(date) or {}
    days[date] = {"slots": chosen, "done": old.get("done", {})}
    for d in sorted(days)[:-45]:
        del days[d]
    state.save("day", days)
    return days[date]


# --------------------------------------------------------------------------- mesures
def _latest(snaps: list[dict], min_h: float = 20) -> dict | None:
    ok = [s for s in snaps or [] if s.get("h", 0) >= min_h and s.get("views") is not None]
    return ok[-1] if ok else None


def score_posts(state: State, cfg: dict) -> None:
    """post['score'] : 0 = médiane des vidéos du compte sur le même réseau, +1 = deux fois mieux, -1 = deux fois moins bien.

    Les vues ne rapportent rien par elles-mêmes : elles servent de dénominateur (taux de partage, d'enregistrement, de commentaire).
    « watch » est la part de la vidéo réellement regardée, quand le réseau la fournit.
    """
    w = (cfg.get("stats") or {}).get("weights") or {"watch": 0.35, "shares": 0.25, "saves": 0.20, "comments": 0.20}
    groups: dict[str, list[tuple[dict, dict]]] = {}
    for p in state.posts:
        for net, snaps in (p.get("stats") or {}).items():
            s = _latest(snaps)
            if s:
                groups.setdefault(net, []).append((p, s))
    parts: dict[str, list[float]] = {}
    for _net, rows in groups.items():
        if len(rows) < 3:
            continue                                  # pas de comparaison honnête avec moins de 3 vidéos sur ce réseau

        def val(p, s, k):
            if k == "watch":
                return None if s.get("watch") is None or not p.get("duration") else float(s["watch"]) / float(p["duration"])
            return None if s.get(k) is None else (s.get(k) or 0) / max(1, s.get("views") or 0)
        med_views = st.median([s["views"] for _, s in rows]) or 1
        med = {}
        for k in w:
            vals = [v for v in (val(p, s, k) for p, s in rows) if v is not None]
            med[k] = (st.median(vals) if vals else 0) or 1e-4
        for p, s in rows:
            tot, wsum = 0.0, 0.0
            for k, wk in w.items():
                v = val(p, s, k)
                if v is None:
                    continue
                if k != "watch":                      # avec peu de vues, un taux est très bruité : on le rapproche de la médiane
                    v = ((s.get(k) or 0) + med_views * med[k]) / ((s.get("views") or 0) + med_views)
                tot += wk * max(-3.0, min(3.0, math.log2(max(v, 1e-6) / med[k]))); wsum += wk
            if wsum:
                parts.setdefault(p["id"], []).append(tot / wsum)
    for p in state.posts:
        if p["id"] in parts:
            p["score"] = round(sum(parts[p["id"]]) / len(parts[p["id"]]), 3)
            p["score_at"] = now().isoformat(timespec="seconds")
    state.save_posts()


def vues(p: dict) -> int:
    tot = 0
    for snaps in (p.get("stats") or {}).values():
        s = _latest(snaps, 0)
        tot += int((s or {}).get("views") or 0)
    return tot


def memo(state: State) -> str:
    """Ce que le scénariste doit savoir des mesures, en quelques lignes."""
    b = state.load("bilan", {}) or {}
    lines = []
    if b.get("constats"):
        lines += [f"- {c}" for c in b["constats"][:6]]
    scored = sorted([p for p in state.posts if p.get("score") is not None], key=lambda p: -p["score"])
    if len(scored) >= 3:
        lines.append("Vidéos les mieux notées : " + " ; ".join(f"« {p['title']} » ({p['score']:+.1f})" for p in scored[:3]))
        lines.append("Vidéos les moins bien notées : " + " ; ".join(f"« {p['title']} » ({p['score']:+.1f})" for p in scored[-2:]))
    return "\n".join(lines)
