"""Garde-fous de FOND : ce qu'une vidéo n'a pas le droit de dire ou de montrer.

Ces contrôles sont du code, pas des consignes : un storyboard écrit par un modèle, de réserve ou à la main
passe par les mêmes. `controle()` renvoie la liste des problèmes (vide = le storyboard est acceptable).

  1. Preuve : tout média cité existe dans le dossier ; tout extrait de la demande s'y retrouve mot pour mot ;
     toute ligne de code affichée se retrouve telle quelle dans un fichier source du dossier.
  2. Nombres : tout nombre affiché ou prononcé figure dans le dossier de preuve ou dans un fait vérifié cité.
     Un nombre suivi d'une unité sensible (minutes, %, FCFA, €…) doit s'y trouver avec cette unité.
  3. Formulations : pas de promesse invérifiable ; « gratuit » et « open source » seulement avec leur précision,
     appuyée sur un fait vérifié ; pas de confusion entre l'agent qui écrit le code et l'outil qui rend la vidéo.
  4. Un seul public : une vidéo « commerçant » ne montre ni code ni terminal et n'ouvre pas sur un nom d'outil.
  5. Un seul appel à l'action : la phrase de fin imposée. Rien d'autre n'invite à commenter, à cliquer ou à recevoir.
"""
from __future__ import annotations

import re

from . import preuves, schema
from .align import norm

UNITES = (r"minutes?|min|secondes?|sec|heures?|jours?|semaines?|mois|ans?|années?|%|pour ?cent|€|euros?|\$|dollars?|fcfa|f ?cfa|cfa|francs?(?: cfa)?|"
          r"vues?|abonnés?|clients?|ventes?|commandes?|likes?|commentaires?|fois|x|personnes?|grammes?|g|kilos?|kg|ml|cl|l|images?|px|pixels?")
ALIAS = {"pourcent": "%", "euros": "€", "euro": "€", "dollars": "$", "dollar": "$", "cfa": "fcfa", "francs": "fcfa", "franc": "fcfa", "francscfa": "fcfa",
         "franccfa": "fcfa", "min": "minute", "sec": "seconde", "pixels": "px", "pixel": "px", "grammes": "g", "gramme": "g", "kilos": "kg", "kilo": "kg"}
NUM_UNIT = re.compile(rf"(\d{{1,3}}(?:[ \u00a0\u202f]\d{{3}})+(?!\d)|\d+(?:[.,]\d+)?)\s*({UNITES})\b", re.I)

# formulations refusées dans tous les cas (aucune précision ne les rattrape)
INTERDIT = [
    (r"\bsans (?:aucun )?effort\b", "« sans effort »"),
    (r"\ben (?:deux|2|quelques|trois|3|cinq|5) (?:minutes?|secondes?|clics?)\b", "une durée promise (« en deux minutes »)"),
    (r"\bexplos\w+", "« explose »"),
    (r"\bd[ée]trui\w+|\b[ée]cras\w+|\btue\b", "« détruit / écrase »"),
    (r"\bviral\w*|\bviraux\b|\bbuzz\b", "une promesse de viralité"),
    (r"\bgaranti\w*", "« garanti »"),
    (r"\billimit[ée]\w*", "« illimité »"),
    (r"\bremplac\w+\b[^.!?]{0,40}\b(?:monteurs?|graphistes?|designers?|agences?|m[ée]tiers?|[ée]quipes?)\b", "« remplace un métier »"),
    (r"\b(?:plus besoin|pas besoin|sans) (?:de |d'un |d'une )?(?:monteurs?|graphistes?|designers?|agences?)\b", "« plus besoin de monteur »"),
    (r"\bsans (?:savoir )?coder\b|\bsans (?:une |aucune )?ligne de code\b|\bz[ée]ro code\b", "« sans coder » (il faut un ordinateur, une installation et des corrections)"),
    (r"\brevenus?\b|\bgagn\w+ (?:de l'argent|\d)|\bchiffre d'affaires\b|\brentab\w+|\bmillionnaire\b", "une promesse de revenu"),
    (r"\b(?:le|la) meilleur\w*\b|\bn° ?1\b|\bnum[ée]ro un\b|\bimbattable\b|\bincroyable\b|\bmagique\b|\br[ée]volution\w*", "un superlatif invérifiable"),
    (r"\bdoubl\w+ (?:tes|vos|ses) ventes\b|\bplus de ventes\b|\bvend(?:s|re)? plus\b|\bboost\w*", "une promesse de ventes"),
    (r"\bt[ée]moignage\w*|\bavis clients?\b|\bmes clients (?:disent|adorent)\b", "un témoignage ou un avis (aucun n'est fourni)"),
]
# envoi promis après un commentaire, ou second appel à l'action
APPEL = [
    (r"\bje t'envoie\w*|\bt'envoyer\b|\btu recevras\b|\bre[cç]ois\b|\brecevoir\b|\bdm\b|\bmessages? priv\w+|\ben priv[ée]\b|\bcadeau\w*|\boffert\w*",
     "une promesse d'envoi (commenter ne fait rien recevoir)"),
    (r"\bcommente\w*\b|\bcommentaire\b|\blien en bio\b|\ben bio\b|\babonne[- ]toi\b|\bpartage cette\b|\bclique\b|\ben promo\b|\bla formation\b|\bpromotion\b",
     "un appel à l'action en dehors de la phrase de fin imposée"),
]
# l'agent écrit le code ; c'est le moteur de rendu qui fabrique les images
CONFUSION = re.compile(r"\bclaude(?: code)?\b[^.!?;:]{0,24}\b(?:filme|tourne|monte\b|exporte|rend(?:u)? (?:la|ta|une|ma|cette) vid[ée]o|"
                       r"g[ée]n[èe]re (?:directement )?(?:la|ta|une|ma|des|cette) (?:vid[ée]os?|images?|pixels?)|fabrique (?:la|ta|une|ma|cette) vid[ée]o|"
                       r"cr[ée]e (?:directement )?(?:la|ta|une|ma) vid[ée]o)", re.I)
OUTILS = ["react", "remotion", "skill", "skills", "terminal", "node", "npm", "npx", "typescript", "javascript", "github", "framework", "api"]
SENSIBLES = {"gratuit": r"\bgratuit\w*", "open source": r"\bopen[- ]source\b"}


def _phrases(texts: list[str]) -> list[str]:
    out = []
    for t in texts:
        out += [p.strip() for p in re.split(r"(?<=[.!?…])\s+", t) if p.strip()]
    return out


def _pairs(text: str) -> set[tuple[str, str]]:
    out = set()
    for m in NUM_UNIT.finditer(text):
        raw = m.group(2).lower().strip()
        u = norm(raw) or raw                                   # « % », « € » et « $ » n'ont pas de lettres
        u = ALIAS.get(u, u if len(u) <= 2 else u.rstrip("s"))
        out.add((schema._num(m.group(1)), u))
    return out


def controle(story: dict, pack: dict, faits: dict[str, dict] | None = None) -> list[str]:
    """`story` a déjà passé schema.check ; `faits` = faits vérifiés et confirmés aujourd'hui ({id: fait})."""
    faits = faits or {}
    out: list[str] = []
    seg = story.get("segment")

    # ---- 0. cohérence avec le dossier
    pb = preuves.problemes(pack)
    if pb:
        return [f"dossier de preuve « {pack.get('id')} » inutilisable : " + " ; ".join(pb)]
    if pack.get("segment") != seg:
        out.append(f"le dossier de preuve « {pack['id']} » est fait pour le public « {pack.get('segment')} », pas « {seg} » : on ne mélange pas les deux publics")
    if story.get("sujet") not in (pack.get("sujets") or []):
        out.append(f"le dossier de preuve « {pack['id']} » ne couvre pas le sujet n° {story.get('sujet')} (il couvre : {pack.get('sujets')})")
    cites = {}
    for fid in story.get("faits") or []:
        if fid not in faits:
            out.append(f"le fait « {fid} » n'est pas confirmé par la veille du jour : retire ce qui s'appuie dessus")
        else:
            cites[fid] = faits[fid]

    # ---- 1. preuve : médias, extraits, code
    media = pack.get("media") or {}
    for ref in sorted(schema.refs_in(story)):
        if ref not in media:
            out.append(f"média « {ref} » absent du dossier de preuve (disponibles : {', '.join(media)})")
    has_code = False
    for s in story["scenes"]:
        for b in s.get("blocks") or []:
            if b["kind"] == "brief":
                where = preuves.extrait_ok(pack, b["text"])
                if where is None:
                    out.append(f"extrait « {b['text'][:50]}… » introuvable mot pour mot dans la demande écrite du dossier : recopie un passage exact")
                elif where != b.get("source"):
                    b["source"] = where
                    b["label"] = "Correction demandée" if where == "correction" else "Demande écrite"
            elif b["kind"] == "code":
                has_code = True
                bad = preuves.code_faux(pack, b["file"], b["lines"])
                if bad:
                    out.append(f"code affiché introuvable dans {b['file']} : « {bad[0][:60]} » — recopie des lignes exactes du fichier")
            elif b["kind"] == "terminal":
                has_code = True
                ok_src = norm(preuves.texte_nombres(pack) + " " + " ".join(str(f.get("affirmation", "")) for f in cites.values()))
                if norm(b["text"]) not in ok_src:
                    out.append(f"commande « {b['text']} » introuvable dans le dossier de preuve : on ne montre qu'une commande réellement utilisée")
            elif b["kind"] == "erreur" and not (media.get(b["ref"]) or {}).get("zone"):
                out.append(f"bloc « erreur » : le média « {b['ref']} » n'indique pas où se trouve le défaut (zone) dans preuve.yaml")

    # ---- 2. nombres
    texts = schema.texts_in(story)
    blob = " | ".join(texts)
    allowed_text = preuves.texte_nombres(pack) + "\n" + "\n".join(str(f.get("affirmation", "")) for f in cites.values())
    ok_num = schema.find_numbers(allowed_text)
    ok_pairs = _pairs(allowed_text)
    for n, u in sorted(_pairs(blob)):
        if (n, u) not in ok_pairs and not (u == "personne" and n in ok_num):
            out.append(f"« {n} {u} » ne figure ni dans le dossier de preuve ni dans un fait vérifié cité : retire ce chiffre")
    for n in sorted(schema.find_numbers(blob)):
        try:
            small = float(n) <= 10 and float(n) == int(float(n))
        except ValueError:
            small = False
        if n not in ok_num and not small:
            out.append(f"le nombre {n} ne figure ni dans le dossier de preuve ni dans un fait vérifié cité : retire-le")
    if sum(1 for s in story["scenes"] for b in s.get("blocks") or [] if b["kind"] == "stat") > 1:
        out.append("une statistique au plus par vidéo")

    # ---- 3. formulations
    low = blob.lower()
    for rx, what in INTERDIT + APPEL:
        m = re.search(rx, low)
        if m:
            out.append(f"formulation refusée — {what} : « {low[max(0, m.start() - 20):m.end() + 20].strip()} »")
    m = CONFUSION.search(blob)
    if m:
        out.append(f"confusion technique : « {m.group(0)} » — l'agent écrit le code, c'est le moteur de rendu qui fabrique la vidéo")
    autorise: dict[str, list[str]] = {}
    for f in cites.values():
        for mot, precisions in (f.get("mots") or {}).items():
            autorise.setdefault(str(mot), []).extend(str(p).lower() for p in precisions)
    for ph in _phrases(texts):
        pl = ph.lower()
        for mot, rx in SENSIBLES.items():
            if re.search(rx, pl) and not any(p in pl for p in autorise.get(mot, [])):
                need = f" (précision attendue : {' ou '.join(autorise[mot])})" if autorise.get(mot) else " (aucun fait vérifié cité ne l'autorise)"
                out.append(f"« {mot} » sans la précision qui le rend exact : « {ph[:70]} »{need}")

    # ---- 4. un seul public
    first = story["scenes"][0]
    if seg == "commercant":
        if has_code:
            out.append("vidéo « commerçant » : ni code ni terminal à l'écran (on montre le produit, la demande et le résultat)")
        opening = re.sub(r"[^a-zà-ÿ0-9]+", " ", " ".join([first.get("title", ""), first.get("public", ""), first.get("say", "")]).lower())
        hit = next((o for o in OUTILS + ["claude code"] if re.search(rf"\b{re.escape(o)}\b", opening)), None)
        if hit:
            out.append(f"vidéo « commerçant » : l'ouverture ne cite pas d'outil (« {hit} ») — elle montre le résultat pour le commerce")
        named = {o for o in OUTILS if re.search(rf"\b{re.escape(o)}\b", low)}
        if len(named) > 1:
            out.append(f"vidéo « commerçant » : trop de noms d'outils ({', '.join(sorted(named))}) — parle d'offre, de produit, de client")
    if pack.get("fictif") and re.search(r"\b(?:vrai|vraie|r[ée]el|r[ée]elle|authentique)s? (?:commerce|boutique|client|produit|commande|vente)", low):
        out.append("l'exemple est fictif : ne le présente pas comme un vrai commerce, un vrai produit ou une vraie vente")
    return out
