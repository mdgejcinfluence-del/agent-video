"""Garde-fous : ce qu'une vidéo n'a pas le droit de dire. Appliqués à TOUT storyboard, écrit par un modèle ou pris en réserve.

L'agent publie seul : ces contrôles sont donc automatiques et sans exception.
  1. Aucune promesse de revenu, de vues, de résultat garanti ; aucune astuce de contournement.
  2. Aucune expérience personnelle inventée (« j'ai testé », « mes clients ») : le compte ne ment pas sur ce qu'il a fait.
  3. Aucun envoi promis en privé : l'agent ne sait pas envoyer de message.
  4. Tout outil nommé et tout chiffre (prix, durée, pourcentage, audience) doit venir d'un fait vérifié sur une page
     officielle (data/faits.yaml), cité dans le storyboard et confirmé par la veille.
  5. « Gratuit » seulement si un fait cité le dit, et la limite est écrite dans la légende.
  6. Une séquence de banque d'images n'est jamais présentée comme un client, un résultat ou un témoignage.

Spécialisation « prompts et commandes d'IA » (novembre 2026) :
  7. Une COMMANDE (un mot précédé d'une barre, /compact) n'est montrée que si une page officielle citée la décrit
     (champ « commandes » d'un fait vérifié). Une commande inventée est refusée.
  8. Un hashtag (#mot) sert à classer une publication sur un réseau social : il n'est jamais présenté comme une commande
     donnée à une IA, et n'apparaît que dans les vidéos de la famille « hashtags ».
  9. Les outils de base (config : editorial.outils_de_base) peuvent être nommés comme l'endroit où coller une instruction.
     Toute autre affirmation sur un outil (une fonction, un menu, « gratuit », une limite) demande un fait vérifié cité.
 10. Le texte d'une instruction à copier et l'extrait de réponse d'une IA sont contrôlés à part : on y refuse les
     contournements et l'imitation d'une personne, pas les mots qu'un utilisateur écrit normalement à une IA.
 11. L'e-book n'est annoncé que par l'écran de fin, et seulement quand il est réellement en vente (config : offer.ebook).
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
          "runway", "kling", "pika", "heygen", "elevenlabs", "capcut", "canva", "photoshop", "premiere pro", "adobe premiere", "after effects", "davinci", "figma",
          "notion ai", "remotion", "hyperframes", "github", "vercel", "supabase", "pexels", "pixabay", "google ai studio", "notebooklm", "perplexity",
          "higgsfield", "seedance", "pomelli", "meta ai", "suno", "descript", "opus clip", "invideo", "synthesia"]
UNITES = r"(secondes?|minutes?|heures?|jours?|semaines?|mois|ans?|annees?|€|euros?|francs?|fcfa|cfa|\$|dollars?|%|pour ?cent|k\b|millions?|milliards?|vues|abonnes|clients|ventes|fois plus|x plus|go\b|mo\b|credits?)"
GRATUIT = r"\bgratuit(e|es|s|ement)?\b|\bsans payer\b|\bzero franc\b|\b0 franc\b|\bsans abonnement\b"
OUTILS += ["leonardo", "ideogram", "gamma app", "cursor", "microsoft copilot", "canva ai", "kling ai", "claude code"]
# refusé même dans une instruction à copier ou dans une réponse d'IA affichée
INTERDITS_IA = [
    (r"\bvpn\b|\bcontourn|\bcrack|\bpirat|\bsans (filigrane|watermark)\b|\bfaux (avis|comptes?|temoignages?)\b|\b(e-?mail|adresse) (jetable|temporaire)\b|\bjailbreak\b|\bmode dan\b",
     "contournement des règles d'un service"),
    (r"\bdeepfake\b|\bcloner? (la|une|sa|ta) voix\b|\busurp|\bimite[rz]? (la voix|le visage) de\b", "imitation d'une personne réelle"),
    (r"\brevenus? garantis?\b(?<!pas de revenus garantis)|\bdevenir riche\b|\bargent facile\b", "promesse de gain dans le résultat montré"),
]
COMMANDE = r"(?<![\w/:.\-])/[a-zA-Z][\w:\-]{1,30}"
HASHTAG = r"(?<![\w&])#[a-zA-ZÀ-ÿ]\w{1,40}"
EBOOK = r"\be-?book\b|\blivre numerique\b|\blien en bio\b|\bbibliotheque ultime\b"


def outils_de_base(cfg: dict) -> set[str]:
    return {_n(x) for x in ((cfg.get("editorial") or {}).get("outils_de_base") or ["ChatGPT", "Gemini", "Claude"])}
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
    ia = schema.textes_ia(story)
    fiches = story.get("prompts") or []
    blob_prompts = _n(" \n ".join(ia["prompts"]))
    blob_ia = _n(" \n ".join(ia["prompts"] + ia["reponses"] + [str(f.get("resultat_exemple") or "") for f in fiches]))
    def cite(m) -> bool:
        """Vrai si le passage est une lecture à haute voix de l'instruction à copier (les mots qui précèdent s'y retrouvent aussi)."""
        debut = blob.rfind(" ", 0, max(0, m.start() - 14)) + 1
        ctx = re.sub(r"\s+", " ", blob[debut:m.end()]).strip(" .,;:!?«»\"'")
        return len(ctx.split()) >= 3 and ctx in re.sub(r"\s+", " ", blob_prompts)
    for rx, why in INTERDITS:
        m = next((x for x in re.finditer(rx, blob) if not cite(x)), None)
        if m:
            pb.append(f"formulation interdite — {why} : « {m.group(0)} »")
    for rx, why in INTERDITS_IA:
        m = re.search(rx, blob_ia)
        if m:
            pb.append(f"instruction ou réponse refusée — {why} : « {m.group(0)} »")
    # outils nommés -> outil de base, ou fait cité qui les couvre
    base = outils_de_base(cfg)
    couverts = {_n(o) for f in cites for o in (f.get("outils") or [])}
    noms = blob + " \n " + _n(" \n ".join(str(f.get("outil") or "") for f in fiches))
    for o in OUTILS:
        if re.search(rf"(?<![a-z]){re.escape(o)}(?![a-z])", noms) and o not in couverts and o not in base:
            if any(o != b and re.fullmatch(rf"{re.escape(b)}( |$).*", o) for b in base) and o not in ("claude code",):
                continue
            pb.append(f"outil « {o} » nommé sans fait vérifié qui le couvre : cite un fait de la liste fournie qui parle de cet outil, ou n'en parle pas")
    for f in fiches:
        if not _n(f.get("outil") or ""):
            continue
        if not any(_n(f["outil"]) == x or _n(f["outil"]).startswith(x + " ") for x in base | couverts):
            pb.append(f"fiche « {f.get('titre')} » : l'outil « {f['outil']} » n'est ni un outil de base ({', '.join(sorted(base))}) ni couvert par un fait vérifié cité")
    # commandes : chacune doit être décrite par une page officielle citée
    connues = {str(c).lower() for f in cites for c in (f.get("commandes") or [])}
    vues = []
    for texte in dits + ecran + ia["prompts"]:
        for m in re.finditer(COMMANDE, str(texte)):
            c = m.group(0).lower().rstrip(".:,-")
            if c not in connues and c not in vues:
                vues.append(c)
    for c in vues:
        pb.append(f"commande « {c} » : aucune page officielle citée ne la décrit — une commande n'est montrée que si un fait vérifié (champ « commandes ») la contient ; "
                  "sinon écris l'instruction en toutes lettres, sans barre")
    # hashtags : jamais une commande d'IA ; seulement dans la famille « hashtags »
    tags_txt = [m.group(0) for texte in dits + ecran for m in re.finditer(HASHTAG, str(texte))]
    if tags_txt and story.get("famille") != "hashtags":
        pb.append(f"« {tags_txt[0]} » : un hashtag classe une publication sur un réseau social, ce n'est pas une commande pour une IA — "
                  "il n'apparaît que dans les vidéos de la famille « hashtags »")
    if re.search(r"(tape[rsz]?|ecri[st]|saisi[st]) #\w+ (dans|a|sur) (chatgpt|gemini|claude|l'ia)", blob):
        pb.append("un hashtag n'active aucune fonction dans une IA : ne présente jamais « #mot » comme une commande")
    # l'e-book : seulement par l'écran de fin
    m = re.search(EBOOK, blob)
    if m:
        pb.append(f"« {m.group(0)} » : l'e-book et le lien en bio ne sont annoncés que par l'écran de fin (ajouté automatiquement quand l'e-book est en vente)")
    # chiffres avec unité -> présents dans un fait cité, dans l'instruction, dans ses valeurs d'exemple ou dans la réponse affichée
    autorises = set()
    for f in cites:
        autorises |= {str(x) for x in (f.get("nombres") or [])}
        autorises |= set(re.findall(r"\d+(?:[.,]\d+)?", str(f.get("affirmation") or "")))
    for f in fiches:
        autorises |= set(re.findall(r"\d+(?:[.,]\d+)?", " ".join([str(f.get("texte") or "")] + [str(v) for v in (f.get("exemple") or {}).values()])))
    autorises |= set(re.findall(r"\d+(?:[.,]\d+)?", " ".join(ia["reponses"])))
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
    if re.search(r"\blien\b|\bpdf\b|\bfichiers?\b|\benvoi|\bdocuments?\b|\be-?book\b|liste a recevoir", prom):
        pb.append("« promesse » ne peut pas annoncer un lien, un fichier ou un envoi : annonce la vidéo suivante")
    # familles qui parlent d'une fonction d'un outil : un fait vérifié est obligatoire
    if story.get("famille") in ("commandes", "outils") and not cites:
        pb.append("famille « commandes » ou « outils » : la vidéo décrit une fonction d'un outil — cite au moins un fait vérifié (page officielle) dans « faits »")
    return pb


def resume() -> list[str]:
    """Les règles en clair (pour la consigne du scénariste et le README)."""
    return [
        "Aucune promesse de revenu, de vues, de succès garanti, de rapidité (« en 2 minutes seulement »), ni de remplacement d'un métier.",
        "N'écris jamais « j'ai testé », « j'ai gagné », « mes clients » : le compte n'a rien testé lui-même. Écris « voici comment », « tu peux », « regarde ».",
        "Ne promets jamais d'envoyer quelque chose (« je t'envoie », « en privé », « en DM »). La seule promesse permise : la vidéo suivante.",
        "ChatGPT, Gemini et Claude peuvent être nommés comme l'endroit où coller une instruction. Tout autre outil, et toute affirmation sur une fonction, un menu, un prix ou une limite d'un outil, demande un FAIT VÉRIFIÉ de la liste, cité dans « faits ».",
        "Une COMMANDE (/mot) n'est montrée que si elle figure dans le champ « commandes » d'un fait vérifié cité. N'invente jamais une commande, un raccourci ou une fonction secrète ; ne présente jamais une commande d'un outil comme valable dans un autre.",
        "Un hashtag (#mot) classe une publication sur un réseau social : ce n'est jamais une commande donnée à une IA. Il n'apparaît que dans la famille « hashtags ».",
        "Ne parle jamais de l'e-book ni du lien en bio : l'écran de fin s'en charge quand l'e-book est en vente.",
        "Aucun chiffre avec une unité (prix, durée, pourcentage, nombre de vues) qui ne figure pas dans un fait vérifié cité. Les simples comptes (« 3 erreurs », « étape 2 ») sont libres.",
        "« Gratuit » seulement si un fait vérifié cité le dit ; les mots « illimité », « à l'infini », « viral », « garanti » sont interdits.",
        "Aucune astuce de contournement (VPN, e-mail jetable, essais gratuits à répétition, retrait de filigrane), aucune imitation d'une personne réelle.",
        "Une séquence filmée de banque d'images illustre un geste ou sert d'exemple de montage. Elle n'est jamais présentée comme un client, un témoignage ou un résultat.",
    ]
