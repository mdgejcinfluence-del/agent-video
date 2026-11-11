"""Garde-fous : ce qu'une vidéo n'a pas le droit de dire. Appliqués à TOUT storyboard, écrit par un modèle ou pris en réserve.

L'agent publie seul : ces contrôles sont donc automatiques et sans exception.
  1. Aucune promesse de revenu, de vues, de résultat garanti ; aucune astuce de contournement.
  2. Aucune expérience personnelle inventée (« j'ai testé », « mes clients ») : le compte ne ment pas sur ce qu'il a fait.
  3. Aucun envoi promis en privé : l'agent ne sait pas envoyer de message.
  4. Tout outil nommé et tout chiffre (prix, durée, pourcentage, audience) doit venir d'un fait vérifié sur une page
     officielle (data/faits.yaml), cité dans le storyboard et confirmé par la veille.
  5. « Gratuit » seulement si un fait cité le dit, et la limite est écrite dans la légende.
  6. Une séquence de banque d'images n'est jamais présentée comme un client, un résultat ou un témoignage.
"""
from __future__ import annotations

import re
import unicodedata

from . import schema


def _n(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s).lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn").replace("’", "'")


INTERDITS = [
    (r"\bj'ai (teste|essaye|gagne|vendu|utilise|obtenu|decouvert)\b", "expérience personnelle invérifiable (« j'ai testé / j'ai gagné… ») : le compte n'a rien testé lui-même"),
    (r"\b(mes|mon|ma) (clients?|eleves?|abonnes?|boutique|chiffre)\b", "référence à des clients, des élèves ou une boutique qui n'existent pas"),
    (r"\bje t'envoie\b|\ben (message )?prive\b|\ben dm\b|\bdans tes dm\b|\binbox\b|\bje te reponds en\b", "promesse d'envoi en privé : l'agent ne sait pas envoyer de message"),
    (r"\b(gagne[rsz]?|gagnant) (de l'argent|\d|des milliers|des millions)|\brevenus?\b|\bchiffre d'affaires\b|\bdevenir riche\b|\bmillionnaire\b|\brentabilis", "promesse de revenu"),
    (r"\bgaranti[es]?\b|\bassure[es]? de\b|\ba coup sur\b|\bsans effort\b|\bsans rien faire\b", "résultat garanti ou sans effort"),
    (r"\bviral[es]?\b|\bvirales\b|\bbuzz\b|\bexplos(e|er|ent) (tes|les|vos) (vues|ventes)|\bdes milliers de vues\b|\bpercer\b", "promesse d'audience (viral, percer, des milliers de vues)"),
    (r"\ba l'infini\b|\billimite[es]?\b|\b100 ?% gratuit", "« illimité », « à l'infini », « 100 % gratuit » : aucune offre ne l'est sans condition"),
    (r"\bvpn\b|\bcontourn|\bcrack|\bpirat|\bsans (filigrane|watermark)\b|\bfaux (avis|comptes?|temoignages?)\b|\b(e-?mail|adresse) (jetable|temporaire)\b|\bessais? gratuits? (en )?illimite", "astuce de contournement des règles d'un service"),
    (r"\bdeepfake\b|\bcloner? (la|une|sa|ta) voix\b|\busurp", "imitation d'une personne réelle"),
    (r"\bremplace[rsz]? (un|ton|le|les) (monteur|graphiste|developpeur|salarie)", "promesse de remplacer un métier"),
    (r"\bplus que \d+ places?\b|\bderniere chance\b|\boffre expire\b", "fausse urgence"),
    (r"\ben \d+ (secondes?|minutes?|clics?) seulement\b", "durée promise"),
]
# outils et services : en parler demande un fait vérifié qui les couvre (champ « outils » du fait)
OUTILS = ["chatgpt", "gpt", "openai", "claude", "anthropic", "gemini", "copilot", "grok", "mistral", "deepseek", "midjourney", "dall-e", "sora", "veo",
          "runway", "kling", "pika", "heygen", "elevenlabs", "capcut", "canva", "photoshop", "premiere", "after effects", "davinci", "figma",
          "notion", "remotion", "hyperframes", "github", "vercel", "supabase", "pexels", "pixabay", "google ai studio", "notebooklm", "perplexity",
          "higgsfield", "seedance", "pomelli", "meta ai", "suno", "descript", "opus clip", "invideo", "synthesia"]
UNITES = r"(secondes?|minutes?|heures?|jours?|semaines?|mois|ans?|annees?|€|euros?|francs?|fcfa|cfa|\$|dollars?|%|pour ?cent|k\b|millions?|milliards?|vues|abonnes|clients|ventes|fois plus|x plus|go\b|mo\b|credits?)"
GRATUIT = r"\bgratuit(e|es|s|ement)?\b|\bsans payer\b|\bzero franc\b|\b0 franc\b|\bsans abonnement\b"
FAUX_RUSH = r"\bclient|\btemoignage|\bresultat (reel|obtenu)|\bma boutique|\bmon (produit|client)|\bavis\b"


def _faits_de(story: dict, faits_ok: dict) -> tuple[list[dict], list[str]]:
    cites, pb = [], []
    for fid in story.get("faits") or []:
        f = (faits_ok or {}).get(fid)
        if f is None:
            pb.append(f"fait « {fid} » cité mais non confirmé par la veille (ou inconnu) : retire-le, ou n'utilise que les faits fournis")
        else:
            cites.append(f)
    return cites, pb


def controle(story: dict, cfg: dict, faits_ok: dict | None) -> list[str]:
    """Liste des problèmes (vide = le storyboard peut être fabriqué et publié)."""
    cites, pb = _faits_de(story, faits_ok or {})
    dits = schema.textes_dits(story)
    ecran = schema.textes_ecran(story)
    leg = story.get("legende") or {}
    tout = dits + ecran + [leg.get("accroche", ""), leg.get("limite", "")] + list(leg.get("points") or []) + [story.get("promesse", "")]
    blob = _n(" \n ".join(tout))
    for rx, why in INTERDITS:
        m = re.search(rx, blob)
        if m:
            pb.append(f"formulation interdite — {why} : « {m.group(0)} »")
    # outils nommés -> fait cité qui les couvre
    couverts = {_n(o) for f in cites for o in (f.get("outils") or [])}
    for o in OUTILS:
        if re.search(rf"(?<![a-z]){re.escape(o)}(?![a-z])", blob) and o not in couverts:
            pb.append(f"outil « {o} » nommé sans fait vérifié qui le couvre : cite un fait de la liste fournie qui parle de cet outil, ou n'en parle pas")
    # chiffres avec unité -> présents dans un fait cité
    autorises = set()
    for f in cites:
        autorises |= {str(x) for x in (f.get("nombres") or [])}
        autorises |= set(re.findall(r"\d+(?:[.,]\d+)?", str(f.get("affirmation") or "")))
    for m in re.finditer(rf"(\d+(?:[.,]\d+)?)\s*{UNITES}", blob):
        if m.group(1) not in autorises:
            pb.append(f"chiffre sans source : « {m.group(0).strip()} » — un prix, une durée, un pourcentage ou une audience doit venir d'un fait vérifié cité")
    for m in re.finditer(r"(?<![\d.,])(\d{2,})(?![\d.,])", blob):
        v = m.group(1)
        if int(v) > 12 and v not in autorises and not re.fullmatch(r"20\d\d", v):
            pb.append(f"nombre sans source : « {v} »")
    # gratuit
    if re.search(GRATUIT, blob) and not any(f.get("gratuit") for f in cites):
        pb.append("« gratuit / sans payer » : seulement si un fait vérifié cité le dit (champ gratuit du fait) — sinon retire le mot")
    # rushs : jamais présentés comme une preuve
    for sc in story.get("scenes") or []:
        for b in sc.get("blocks") or []:
            if b.get("kind") in ("rush", "avant_apres"):
                lab = _n(" ".join(str(b.get(k) or "") for k in ("label", "titre")))
                if re.search(FAUX_RUSH, lab):
                    pb.append(f"étiquette de séquence trompeuse « {b.get('label') or b.get('titre')} » : une image de banque n'est ni un client ni un résultat")
    prom = _n(story.get("promesse", ""))
    if prom and not re.search(r"suite|partie|video|episode|tuto|prochain", prom):
        pb.append("« promesse » doit annoncer la vidéo suivante (ex. « la partie 2 : le script exact ») : c'est la seule chose que le compte sait tenir")
    if re.search(r"lien|pdf|fichier|liste|envoi|document|modele a copier|prompt", prom):
        pb.append("« promesse » ne peut pas annoncer un lien, un fichier ou une liste à recevoir : annonce la vidéo suivante")
    return pb


def resume() -> list[str]:
    """Les règles en clair (pour la consigne du scénariste et le README)."""
    return [
        "Aucune promesse de revenu, de vues, de succès garanti, de rapidité (« en 2 minutes seulement »), ni de remplacement d'un métier.",
        "N'écris jamais « j'ai testé », « j'ai gagné », « mes clients » : le compte n'a rien testé lui-même. Écris « voici comment », « tu peux », « regarde ».",
        "Ne promets jamais d'envoyer quelque chose (« je t'envoie », « en privé », « en DM »). La seule promesse permise : la vidéo suivante.",
        "Ne nomme un outil, une application ou un site (ChatGPT, CapCut, Canva, Pexels…) que si un FAIT VÉRIFIÉ de la liste le couvre, et cite l'identifiant de ce fait dans « faits ».",
        "Aucun chiffre avec une unité (prix, durée, pourcentage, nombre de vues) qui ne figure pas dans un fait vérifié cité. Les simples comptes (« 3 erreurs », « étape 2 ») sont libres.",
        "« Gratuit » seulement si un fait vérifié cité le dit ; les mots « illimité », « à l'infini », « viral », « garanti » sont interdits.",
        "Aucune astuce de contournement (VPN, e-mail jetable, essais gratuits à répétition, retrait de filigrane), aucune imitation d'une personne réelle.",
        "Une séquence filmée de banque d'images illustre un geste ou sert d'exemple de montage. Elle n'est jamais présentée comme un client, un témoignage ou un résultat.",
    ]
