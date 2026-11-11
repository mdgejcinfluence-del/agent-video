"""La bibliothèque de prompts : chaque instruction montrée dans une vidéo y est rangée, pour préparer l'e-book.

Mémoire : state/bibliotheque.json  {"suivant": 12, "fiches": [ {...}, ... ]}
Lecture : state/BIBLIOTHEQUE.md    (le même contenu, en clair : un tableau, puis une fiche par instruction)

Une fiche : identifiant unique (P-0001), titre, catégorie, outil, type, fonction, prompt complet, exemple d'utilisation,
résultat attendu, résultat obtenu au dernier essai, personnalisation, date de vérification, façon dont elle a été
vérifiée, statut (à vérifier | testé | validé | rejeté), identifiants des vidéos.
Deux instructions identiques pour le même outil ne font qu'une fiche : la vidéo s'ajoute à la fiche existante.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import re
import unicodedata

from . import schema

ORDRE = {"validé": 0, "testé": 1, "à vérifier": 2, "rejeté": 3}


def cle(texte: str, outil: str) -> str:
    s = unicodedata.normalize("NFD", f"{outil}|{texte}".lower())
    s = re.sub(r"[^a-z0-9]+", " ", "".join(c for c in s if unicodedata.category(c) != "Mn")).strip()
    return hashlib.sha1(s.encode()).hexdigest()[:14]


def charger(state) -> dict:
    lib = state.load("bibliotheque", {"suivant": 1, "fiches": []}) or {}
    lib.setdefault("suivant", 1)
    lib.setdefault("fiches", [])
    return lib


def enregistrer(state, story: dict, video_id: str, cfg: dict, qualite_ok: bool, publiee: bool = False, familles: dict | None = None, log=print) -> list[str]:
    """Range les fiches du storyboard. « validé » = vérifiée ET montrée dans une vidéo qui a passé tous ses contrôles."""
    lib = charger(state)
    today = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    fam = story.get("famille") or ""
    cat = ((familles or {}).get(fam) or {}).get("nom") or fam
    ids = []
    for f in story.get("prompts") or []:
        k = cle(f.get("texte", ""), f.get("outil", ""))
        fiche = next((x for x in lib["fiches"] if x.get("cle") == k), None)
        if fiche is None:
            fiche = {"id": f"P-{int(lib['suivant']):04d}", "cle": k, "cree_le": today, "videos": []}
            lib["suivant"] = int(lib["suivant"]) + 1
            lib["fiches"].append(fiche)
        statut = f.get("statut") if f.get("statut") in schema.STATUTS else "à vérifier"
        if statut == "testé" and qualite_ok:
            statut = "validé"
        ancien = fiche.get("statut")
        if ancien == "validé" and statut == "à vérifier":
            statut = "validé"                                    # un essai sans clé ne défait pas une vérification déjà faite
        fiche.update({
            "titre": f.get("titre"), "categorie": cat, "famille": fam, "outil": f.get("outil"), "type": f.get("type") or "prompt",
            "fonction": f.get("fonction"), "prompt": f.get("texte"),
            "exemple": {"valeurs": f.get("exemple") or {}, "instruction_envoyee": schema.remplir(f.get("texte", ""), f.get("exemple") or {})},
            "resultat_attendu": f.get("resultat_attendu"), "personnalisation": f.get("personnalisation"), "statut": statut,
        })
        if f.get("statut") in ("testé", "validé", "rejeté") or not fiche.get("verification"):
            fiche["verification"] = f.get("verification") or "non vérifié"
            fiche["date_verification"] = f.get("teste_le") or (today if f.get("statut") in ("testé", "rejeté") else "")
            fiche["teste_sur"] = f.get("teste_sur") or ""
        if f.get("resultat_exemple") and f.get("statut") in ("testé", "validé"):
            fiche["resultat_obtenu"] = str(f["resultat_exemple"])[:3000]
        v = {"id": video_id, "le": today, "publiee": bool(publiee)}
        fiche["videos"] = [x for x in fiche.get("videos") or [] if x.get("id") != video_id] + [v]
        ids.append(fiche["id"])
    state.save("bibliotheque", lib)
    ecrire_catalogue(state, lib)
    if ids:
        log(f"bibliothèque : {len(ids)} fiche(s) rangée(s) ({', '.join(ids)}) — {len(lib['fiches'])} au total")
    return ids


def resume(lib: dict) -> dict:
    out = {s: 0 for s in schema.STATUTS}
    for f in lib.get("fiches") or []:
        out[f.get("statut") if f.get("statut") in out else "à vérifier"] += 1
    return out


def _cell(x) -> str:
    return re.sub(r"\s+", " ", str(x or "—")).replace("|", "/").strip()


def catalogue(lib: dict) -> str:
    fiches = sorted(lib.get("fiches") or [], key=lambda f: (ORDRE.get(f.get("statut"), 9), f.get("famille") or "", f.get("id") or ""))
    r = resume(lib)
    L = ["# Bibliothèque de prompts", "",
         f"{len(fiches)} fiche(s) : {r['validé']} validée(s), {r['testé']} testée(s), {r['à vérifier']} à vérifier, {r['rejeté']} rejetée(s).", "",
         "- **validé** : vérifiée, et montrée dans une vidéo qui a passé tous ses contrôles. C'est ce qui peut entrer dans l'e-book.",
         "- **testé** : vérifiée aujourd'hui (essai réel sur Gemini pour un prompt ; page officielle relue pour une commande ou un réglage).",
         "- **à vérifier** : écrite, pas encore vérifiée (pas de clé Gemini, ou page officielle non confirmée). Jamais publiée dans cet état.",
         "- **rejeté** : l'essai a échoué ou la réponse était inutilisable.", ""]
    if not fiches:
        return "\n".join(L + ["Aucune fiche pour l'instant."]) + "\n"
    L += ["| Identifiant | Titre | Catégorie | Outil | Type | Statut | Vérification | Date | Vidéos |", "|---|---|---|---|---|---|---|---|---|"]
    for f in fiches:
        L.append(f"| {f.get('id')} | {_cell(f.get('titre'))} | {_cell(f.get('categorie'))} | {_cell(f.get('outil'))} | {_cell(f.get('type'))} | {_cell(f.get('statut'))} | "
                 f"{_cell(f.get('verification'))} | {_cell(f.get('date_verification'))} | {', '.join(v.get('id', '') for v in f.get('videos') or []) or '—'} |")
    for f in fiches:
        ex = f.get("exemple") or {}
        vals = ", ".join(f"[{k}] = {v}" for k, v in (ex.get("valeurs") or {}).items()) or "aucun champ à remplacer"
        L += ["", f"## {f.get('id')} — {_cell(f.get('titre'))}", "",
              f"- **Catégorie** : {_cell(f.get('categorie'))} · **Outil** : {_cell(f.get('outil'))} · **Type** : {_cell(f.get('type'))}",
              f"- **Fonction recherchée** : {_cell(f.get('fonction'))}",
              f"- **Statut** : {_cell(f.get('statut'))} — {_cell(f.get('verification'))}" + (f" ({_cell(f.get('teste_sur'))})" if f.get("teste_sur") else "")
              + (f", le {f.get('date_verification')}" if f.get("date_verification") else ""),
              f"- **Vidéo(s)** : {', '.join(v.get('id', '') + (' (publiée)' if v.get('publiee') else ' (essai)') for v in f.get('videos') or []) or '—'}", "",
              "**Prompt complet**", "", "```", str(f.get("prompt") or ""), "```", "",
              f"**Exemple d'utilisation** : {vals}", "",
              f"**Résultat attendu** : {_cell(f.get('resultat_attendu'))}", "",
              f"**Personnalisation** : {_cell(f.get('personnalisation'))}"]
        if f.get("resultat_obtenu"):
            L += ["", "**Résultat obtenu au dernier essai** (extrait)", "", "```", str(f["resultat_obtenu"])[:1200], "```"]
    return "\n".join(L) + "\n"


def ecrire_catalogue(state, lib: dict | None = None):
    lib = lib or charger(state)
    p = state.dir / "BIBLIOTHEQUE.md" if hasattr(state, "dir") else None
    if p is not None:
        p.write_text(catalogue(lib), encoding="utf-8")
    return p
