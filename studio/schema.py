"""Forme d'un storyboard (format « mascotte ») : ce que le scénariste — modèle ou réserve — doit rendre.

Un storyboard est une suite de 4 à 7 ÉCRANS, suivis de l'écran de fin que l'agent ajoute lui-même.
Chaque écran : un titre court, une tuile numérotée facultative, une pose du personnage, le texte dit par
la voix (« say ») et au plus deux blocs. Dans « say », un repère [a] fait apparaître le premier bloc au
mot qui suit, [a1] [a2]… ses éléments ; [b], [b1]… pour le second bloc.

`normaliser()` range le storyboard et renvoie la liste de TOUT ce qui ne va pas, en français : c'est ce
texte qui est renvoyé au modèle pour qu'il corrige.
"""
from __future__ import annotations

import copy
import re

from . import align

POSES = ("presente", "pointe", "bras_croises", "mains_hanches", "reflechit", "surpris", "ordi", "pouce", "victoire", "stop", "telephone")
ICONES = ("video", "voix", "image", "texte", "lien", "telephone", "ordi", "horloge", "cadenas", "loupe", "argent", "message", "coche", "croix",
          "etoile", "panier", "photo", "musique", "robot", "ciseaux", "idee", "cible", "fleche", "dossier", "oeil")
TUILES = ("ÉTAPE", "NUMÉRO", "ERREUR", "OUTIL", "RÈGLE", "PLAN", "ASTUCE", "RÉGLAGE", "EFFET", "PIÈGE")
FAMILLES = ("methode", "liste", "erreurs", "avant_apres", "coulisses", "alerte", "outil")
HOOKS = ("resultat", "probleme", "contraste", "question")
EFFETS = ("couleurs", "zoom", "titre", "sous_titres", "barre")
CADRES = ("portrait", "paysage", "carre")
KINDS = ("liste", "check", "cartes", "icones", "chrono", "fenetre", "mot", "etiquette", "tuiles_video", "rush", "avant_apres")
MOTS = (100, 215)          # mots prononcés, hors écran de fin
ECRANS = (4, 7)
MARK = re.compile(r"\[([a-z]\d?|promo)\]")


def visible(s: str) -> str:
    """Le texte tel qu'il s'affiche (sans les marques *…* ni le retour à la ligne « / »)."""
    return re.sub(r"\s+", " ", str(s or "").replace("*", "").replace(" / ", " ")).strip()


def sub_cues(b: dict) -> int:
    """Nombre de repères d'éléments ([a1], [a2]…) que ce bloc sait utiliser."""
    k = b.get("kind")
    if k in ("liste", "check", "icones"):
        return len(b.get("items") or [])
    if k == "cartes":
        return 2
    if k == "fenetre":
        return 2 if b.get("reponse") else 1
    if k == "avant_apres":
        return 1 + len(b.get("effets") or [])
    if k == "mot":
        return 1 if b.get("sous") else 0
    return 0


def hauteur(b: dict) -> int:
    """Hauteur approximative du bloc à l'écran, en pixels (pour refuser un écran trop chargé avant le rendu)."""
    k = b.get("kind")
    n = len(b.get("items") or [])
    if k == "liste":
        return 98 * n + 22 * max(0, n - 1)
    if k == "check":
        return 92 * n + 20 * max(0, n - 1)
    if k == "cartes":
        return 400 if any(c.get("note") for c in b.get("cards") or []) else 310
    if k == "icones":
        return 232 if n <= 3 else 492
    if k == "chrono":
        return 190
    if k == "fenetre":
        return 430 if b.get("reponse") else 370
    if k == "mot":
        return 220 if b.get("sous") else 150
    if k == "etiquette":
        return 70
    if k == "tuiles_video":
        return 236 if int(b.get("n") or 4) <= 2 else 496
    if k in ("rush", "avant_apres"):
        cadre = b.get("cadre") or "portrait"
        h = {"portrait": 718, "paysage": 514, "carre": 600}.get(cadre, 718)
        if k == "avant_apres":                                   # sous le cadre : les étiquettes des effets, 2 par ligne en portrait
            par_ligne = {"portrait": 2, "carre": 3, "paysage": 5}.get(cadre, 2)
            h += 22 + 56 * -(-len(b.get("effets") or [1, 2]) // par_ligne)
        return h
    return 200


def _txt(pb: list[str], where: str, v, lo: int, hi: int, nom: str) -> str:
    s = str(v or "").strip()
    n = len(visible(s))
    if n < lo:
        pb.append(f"{where} : « {nom} » manque ou est trop court (au moins {lo} caractères)")
    elif n > hi:
        pb.append(f"{where} : « {nom} » fait {n} caractères, maximum {hi} : « {visible(s)[:50]} »")
    return s


def _bloc(pb: list[str], where: str, b: dict) -> dict:
    if not isinstance(b, dict):
        pb.append(f"{where} : un bloc doit être un objet")
        return {"kind": "etiquette", "text": "?"}
    k = b.get("kind")
    if k not in KINDS:
        pb.append(f"{where} : type de bloc inconnu « {k} » (types permis : {', '.join(KINDS)})")
        return {"kind": "etiquette", "text": "?"}
    o: dict = {"kind": k}
    if k in ("liste", "check"):
        items = [str(x).strip() for x in (b.get("items") or []) if str(x).strip()]
        lo, hi, mx = (2, 5, 28) if k == "liste" else (2, 4, 30)
        if not lo <= len(items) <= hi:
            pb.append(f"{where} : « {k} » demande {lo} à {hi} éléments, il y en a {len(items)}")
        for x in items:
            if len(visible(x)) > mx:
                pb.append(f"{where} : élément de « {k} » trop long ({len(visible(x))} caractères, maximum {mx}) : « {visible(x)} »")
        o["items"] = items[:hi]
        if k == "liste" and str(b.get("debut") or "").isdigit() and 1 < int(b["debut"]) <= 9:
            o["debut"] = int(b["debut"])                       # la numérotation continue celle des écrans précédents
    elif k == "cartes":
        cards = b.get("cards") or []
        if len(cards) != 2:
            pb.append(f"{where} : « cartes » demande exactement 2 cartes (une « non », une « oui »)")
        o["cards"] = []
        for c in cards[:2]:
            c = c if isinstance(c, dict) else {}
            card = {"tag": _txt(pb, where, c.get("tag"), 2, 24, "tag de carte"), "text": _txt(pb, where, c.get("text"), 2, 20, "texte de carte"),
                    "ton": "oui" if c.get("ton") == "oui" else "non"}
            if c.get("note"):
                card["note"] = _txt(pb, where, c.get("note"), 1, 14, "note de carte")
            o["cards"].append(card)
        if len(o["cards"]) == 2 and {c["ton"] for c in o["cards"]} != {"oui", "non"}:
            pb.append(f"{where} : les deux cartes doivent s'opposer (ton « non » puis ton « oui »)")
    elif k == "icones":
        items = b.get("items") or []
        if not 2 <= len(items) <= 4:
            pb.append(f"{where} : « icones » demande 2 à 4 éléments")
        o["items"] = []
        for x in items[:4]:
            x = x if isinstance(x, dict) else {}
            if x.get("icon") not in ICONES:
                pb.append(f"{where} : pictogramme inconnu « {x.get('icon')} » (permis : {', '.join(ICONES)})")
            o["items"].append({"icon": x.get("icon") if x.get("icon") in ICONES else "idee", "label": _txt(pb, where, x.get("label"), 2, 13, "libellé de pictogramme")})
    elif k == "chrono":
        o["valeur"] = _txt(pb, where, b.get("valeur"), 1, 4, "valeur du chrono")
        o["unite"] = _txt(pb, where, b.get("unite"), 2, 10, "unité du chrono")
    elif k == "fenetre":
        o["titre"] = _txt(pb, where, b.get("titre") or "Assistant IA", 2, 20, "titre de fenêtre")
        o["question"] = _txt(pb, where, b.get("question"), 6, 64, "question")
        if b.get("reponse"):
            o["reponse"] = _txt(pb, where, b.get("reponse"), 4, 80, "réponse")
    elif k == "mot":
        o["text"] = _txt(pb, where, b.get("text"), 2, 16, "mot")
        if b.get("sous"):
            o["sous"] = _txt(pb, where, b.get("sous"), 4, 46, "sous-texte")
    elif k == "etiquette":
        o["text"] = _txt(pb, where, b.get("text"), 2, 26, "étiquette")
    elif k == "tuiles_video":
        o["n"] = max(2, min(4, int(b.get("n") or 4)))
    else:  # rush, avant_apres
        o["q"] = _txt(pb, where, b.get("q"), 4, 60, "q (recherche en anglais)")
        if re.search(r"[àâçéèêëîïôùûü]", o["q"].lower()):
            pb.append(f"{where} : « q » doit être en anglais, 2 à 5 mots simples (c'est la recherche envoyée à la banque de vidéos) : « {o['q']} »")
        if not 2 <= len(o["q"].split()) <= 6:
            pb.append(f"{where} : « q » doit faire 2 à 5 mots : « {o['q']} »")
        o["voir"] = _txt(pb, where, b.get("voir"), 10, 110, "voir (ce qu'on doit voir à l'image, en français)")
        o["cadre"] = b.get("cadre") if b.get("cadre") in CADRES else "portrait"
        if b.get("ref"):
            o["ref"] = str(b["ref"])
        if k == "rush":
            if b.get("label"):
                o["label"] = _txt(pb, where, b.get("label"), 2, 26, "label")
        else:
            eff = [e for e in (b.get("effets") or []) if e in EFFETS]
            if len(eff) < 1:
                pb.append(f"{where} : « avant_apres » demande 1 à 5 effets parmi {', '.join(EFFETS)}")
            o["effets"] = list(dict.fromkeys(eff))[:5]
            if "titre" in o["effets"]:
                o["titre"] = _txt(pb, where, b.get("titre"), 3, 24, "titre incrusté")
            if "sous_titres" in o["effets"]:
                o["sous_titre"] = _txt(pb, where, b.get("sous_titre"), 5, 30, "sous_titre (2 à 4 mots)")
                if not 2 <= len(o["sous_titre"].split()) <= 4:
                    pb.append(f"{where} : « sous_titre » doit faire 2 à 4 mots")
    return o


def normaliser(story: dict) -> tuple[dict, list[str]]:
    """Renvoie (storyboard rangé, problèmes). L'écran de fin éventuel est retiré : l'agent le remet lui-même."""
    pb: list[str] = []
    if not isinstance(story, dict):
        return {}, ["le storyboard doit être un objet JSON"]
    s = copy.deepcopy(story)
    out: dict = {k: s[k] for k in ("sujet", "idee", "_reserve", "suite_de", "suite") if k in s}
    out["title"] = _txt(pb, "storyboard", s.get("title"), 12, 80, "title")
    out["famille"] = s.get("famille") if s.get("famille") in FAMILLES else None
    if out["famille"] is None:
        pb.append(f"storyboard : « famille » doit valoir l'un de : {', '.join(FAMILLES)}")
    out["hook_type"] = s.get("hook_type") if s.get("hook_type") in HOOKS else None
    if out["hook_type"] is None:
        pb.append(f"storyboard : « hook_type » doit valoir l'un de : {', '.join(HOOKS)}")
    kw = align.norm(str(s.get("keyword") or "")).upper()
    kw_aff = str(s.get("keyword") or "").strip().upper()
    if not re.fullmatch(r"[A-Z]{3,10}", kw) or not re.fullmatch(r"[A-Za-zÀ-ÿ]{3,10}", kw_aff):
        pb.append("storyboard : « keyword » doit être UN mot de 3 à 10 lettres, facile à écrire en commentaire (ex. MONTAGE)")
    out["keyword"] = kw_aff or "SUITE"
    out["promesse"] = _txt(pb, "storyboard", s.get("promesse"), 6, 40, "promesse (ce que la suite apportera)")
    cov = [str(x).strip().upper() for x in (s.get("couverture") or []) if str(x).strip()]
    if not 2 <= len(cov) <= 3:
        pb.append("storyboard : « couverture » demande 2 ou 3 lignes très courtes (le texte de la miniature)")
    for x in cov:
        if len(visible(x)) > 15:
            pb.append(f"storyboard : ligne de couverture trop longue ({len(visible(x))} caractères, maximum 15) : « {visible(x)} »")
    if cov and not any("*" in x for x in cov):
        cov[-1] = f"*{cov[-1]}*"
    out["couverture"] = cov[:3]
    leg = s.get("legende") if isinstance(s.get("legende"), dict) else {}
    pts = [str(x).strip() for x in (leg.get("points") or []) if str(x).strip()]
    out["legende"] = {"accroche": _txt(pb, "légende", leg.get("accroche"), 20, 150, "accroche"), "points": pts[:5],
                      "limite": _txt(pb, "légende", leg.get("limite"), 20, 210, "limite (la ligne honnête : ce que la méthode ne fait pas, ce qu'il faut avoir)")}
    if not 2 <= len(pts) <= 5:
        pb.append("légende : « points » demande 2 à 5 lignes (les étapes ou les éléments de la vidéo)")
    for x in pts:
        if len(x) > 100:
            pb.append(f"légende : point trop long ({len(x)} caractères, maximum 100)")
    tags = []
    for h in s.get("hashtags") or []:
        h = "#" + re.sub(r"[^0-9A-Za-zÀ-ÿ_]", "", str(h))
        if len(h) > 2 and h.lower() not in [t.lower() for t in tags]:
            tags.append(h)
    if not 4 <= len(tags) <= 9:
        pb.append(f"storyboard : 4 à 9 hashtags attendus, il y en a {len(tags)}")
    out["hashtags"] = tags[:9]
    out["faits"] = [str(x) for x in (s.get("faits") or [])]
    out["outils"] = [str(x) for x in (s.get("outils") or [])]

    scenes = [sc for sc in (s.get("scenes") or []) if isinstance(sc, dict) and sc.get("type") != "fin"]
    if not ECRANS[0] <= len(scenes) <= ECRANS[1]:
        pb.append(f"storyboard : {ECRANS[0]} à {ECRANS[1]} écrans attendus (sans l'écran de fin), il y en a {len(scenes)}")
    out["scenes"] = []
    total, rushs = 0, 0
    for i, sc in enumerate(scenes):
        w = f"écran {i + 1}"
        o: dict = {"type": "ecran", "title": _txt(pb, w, sc.get("title"), 3, 36, "title")}
        if o["title"].count("*") % 2 or o["title"].count("*") > 4:
            pb.append(f"{w} : dans le titre, entoure un ou deux mots avec *…* (ils seront surlignés), pas plus")
        t = sc.get("tuile")
        if t:
            if i == 0:
                pb.append("écran 1 : pas de tuile sur l'accroche")
            elif not isinstance(t, dict) or str(t.get("label") or "").upper() not in TUILES or not re.fullmatch(r"[1-9]", str(t.get("n") or "")):
                pb.append(f"{w} : « tuile » doit être {{\"label\": l'un de {', '.join(TUILES)}, \"n\": chiffre de 1 à 9}}")
            else:
                o["tuile"] = {"label": str(t["label"]).upper(), "n": str(t["n"])}
        o["pose"] = sc.get("pose") if sc.get("pose") in POSES else None
        if o["pose"] is None:
            if sc.get("pose"):
                pb.append(f"{w} : pose inconnue « {sc.get('pose')} » (poses permises : {', '.join(POSES)})")
            o["pose"] = POSES[i % len(POSES)]
        say = re.sub(r"\s+", " ", str(sc.get("say") or "")).strip()
        _clean, toks, cues = align.parse_say(say)
        n = len(toks)
        total += n
        lo, hi = (8, 32) if i == 0 else (12, 55)
        if not lo <= n <= hi:
            pb.append(f"{w} : « say » fait {n} mots ({lo} à {hi} attendus)")
        o["say"] = say
        blocks = sc.get("blocks") or []
        if len(blocks) > 2:
            pb.append(f"{w} : 2 blocs au plus par écran, il y en a {len(blocks)}")
        o["blocks"] = []
        permis = set()
        for j, b in enumerate(blocks[:2]):
            ob = _bloc(pb, f"{w}, bloc {j + 1}", b)
            ob["id"] = "ab"[j]
            permis |= {ob["id"]} | {f"{ob['id']}{q + 1}" for q in range(sub_cues(ob))}
            if ob["kind"] in ("rush", "avant_apres"):
                rushs += 1
                ob.setdefault("ref", f"r{i + 1}{ob['id']}")
            o["blocks"].append(ob)
        inconnus = [c for c in cues if c not in permis]
        if inconnus:
            pb.append(f"{w} : repères inconnus dans « say » : {', '.join('[' + c + ']' for c in inconnus)} (repères permis ici : "
                      f"{', '.join('[' + c + ']' for c in sorted(permis)) or 'aucun'})")
        budget = (880 if o.get("tuile") else 940) - 36 * max(0, len(o["blocks"]) - 1)
        h = sum(hauteur(b) for b in o["blocks"])
        if h > budget:
            pb.append(f"{w} : écran trop chargé ({h} px de blocs pour {budget} px disponibles) — retire un bloc, raccourcis la liste, ou mets le rush seul")
        if sum(1 for b in o["blocks"] if b["kind"] in ("rush", "avant_apres")) > 1:
            pb.append(f"{w} : une seule séquence filmée par écran")
        out["scenes"].append(o)
    if scenes and not MOTS[0] <= total <= MOTS[1]:
        pb.append(f"storyboard : {total} mots prononcés au total, il en faut entre {MOTS[0]} et {MOTS[1]} (hors phrase de fin)")
    if scenes and not 1 <= rushs <= 3:
        pb.append(f"storyboard : il faut 1 à 3 séquences filmées (blocs « rush » ou « avant_apres »), il y en a {rushs}")
    return out, pb


def refs_in(story: dict) -> list[str]:
    return [b["ref"] for sc in story.get("scenes") or [] for b in sc.get("blocks") or [] if b.get("kind") in ("rush", "avant_apres") and b.get("ref")]


def textes_ecran(story: dict) -> list[str]:
    """Tout ce qui s'affiche (titres, blocs, couverture) : pour les contrôles de formulation."""
    out = [story.get("title", "")] + list(story.get("couverture") or []) + [story.get("promesse", "")]
    for sc in story.get("scenes") or []:
        out.append(sc.get("title", ""))
        for b in sc.get("blocks") or []:
            for k in ("text", "sous", "titre", "question", "reponse", "label", "valeur", "unite", "sous_titre"):
                if b.get(k):
                    out.append(str(b[k]))
            out += [str(x) for x in b.get("items") or [] if isinstance(x, str)]
            out += [str(x.get("label", "")) for x in b.get("items") or [] if isinstance(x, dict)]
            for c in b.get("cards") or []:
                out += [c.get("tag", ""), c.get("text", ""), c.get("note", "")]
    return [visible(x) for x in out if x]


def textes_dits(story: dict) -> list[str]:
    return [align.parse_say(sc.get("say") or "")[0] for sc in story.get("scenes") or []]
