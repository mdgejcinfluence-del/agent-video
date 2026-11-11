"""Le stratège : choisit le public, le sujet, la preuve et l'accroche de la prochaine vidéo, et lit les mesures.

Trois règles, tirées de l'étude de marché du 11 novembre 2026 :
  1. PAS DE PREUVE, PAS DE VIDÉO : un sujet n'est retenu que si un dossier preuves/<id>/ le couvre pour ce public.
  2. UN SEUL PUBLIC PAR VIDÉO, et les deux séries alternent : chaque jour de publication sert les deux publics.
  3. ON NE CHANGE QU'UN FACTEUR À LA FOIS : quand un sujet revient, c'est avec la même preuve et une autre accroche.

Chaque sujet reçoit une note de 0 à 5 (fiche sujet). C'est un outil de tri interne, pas une probabilité de succès :
    problème pour le public 30 % · preuve visuelle réelle 25 % · signal de demande vérifiable 20 %
    adéquation à la formation 15 % · fraîcheur vérifiée 10 %

Les mesures ne désignent jamais une « gagnante » sur les seules vues : la note de qualité d'une vidéo compare la part
regardée, les partages, les enregistrements et les commentaires à ceux des vidéos du MÊME public sur le MÊME réseau.
Les clics et les ventes ne sont pas visibles par l'agent : tant que tu ne les saisis pas, il le dit.
"""
from __future__ import annotations

import datetime as dt
import math
import random
import statistics as st
from pathlib import Path

import yaml

from . import preuves
from .state import State, now

SEGMENTS = ("commercant", "createur_freelance")
HOOKS = ("resultat", "probleme", "contraste")
POIDS = {"probleme": 30, "preuve": 25, "demande": 20, "formation": 15, "fraicheur": 10}
N0 = 2.0     # poids de l'a priori (neutre), en « nombre de vidéos »


def slot_bucket(hhmm: str) -> str:
    h = int(hhmm.split(":")[0])
    return "matin" if h < 11 else "midi" if h < 16 else "soir"


# --------------------------------------------------------------------------- banque de sujets
def banque(root: str | Path) -> dict:
    d = yaml.safe_load((Path(root) / "data" / "sujets.yaml").read_text(encoding="utf-8")) or {}
    poids = {**POIDS, **(d.get("poids") or {})}
    tot = sum(poids.values()) or 1
    return {"poids": {k: v / tot for k, v in poids.items()}, "themes": list(d.get("themes") or ["motion", "visuels", "sites", "contenus"]),
            "sujets": {int(s["n"]): s for s in d.get("sujets") or []}}


def references(root: str | Path, segment: str, n: int) -> list[dict]:
    p = Path(root) / "data" / "references.yaml"
    d = (yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}) or {}
    rows = [dict(r, observe_le=d.get("observe_le"), origine=d.get("source")) for r in d.get("references") or []]
    exact = [r for r in rows if n in (r.get("sujets") or [])]
    return (exact + [r for r in rows if r not in exact and r.get("segment") == segment])[:3]


def _clamp5(x) -> float:
    try:
        return max(0.0, min(5.0, float(x)))
    except (TypeError, ValueError):
        return 0.0


def fiche(sujet: dict, packs: dict[str, dict], state: State, bq: dict, faits_ok: dict[str, dict], veille_items: list[dict] | None = None) -> dict:
    """Fiche sujet : les cinq critères, la note pondérée, et ce qu'on sait ou non (niveau de confiance)."""
    n, seg = int(sujet["n"]), sujet["segment"]
    dispo = preuves.pour_sujet(packs, n, seg)
    pack = dispo[0] if dispo else None
    notes = sujet.get("notes") or {}
    c: dict[str, float] = {"probleme": _clamp5(notes.get("probleme")), "formation": _clamp5(notes.get("formation")),
                           "preuve": float(preuves.note(pack))}
    conf = []
    # demande : tes mesures d'abord (vidéos déjà publiées sur ce sujet), sinon ce que tu as saisi, sinon « inconnu »
    own = [p["score"] for p in state.posts if (p.get("brief") or {}).get("sujet") == n and p.get("score") is not None]
    if own:
        c["demande"] = _clamp5(2.5 + 1.25 * (sum(own) / len(own)))
        conf.append(f"demande : mesurée sur {len(own)} vidéo(s) de ce compte")
    elif sujet.get("demande") not in (None, ""):
        c["demande"] = _clamp5(sujet["demande"])
        conf.append(f"demande : saisie à la main ({sujet.get('demande_source') or 'source non précisée'})")
    else:
        c["demande"] = 0.0
        conf.append("demande : inconnue (aucune recherche, question ou mesure enregistrée) — comptée 0")
    # fraîcheur : faits liés reconfirmés par la veille, actualité récente des outils cités
    lies = [f for f in (sujet.get("faits") or [])]
    ok = [f for f in lies if f in faits_ok]
    kws = [str(k).lower() for k in (sujet.get("veille") or [])]
    recent = 0
    limit = (now() - dt.timedelta(days=14)).strftime("%Y-%m-%d")
    for it in veille_items or []:
        blob = (it.get("title", "") + " " + " ".join(it.get("facts", []))).lower()
        if kws and any(k in blob for k in kws) and str(it.get("date", ""))[:10] >= limit:
            recent += 1
    c["fraicheur"] = (3.0 if lies and len(ok) == len(lies) else 0.0) + (2.0 if recent else 0.0)
    if lies and len(ok) < len(lies):
        conf.append("fraîcheur : " + ", ".join(f for f in lies if f not in ok) + " non reconfirmé(s) par la veille")
    elif lies:
        conf.append(f"fraîcheur : {len(ok)} fait(s) reconfirmé(s) sur les pages officielles")
    else:
        conf.append("fraîcheur : aucun fait d'outil à vérifier pour ce sujet")
    if recent:
        conf.append(f"{recent} actualité(s) d'outil de moins de 14 jours sur ce thème")
    conf.append({0: "preuve : aucun dossier", 2: "preuve : exemple fictif seulement", 4: "preuve : dossier réel, non signé",
                 5: "preuve : dossier réel et signé"}[int(c["preuve"])])
    conf.append("problème et adéquation : estimation éditoriale de départ (data/sujets.yaml)")
    total = sum(bq["poids"][k] * c[k] for k in bq["poids"])
    return {"n": n, "segment": seg, "theme": sujet.get("theme"), "sujet": sujet["sujet"], "hook": sujet.get("hook", ""),
            "preuve_a_montrer": sujet.get("preuve", ""), "formation": sujet.get("formation", ""), "faits": lies,
            "criteres": {k: round(v, 2) for k, v in c.items()}, "note": round(total, 2), "confiance": conf,
            "preuve": pack["id"] if pack else None, "preuves": [p["id"] for p in dispo]}


def fiches(root: str | Path, state: State, faits_ok: dict[str, dict], veille_items: list[dict] | None = None) -> list[dict]:
    bq = banque(root)
    packs = preuves.tous(root)
    return [fiche(s, packs, state, bq, faits_ok, veille_items) for _, s in sorted(bq["sujets"].items())]


# --------------------------------------------------------------------------- choix de la prochaine vidéo
def _used(state: State, days: int) -> list[dict]:
    """Vidéos publiées (ou en attente de validation) récemment : ce qu'il ne faut pas refaire à l'identique."""
    limit = now() - dt.timedelta(days=days)
    out = []
    for p in state.posts + state.load("attente", []):
        try:
            if dt.datetime.fromisoformat(p["created"]) >= limit:
                out.append(p.get("brief") or {})
        except (KeyError, ValueError):
            continue
    return out


def themes_ouverts(all_fiches: list[dict], segment: str, done: set, themes: list[str]) -> list[str]:
    """Ordre de lancement, par public : motion design d'abord, puis visuels, sites, contenus.
    Un thème s'ouvre quand tous les sujets PRODUISIBLES des thèmes précédents ont été traités une fois pour ce public."""
    out = []
    for th in themes:
        out.append(th)
        if any(f["theme"] == th and f["segment"] == segment and f["preuve"] and f["n"] not in done for f in all_fiches):
            break
    return out


def segment_du_creneau(date: str, slots: list[str], slot: str) -> str:
    """Les deux séries alternent : un jour le commerçant ouvre, le lendemain le créateur."""
    try:
        day = dt.date.fromisoformat(date).toordinal()
    except ValueError:
        day = 0
    i = slots.index(slot) if slot in slots else 0
    return SEGMENTS[(day + i) % 2]


def hook_stats(state: State, segment: str) -> dict[str, list[float]]:
    out: dict[str, list[float]] = {h: [] for h in HOOKS}
    for p in state.posts:
        b = p.get("brief") or {}
        if b.get("segment") == segment and b.get("hook_type") in out and p.get("score") is not None:
            out[b["hook_type"]].append(p["score"])
    return out


def _candidats(allf: list[dict], segment: str, themes: list[str], done_topics: set, done_pairs: set, order: list[str]) -> list[tuple[dict, str, str]]:
    ouverts = themes_ouverts(allf, segment, done_topics, themes)
    mine = [f for f in allf if f["segment"] == segment and f["preuve"] and f["theme"] in ouverts]
    out: list[tuple[dict, str, str]] = []
    for f in sorted([f for f in mine if f["n"] not in done_topics], key=lambda f: (themes.index(f["theme"]) if f["theme"] in themes else 99, -f["note"], f["n"])):
        ht = next((h for h in order if (f["n"], h) not in done_pairs), None)
        if ht:
            out.append((f, ht, f"sujet jamais traité, note {f['note']}/5"))
    # un sujet qui revient : d'abord celui qui a été le moins traité, pour que la série ne tourne pas sur un seul sujet
    fois = {n: sum(1 for (m, _h) in done_pairs if m == n) for n in done_topics}
    for f in sorted([f for f in mine if f["n"] in done_topics], key=lambda f: (fois.get(f["n"], 0), -f["note"], f["n"])):
        ht = next((h for h in order if (f["n"], h) not in done_pairs), None)
        if ht:
            out.append((f, ht, "sujet déjà traité : même preuve, nouvelle accroche (un seul facteur change)"))
    return out


def choisir(root: str | Path, state: State, cfg: dict, segment: str, faits_ok: dict[str, dict], rng: random.Random,
            veille_items: list[dict] | None = None, essai: bool = False) -> dict | None:
    """La prochaine vidéo de ce public : {fiche, hook_type, pourquoi, suite, themes} — ou None s'il n'y a rien d'honnête à produire.

    Priorité : 1) un sujet jamais traité, dans l'ordre de lancement des thèmes puis par note ;
               2) un sujet déjà traité, avec la MÊME preuve et une accroche pas encore essayée (un seul facteur change).
    « suite » est la vidéo qui viendrait ensuite dans la même série : c'est elle qui rend vraie la phrase « si tu veux la suite ».
    En mode essai, rien n'est compté comme traité : les sujets tournent pour que tu voies chaque format.
    """
    scfg = cfg.get("strategy") or {}
    bq = banque(root)
    allf = fiches(root, state, faits_ok, veille_items)
    if essai:
        order_f = sorted([f for f in allf if f["segment"] == segment and f["preuve"]], key=lambda f: f["n"])
        if not order_f:
            return None
        k = int(state.load("essais", {"n": 0}).get("n", 0)) // 2            # deux essais par tour : un par public
        f = order_f[k % len(order_f)]
        ht = HOOKS[(k // len(order_f)) % len(HOOKS)]
        nxt = order_f[(k + 1) % len(order_f)]
        return {"fiche": dict(f, hook_type=ht), "hook_type": ht, "pourquoi": "mode essai : les sujets tournent pour te montrer chaque format",
                "suite": None if len(order_f) < 2 else {"n": nxt["n"], "sujet": nxt["sujet"]}, "themes": bq["themes"]}
    used = _used(state, int(scfg.get("repeat_days", 21)))
    done_pairs = {(b.get("sujet"), b.get("hook_type")) for b in used}
    done_topics = {(p.get("brief") or {}).get("sujet") for p in state.posts + state.load("attente", [])}
    explore = float(scfg.get("explore", 0.25))
    obs = hook_stats(state, segment)
    # tirage de Thompson avec un a priori neutre : ce qui a mieux retenu ce public revient plus souvent, sans exclure le reste
    draws = []
    for h in HOOKS:
        r = obs[h]
        draws.append((rng.gauss(sum(r) / (N0 + len(r)), (1.0 / math.sqrt(N0 + len(r))) * (0.6 + 2.0 * explore)), h))
    order = [h for _, h in sorted(draws, reverse=True)]
    cands = _candidats(allf, segment, bq["themes"], done_topics, done_pairs, order)
    if not cands:
        return None
    f, ht, why = cands[0]
    after = _candidats(allf, segment, bq["themes"], done_topics | {f["n"]}, done_pairs | {(f["n"], ht)}, order)
    nxt = next((c for c in after if c[0]["n"] != f["n"]), after[0] if after else None)
    suite = None if nxt is None else {"n": nxt[0]["n"], "sujet": nxt[0]["sujet"], **({"meme_sujet": True} if nxt[0]["n"] == f["n"] else {})}
    return {"fiche": dict(f, hook_type=ht), "hook_type": ht, "pourquoi": why, "suite": suite,
            "themes": themes_ouverts(allf, segment, done_topics, bq["themes"])}


def manques(root: str | Path, state: State, faits_ok: dict[str, dict]) -> list[str]:
    """Ce qu'il faut ajouter pour débloquer des sujets (affiché par « plan » et dans la fiche de production)."""
    out = []
    for f in fiches(root, state, faits_ok):
        if not f["preuve"]:
            out.append(f"sujet {f['n']} ({'commerçant' if f['segment'] == 'commercant' else 'créateur'}) « {f['sujet']} » — preuve à fournir : {f['preuve_a_montrer']}")
    return out


# --------------------------------------------------------------------------- créneaux
def posterior(values: list[str], dim: str, state: State) -> dict[str, tuple[float, float]]:
    obs: dict[str, list[float]] = {}
    for p in state.posts:
        v = (p.get("brief") or {}).get(dim)
        if v and p.get("score") is not None:
            obs.setdefault(v, []).append(p["score"])
    return {v: (sum(obs.get(v, [])) / (N0 + len(obs.get(v, []))), 1.0 / math.sqrt(N0 + len(obs.get(v, [])))) for v in values}


def plan_day(state: State, cfg: dict, date: str, rng: random.Random) -> dict:
    days = state.load("day", {})
    if date in days and "segments" in days[date]:
        return days[date]
    sch = cfg.get("schedule", {})
    slots = list(sch.get("slots") or ["07:30", "18:30"])
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
    days[date] = {"slots": chosen, "segments": {s: segment_du_creneau(date, chosen, s) for s in chosen}, "done": old.get("done", {})}
    for d in sorted(days)[:-45]:
        del days[d]
    state.save("day", days)
    return days[date]


# --------------------------------------------------------------------------- mesures
def _latest(snaps: list[dict], min_h: float = 20) -> dict | None:
    ok = [s for s in snaps or [] if s.get("h", 0) >= min_h and s.get("views") is not None]
    return max(ok, key=lambda s: s["h"]) if ok else None


def score_posts(state: State, cfg: dict) -> None:
    """post['score'] : 0 = médiane des vidéos du même public sur le même réseau, +1 = deux fois mieux, -1 = deux fois moins bien.

    Les vues ne rapportent rien par elles-mêmes : elles servent de dénominateur (taux de partage, d'enregistrement, de commentaire).
    « watch » est la part de la vidéo réellement regardée (durée moyenne vue / durée), quand le réseau la fournit.
    """
    w = (cfg.get("stats") or {}).get("weights") or {"watch": 0.35, "shares": 0.25, "saves": 0.20, "comments": 0.20}
    groups: dict[tuple[str, str], list[tuple[dict, dict]]] = {}
    for p in state.posts:
        seg = (p.get("brief") or {}).get("segment") or "?"
        for net, snaps in (p.get("stats") or {}).items():
            s = _latest(snaps)
            if s:
                groups.setdefault((seg, net), []).append((p, s))
    parts: dict[str, list[float]] = {}
    for (_seg, _net), rows in groups.items():
        if len(rows) < 3:
            continue                                  # pas de comparaison honnête avec moins de 3 vidéos du même public sur ce réseau

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


def ventes(root: str | Path) -> dict:
    """Clics et ventes saisis à la main (data/mesures.yaml) : l'agent ne peut pas les lire tout seul."""
    p = Path(root) / "data" / "mesures.yaml"
    d = (yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}) or {}
    return {str(k): v for k, v in (d.get("videos") or {}).items() if isinstance(v, dict)}


def memo(state: State, root: str | Path | None = None, segment: str | None = None) -> str:
    """Ce que disent les mesures, sans conclure au-delà de ce qu'elles montrent."""
    posts = [p for p in state.posts if segment is None or (p.get("brief") or {}).get("segment") == segment]
    scored = [p for p in posts if p.get("score") is not None]
    lines = []
    if len(scored) < 3:
        lines.append(f"Mesures : {len(scored)} vidéo(s) notée(s)" + (f" pour ce public" if segment else "") +
                     " — pas assez pour comparer (il en faut 3 du même public sur le même réseau). Aucune conclusion.")
    else:
        for h in HOOKS:
            r = [p["score"] for p in scored if (p.get("brief") or {}).get("hook_type") == h]
            if r:
                lines.append(f"Accroche « {h} » : note de qualité moyenne {sum(r) / len(r):+.2f} sur {len(r)} vidéo(s).")
        best = max(scored, key=lambda p: p["score"])
        lines.append(f"Meilleure note de qualité : « {best.get('title', '')[:60]} » ({best['score']:+.2f}). Ce n'est pas une preuve de vente.")
    v = ventes(root) if root else {}
    if v:
        tot = {}
        for pid, m in v.items():
            seg = next(((p.get("brief") or {}).get("segment") for p in state.posts if p["id"] == pid), None) or m.get("segment") or "?"
            t = tot.setdefault(seg, {"clics": 0, "ventes": 0})
            t["clics"] += int(m.get("clics") or 0); t["ventes"] += int(m.get("ventes") or 0)
        lines += [f"Saisi à la main — {seg} : {t['clics']} clic(s), {t['ventes']} vente(s)." for seg, t in tot.items()]
    else:
        lines.append("Clics sur le lien et ventes : non renseignés (data/mesures.yaml). Sans eux, on ne peut pas dire qu'une vidéo « vend ».")
    return "\n".join(lines)
