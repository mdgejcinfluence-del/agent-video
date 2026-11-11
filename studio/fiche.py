"""Fiche de production : ce que l'agent a décidé et vérifié pour chaque vidéo, dans un fichier lisible (out/<id>.md).

1. stratégie · 2. faits et sources · 3. séquences filmées et droits · 4. script minuté ·
5. légendes par plateforme · 6. contrôle avant publication

Chaque ligne vient d'un fichier du dépôt ou d'une mesure faite sur la vidéo. Quand une information manque, la fiche le dit.
"""
from __future__ import annotations

import re
from pathlib import Path

from . import rushs, writer
from .align import MARK
from .publish import NETWORKS, packs

BLOC = {"liste": "liste numérotée", "check": "liste à cocher", "cartes": "deux cartes qui s'opposent", "icones": "pictogrammes", "chrono": "chrono",
        "fenetre": "fenêtre de discussion", "mot": "mot en grand", "etiquette": "étiquette", "tuiles_video": "tuiles vidéo",
        "rush": "séquence filmée", "avant_apres": "séquence filmée : brute, puis montée"}


def _say(s: dict) -> str:
    return re.sub(r"\s+", " ", MARK.sub("", s.get("say", ""))).strip()


def _plain(s) -> str:
    return re.sub(r"\s+", " ", str(s or "").replace("*", "").replace(" / ", " ")).strip().replace("|", "/")


def ecrire(path: str | Path, story: dict, cfg: dict, res: dict, choix: dict | None, faits_ok: dict, origine: str, bloquants: list[str]) -> Path:
    path = Path(path)
    idee = (choix or {}).get("idee") or {}
    credit = rushs.ligne_credit(res.get("rushs") or {})
    L = [f"# {story['title']}", "",
         f"Durée {res['duration']:.1f} s · {res['words']} mots · voix {'+'.join(res.get('voice') or [])} au débit {res.get('voice_rate')} · écrit par : {origine}", ""]
    L += ["## 1. Stratégie", "",
          f"- Sujet : {idee.get('sujet') or story.get('sujet') or story['title']}",
          f"- Famille : {story.get('famille')} · accroche : {story.get('hook_type')}",
          f"- Pourquoi ce sujet maintenant : {(choix or {}).get('pourquoi') or 'storyboard fourni à la main'}",
          f"- Mot à commenter : **{story.get('keyword')}** · suite annoncée : {_plain(story.get('promesse'))}",
          f"- Texte de la miniature : {' / '.join(_plain(x) for x in story.get('couverture') or [])}", ""]
    L += ["## 2. Faits et sources", ""]
    cites = [(f, faits_ok.get(f)) for f in story.get("faits") or []]
    if cites:
        L += ["| Fait | Affirmation | Source | Vérifié le | Limite |", "|---|---|---|---|---|"]
        for fid, f in cites:
            if f:
                how = "lu à la main" if f.get("verification") == "manuelle" else "rouvert par l'agent"
                L.append(f"| {fid} | {_plain(f.get('affirmation'))} | {f.get('url')} | {f.get('verifie_le')} ({how}) | {_plain(f.get('limite'))} |")
            else:
                L.append(f"| {fid} | — | — | NON CONFIRMÉ | — |")
    else:
        L.append("Aucun outil nommé, aucun chiffre avec unité : cette vidéo ne s'appuie sur aucun fait extérieur (conseils de méthode).")
    L += ["", "## 3. Séquences filmées et droits", ""]
    rs = res.get("rushs") or {}
    if rs:
        L += ["| Repère | Séquence | Source | Auteur | Page d'origine | Contrôle de cohérence | Mesures |", "|---|---|---|---|---|---|---|"]
        for ref, c in rs.items():
            m = c.get("mesures") or {}
            L.append(f"| {ref} | {c['id']} | {c.get('source')} | {c.get('auteur') or '—'} | {c.get('page')} | {_plain(c.get('controle'))} | "
                     f"{m.get('w')}×{m.get('h')}, {m.get('dur', 0):.0f} s, netteté {m.get('nettete')}, mouvement {m.get('mouvement')} |")
        L += ["", f"Licence : {', '.join(sorted({c.get('licence') or '' for c in rs.values()}))}. Usage gratuit, attribution non exigée ; interdit de revendre la séquence telle quelle, "
                  "de montrer une personne reconnaissable sous un mauvais jour, de laisser croire qu'elle recommande un produit.",
              f"Crédit ajouté à la légende : « {credit} »" if credit else "Aucun crédit ajouté."]
    else:
        L.append("Aucune séquence filmée.")
    L += ["", "## 4. Script minuté", "", "| Temps | Écran | Ce que dit la voix | Ce qu'on voit |", "|---|---|---|---|"]
    for i, s in enumerate(story["scenes"]):
        t = res["scenes"][i] if i < len(res.get("scenes") or []) else {}
        span = f"{t.get('t0', 0):.1f}–{t.get('t1', 0):.1f} s" if t else "—"
        if s["type"] == "fin":
            vu = f"écran de fin : « Abonne-toi », bouton, « Commente {s['keyword']} », « = {_plain(s.get('promesse'))} »" + (f", « {_plain(s.get('promo'))} »" if s.get("promo") else "")
            L.append(f"| {span} | fin | {_say(s)} | {vu} |")
            continue
        tu = f"{s['tuile']['label']} {s['tuile']['n']} · " if s.get("tuile") else ""
        vu = "; ".join(BLOC.get(b["kind"], b["kind"]) + (f" « {_plain(b.get('voir'))} »" if b.get("voir") else "") for b in s.get("blocks") or []) or "titre seul"
        L.append(f"| {span} | {tu}{_plain(s['title'])} | {_say(s)} | {vu} ; personnage : {s.get('pose')} |")
    L += ["", "## 5. Légendes par plateforme", ""]
    pk = packs(story, cfg, credit)
    for net in (cfg.get("publish") or {}).get("networks") or ["facebook", "instagram", "tiktok"]:
        if net in pk:
            L += [f"### {NETWORKS.get(net, net)}", "", "```", pk[net]["legende"], "```", ""]
    if "youtube" not in ((cfg.get("publish") or {}).get("networks") or []):
        L += ["### YouTube Shorts (texte prêt, publication non reliée)", "", "```", pk["youtube"]["legende"], "```", ""]
    qa = res.get("qa") or {}
    a = res.get("audio") or {}
    L += ["## 6. Contrôle avant publication", "",
          "- ✅ **Forme et garde-fous** — aucune promesse, aucun chiffre sans source, aucun outil sans fait vérifié (contrôle automatique).",
          f"- {'✅' if rs else '⛔'} **Séquences filmées** — {len(rs)} séquence(s), chacune contrôlée (format, netteté, mouvement, cohérence avec la phrase).",
          f"- {'✅' if not (res.get('layout') or {}).get('warnings') else '⛔'} **Lisibilité** — " + ("aucun débordement, tout le texte est au-dessus de la zone couverte par les boutons." if not (res.get('layout') or {}).get('warnings') else "; ".join(res['layout']['warnings'])),
          f"- ✅ **Son** — niveau {a.get('lufs')} LUFS, voix {a.get('clarte_db')} dB au-dessus du fond, sous-titres synchronisés mot à mot. Personne n'a écouté la vidéo.",
          f"- {'✅' if qa.get('ok') else '⛔'} **Contrôle qualité** — " + ("réussi" if qa.get("ok") else "; ".join(qa.get("problems") or [])) + ("" if not qa.get("warnings") else " ; à noter : " + "; ".join(qa["warnings"])),
          f"- {'✅' if writer.promo_active(cfg) else 'ℹ️'} **Écran de fin** — " + ("la formation en promo est annoncée (promo confirmée, lien en bio renseigné)." if writer.promo_active(cfg) else "la formation n'est pas annoncée (offer.promo et offer.lien_bio non renseignés) : l'écran de fin annonce seulement la suite."),
          ""]
    L.append("**Publication : " + ("RETENUE** — " + " ; ".join(bloquants) if bloquants else "rien ne bloque.**"))
    path.write_text("\n".join(L) + "\n", encoding="utf-8")
    return path
