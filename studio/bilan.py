"""Le bilan automatique : tous les trois jours, l'agent relit ses mesures et corrige sa route tout seul.

  1. Relevé des statistiques de chaque vidéo par l'API du réseau (Buffer, Meta, TikTok) — fait à chaque réveil.
  2. Note de chaque vidéo (strategist.score_posts) : rétention, partages, enregistrements, commentaires, jamais les vues seules.
  3. Par famille de sujets, type d'accroche, créneau et durée : combien de vidéos, quelle note moyenne.
  4. Décisions, bornées : le poids d'une famille monte ou descend d'au plus « pas_max » ; aucune famille ne disparaît ;
     une vidéo nettement au-dessus du lot donne naissance à une variante (comme le font les comptes qui grandissent).
  5. Avec Gemini : un diagnostic en clair et de nouvelles idées dans les familles qui marchent.
  6. Tout est écrit dans state/bilan.json et dans state/BILAN.md, lisible sur GitHub.
Avec moins de « minimum_videos » vidéos mesurées, le bilan constate et ne change rien : pas de conclusion sur du bruit.
"""
from __future__ import annotations

import datetime as dt
import math
import re
from pathlib import Path

from . import schema, strategist
from .state import now

DIMS = (("famille", "Famille"), ("hook_type", "Accroche"), ("slot", "Créneau"), ("duree", "Durée"))


def du(state, cfg: dict) -> bool:
    b = state.load("bilan", {}) or {}
    every = int((cfg.get("bilan") or {}).get("tous_les_jours", 3))
    try:
        return (now() - dt.datetime.fromisoformat(b["fait_le"])).total_seconds() >= every * 86400 - 3600
    except (KeyError, ValueError):
        return True


def _groupes(posts: list[dict]) -> dict[str, dict[str, list[dict]]]:
    out: dict[str, dict[str, list[dict]]] = {d: {} for d, _ in DIMS}
    for p in posts:
        b = dict(p.get("brief") or {})
        b["duree"] = strategist.duree_bucket(float(p.get("duration") or 0))
        for d, _ in DIMS:
            if b.get(d):
                out[d].setdefault(str(b[d]), []).append(p)
    return out


def faire(state, cfg: dict, root: str | Path, brain=None, log=print, faits_ok: dict | None = None) -> dict:
    bcfg = cfg.get("bilan") or {}
    mini = int(bcfg.get("minimum_videos", 4))
    pas = float(bcfg.get("pas_max", 0.35))
    strategist.score_posts(state, cfg)
    posts = [p for p in state.posts if p.get("published")]
    notes = [p for p in posts if p.get("score") is not None]
    bq = strategist.banque(root)
    avant = strategist.poids(root, state)
    g = _groupes(notes)
    tableau: dict[str, list[dict]] = {}
    for d, _nom in DIMS:
        rows = []
        for k, ps in g[d].items():
            sc = [p["score"] for p in ps]
            rows.append({"valeur": k, "n": len(ps), "note": round(sum(sc) / len(sc), 2), "vues": int(sum(strategist.vues(p) for p in ps) / len(ps))})
        tableau[d] = sorted(rows, key=lambda r: -r["note"])
    constats, decisions = [], []
    apres = dict(avant)
    if len(notes) < mini:
        constats.append(f"{len(notes)} vidéo(s) mesurée(s) sur {len(posts)} publiée(s) : il en faut {mini} pour tirer une conclusion. Rien n'est changé.")
    else:
        for r in tableau["famille"]:
            f = r["valeur"]
            if f not in apres or r["n"] < 2:
                continue
            k = 1 + pas * math.tanh(r["note"])                     # +1 de note (deux fois mieux que la médiane) ≈ +27 % de poids
            apres[f] = apres[f] * k
            if abs(k - 1) >= 0.05:
                decisions.append(f"famille « {bq['familles'][f].get('nom', f)} » : note {r['note']:+.2f} sur {r['n']} vidéos -> poids {'augmenté' if k > 1 else 'réduit'} de {abs(k - 1):.0%}")
        apres = {k: max(bq["plancher"], v) for k, v in apres.items()}
        tot = sum(apres.values()) or 1
        apres = {k: round(v / tot, 4) for k, v in apres.items()}
        for d, nom in DIMS[1:]:
            rows = [r for r in tableau[d] if r["n"] >= 2]
            if len(rows) >= 2 and rows[0]["note"] - rows[-1]["note"] >= 0.3:
                constats.append(f"{nom} : « {rows[0]['valeur']} » fait mieux ({rows[0]['note']:+.2f} sur {rows[0]['n']} vidéos) que « {rows[-1]['valeur']} » ({rows[-1]['note']:+.2f} sur {rows[-1]['n']}).")
    # une vidéo nettement au-dessus du lot -> une variante est ajoutée aux idées (une seule fois par vidéo)
    extra = state.load("idees", [])
    connus = {i.get("source") for i in extra}
    variantes = []
    for p in sorted(notes, key=lambda p: -p["score"])[:2]:
        if len(notes) >= mini and p["score"] >= 0.5 and p["id"] not in connus:
            b = p.get("brief") or {}
            idee = {"id": f"v-{p['id']}", "famille": b.get("famille") or "prompts", "sujet": f"Variante de « {p['title']} » : même sujet, autre angle, autres exemples",
                    "angle": "reprendre ce qui a retenu le public (le sujet), changer l'accroche et les exemples ; ne pas répéter les phrases",
                    "origine": "bilan", "source": p["id"], "faits": p.get("faits") or []}
            extra.append(idee); variantes.append(idee)
            decisions.append(f"« {p['title']} » (note {p['score']:+.2f}) : une variante est ajoutée en tête des idées")
    # commentaires : le mot le plus commenté dit quelle suite est attendue
    coms = sorted(((sum(int((strategist._latest(s, 0) or {}).get("comments") or 0) for s in (p.get("stats") or {}).values()), p) for p in posts), key=lambda x: -x[0])
    if coms and coms[0][0] > 0:
        constats.append(f"Mot le plus commenté : {coms[0][1].get('keyword')} ({coms[0][0]} commentaires sur « {coms[0][1].get('title')} »).")
    diagnostic, nouvelles = "", []
    if brain is not None and brain.available() and len(notes) >= mini:
        try:
            diagnostic, nouvelles = _avis(brain, cfg, bq, tableau, notes, faits_ok or {}, log)
            for i in nouvelles:
                extra.append(i)
            if nouvelles:
                decisions.append(f"{len(nouvelles)} nouvelle(s) idée(s) proposée(s) par le modèle dans les familles qui marchent")
        except Exception as e:  # noqa: BLE001 — le bilan chiffré reste valable sans l'avis du modèle
            log(f"bilan : avis du modèle indisponible ({type(e).__name__}: {str(e)[:120]})")
    if variantes or nouvelles:
        state.save("idees", extra[-120:])
    rapport = {"fait_le": now().isoformat(timespec="seconds"), "videos_publiees": len(posts), "videos_mesurees": len(notes), "poids_avant": {k: round(v, 4) for k, v in avant.items()},
               "poids": apres, "tableau": tableau, "constats": constats, "decisions": decisions, "diagnostic": diagnostic,
               "prochain": (now() + dt.timedelta(days=int(bcfg.get("tous_les_jours", 3)))).strftime("%Y-%m-%d")}
    hist = (state.load("bilan", {}) or {}).get("historique", [])
    hist.append({"le": rapport["fait_le"][:10], "mesurees": len(notes), "poids": apres})
    rapport["historique"] = hist[-30:]
    state.save("bilan", rapport)
    (Path(state.dir) / "BILAN.md").write_text(texte(rapport, bq, notes), encoding="utf-8")
    log(f"bilan : {len(notes)} vidéo(s) mesurée(s), {len(decisions)} décision(s)" + ("" if decisions else " — rien à changer pour l'instant") + f" ; prochain bilan le {rapport['prochain']}")
    for dline in decisions:
        log(f"bilan : {dline}")
    return rapport


def _avis(brain, cfg: dict, bq: dict, tableau: dict, notes: list[dict], faits_ok: dict, log) -> tuple[str, list[dict]]:
    lignes = ["Mesures du compte (note 0 = médiane du compte ; +1 = deux fois mieux ; -1 = deux fois moins bien) :"]
    for d, nom in DIMS:
        lignes.append(f"{nom} : " + " ; ".join(f"{r['valeur']} = {r['note']:+.2f} sur {r['n']} vidéos, {r['vues']} vues en moyenne" for r in tableau[d]))
    lignes.append("Vidéos, de la mieux notée à la moins bien notée :")
    for p in sorted(notes, key=lambda p: -p["score"])[:14]:
        b = p.get("brief") or {}
        lignes.append(f"- {p['score']:+.2f} | {b.get('famille')} | accroche {b.get('hook_type')} | {p.get('duration')} s | « {p['title']} »")
    lignes.append("Familles possibles : " + ", ".join(f"{k} ({f.get('nom')})" for k, f in bq["familles"].items()))
    lignes.append("Faits vérifiés disponibles (seuls outils qu'une idée peut nommer) : " + (", ".join(f"{k} [{', '.join(f.get('outils') or [])}]" for k, f in faits_ok.items()) or "aucun"))
    system = ("Tu analyses les mesures d'un compte de vidéos courtes spécialisé dans les prompts, les commandes et les techniques d'intelligence artificielle "
              "(public : des jeunes francophones débutants). Réponds par un objet JSON : "
              '{"diagnostic": 4 à 6 phrases simples en français : ce qui marche, ce qui ne marche pas, ce qu\'il faut essayer ; sans jargon et sans promesse, '
              '"idees": 3 à 5 nouvelles idées de vidéo {"famille": identifiant de famille, "outil": UN outil (ChatGPT, Gemini ou Claude, sauf fait vérifié), '
              '"sujet": le sujet en une phrase (« Le prompt pour… », « La commande qui… »), "angle": ce que l\'instruction demande et ce qu\'elle rend, "faits": identifiants des faits nécessaires}}. '
              "Chaque idée doit contenir une instruction concrète à copier, comprise vite, dont le résultat donne envie de tester, et qui n'existe pas déjà dans les vidéos listées. "
              "Jamais une promesse de revenu ou d'audience, jamais une commande ou une fonction d'outil sans fait vérifié, jamais un conseil général sans instruction.")
    obj = brain.ask_json(system, "\n".join(lignes), niveau="ecriture", temperature=0.6, max_tokens=4096, retries=1, purpose="bilan")
    diag = re.sub(r"\s+", " ", str(obj.get("diagnostic") or "")).strip()[:900]
    out = []
    stamp = now().strftime("%Y%m%d")
    for k, i in enumerate(obj.get("idees") or []):
        if not isinstance(i, dict) or i.get("famille") not in bq["familles"]:
            continue
        sujet = re.sub(r"\s+", " ", str(i.get("sujet") or "")).strip()
        faits = [f for f in (i.get("faits") or []) if f in faits_ok]
        if not 12 <= len(sujet) <= 140:
            continue
        from . import garde
        test = {"scenes": [], "legende": {"accroche": sujet, "points": [str(i.get("angle") or "")], "limite": ""}, "faits": faits, "title": sujet, "promesse": "la suite"}
        if garde.controle(test, cfg, faits_ok):
            continue                                                   # idée qui promet ou qui nomme un outil sans fait : écartée
        out.append({"id": f"g-{stamp}-{k + 1}", "famille": i["famille"], "sujet": sujet, "angle": str(i.get("angle") or "")[:200], "faits": faits, "origine": "modele"})
    return diag, out[:5]


def texte(r: dict, bq: dict, notes: list[dict]) -> str:
    L = [f"# Bilan du {r['fait_le'][:10]}", "",
         f"Vidéos publiées : **{r['videos_publiees']}** · mesurées et notées : **{r['videos_mesurees']}** · prochain bilan : {r['prochain']}", "",
         "La note d'une vidéo compare sa rétention, ses partages, ses enregistrements et ses commentaires à la médiane du compte sur le même réseau "
         "(0 = dans la médiane, +1 = deux fois mieux, −1 = deux fois moins bien). Les vues seules ne désignent jamais une gagnante.", ""]
    if r.get("diagnostic"):
        L += ["## Diagnostic", "", r["diagnostic"], ""]
    L += ["## Constats", ""] + ([f"- {c}" for c in r["constats"]] or ["- Rien de marquant."]) + [""]
    L += ["## Décisions prises par l'agent", ""] + ([f"- {d}" for d in r["decisions"]] or ["- Aucune : pas assez de mesures, ou rien qui justifie un changement."]) + [""]
    L += ["## Poids des familles de sujets", "", "| Famille | Avant | Après |", "|---|---|---|"]
    for k, v in sorted(r["poids"].items(), key=lambda x: -x[1]):
        L.append(f"| {bq['familles'].get(k, {}).get('nom', k)} | {r['poids_avant'].get(k, 0):.0%} | {v:.0%} |")
    for d, nom in DIMS:
        rows = r["tableau"].get(d) or []
        if rows:
            L += ["", f"## Par {nom.lower()}", "", "| Valeur | Vidéos | Note moyenne | Vues moyennes |", "|---|---|---|---|"]
            L += [f"| {x['valeur']} | {x['n']} | {x['note']:+.2f} | {x['vues']} |" for x in rows]
    if notes:
        L += ["", "## Vidéos", "", "| Note | Vues | Famille | Titre |", "|---|---|---|---|"]
        for p in sorted(notes, key=lambda p: -p["score"]):
            L.append(f"| {p['score']:+.2f} | {strategist.vues(p)} | {(p.get('brief') or {}).get('famille', '')} | {p['title']} |")
    return "\n".join(L) + "\n"
