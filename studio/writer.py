"""Le scénariste : il transforme une idée en storyboard au format « mascotte ».

Avec une clé Gemini, un modèle écrit le storyboard ; sa réponse repasse par la forme (schema) et les
garde-fous (garde) et tout ce qui est refusé lui est renvoyé pour correction. Sans clé, l'agent prend un
storyboard de réserve (examples/reserve/), écrit à l'avance et soumis aux mêmes contrôles.
L'écran de fin n'est jamais écrit par le modèle : il est construit ici, à partir de config.yaml.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import re
from pathlib import Path

from . import align, garde, schema

FIN_SUITE = "Abonne-toi pour ne rien rater. Et commente MOT si tu veux [p]PROMESSE."
FIN_PROMO = " [promo]La formation complète est en promo, lien en bio."


def promo_active(cfg: dict, today: dt.date | None = None) -> bool:
    """La phrase « formation en promo, lien en bio » n'est dite que si c'est vrai : promo confirmée, non expirée, lien renseigné."""
    o = cfg.get("offer") or {}
    p = o.get("promo") or {}
    if not (p.get("confirmee") and str(o.get("lien_bio") or "").strip()):
        return False
    fin = str(p.get("jusquau") or "").strip()
    if fin:
        try:
            if dt.date.fromisoformat(fin) < (today or dt.date.today()):
                return False
        except ValueError:
            return False
    return True


def fin_scene(story: dict, cfg: dict) -> dict:
    """L'écran de fin, imposé : abonne-toi + mot à commenter + ce que la suite apportera (+ la formation si elle est réellement en promo)."""
    o = cfg.get("offer") or {}
    kw = (str(o.get("cta_mot_fixe") or "").strip() or story["keyword"]).upper()
    prom = schema.visible(story.get("promesse") or "la suite").rstrip(".! ")
    say = (o.get("cta") or FIN_SUITE).replace("MOT", kw).replace("PROMESSE", prom)
    sc = {"type": "fin", "keyword": kw, "promesse": prom, "pose": "pouce"}
    if promo_active(cfg):
        say += o.get("cta_promo") or FIN_PROMO
        sc["promo"] = o.get("cta_promo_ecran") or "Formation complète en *promo* · lien en bio"
    sc["say"] = say
    return sc


def apply_cta(story: dict, cfg: dict) -> dict:
    st = copy.deepcopy(story)
    st["scenes"] = [s for s in st["scenes"] if s.get("type") != "fin"] + [fin_scene(st, cfg)]
    if (cfg.get("offer") or {}).get("cta_mot_fixe"):
        st["keyword"] = str(cfg["offer"]["cta_mot_fixe"]).upper()
    return st


def controler(story: dict, cfg: dict, faits_ok: dict | None, strict: bool = True) -> tuple[dict, list[str]]:
    """Forme + garde-fous + écran de fin. Lève ValueError avec la liste complète des refus."""
    st, pb = schema.normaliser(story)
    if not pb:
        pb += garde.controle(st, cfg, faits_ok)
    if pb and strict:
        raise ValueError("\n".join(f"- {x}" for x in pb))
    return apply_cta(st, cfg), pb


# --------------------------------------------------------------------------- réserves
def reserves(cfg: dict) -> list[dict]:
    root = Path(cfg.get("_root", "."))
    out = []
    for f in sorted((root / "examples" / "reserve").glob("*.json")):
        try:
            st = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        st["_reserve"] = f.stem
        out.append(st)
    return out


def reserve(cfg: dict, name: str) -> dict | None:
    return next((r for r in reserves(cfg) if r["_reserve"] == name), None)


# --------------------------------------------------------------------------- consigne du modèle
def _exemple(cfg: dict) -> str:
    r = reserve(cfg, "r2_zapper") or (reserves(cfg) or [{}])[0]
    r = {k: v for k, v in r.items() if k not in ("_reserve", "suite")}
    return json.dumps(r, ensure_ascii=False)


def systeme(cfg: dict) -> str:
    brand = cfg.get("brand") or {}
    v = cfg.get("video") or {}
    lo, hi = (v.get("seconds") or [40, 70])[:2]
    return "\n".join([
        f"Tu écris les vidéos courtes (verticales, {lo} à {hi} secondes) du compte « {brand.get('name') or 'le compte'} » : {brand.get('promesse') or 'des astuces vidéo et IA, simples et vraies'}.",
        f"Public : {brand.get('public') or 'des francophones (Afrique de l’Ouest et centrale, Europe) qui créent du contenu ou vendent avec leur téléphone'}.",
        "Ton : tu tutoies, phrases courtes, concrètes, sans jargon, en français simple. Un personnage dessiné (la mascotte) présente la vidéo.",
        "",
        "FORMAT DE LA VIDÉO — toujours le même :",
        "1. Écran 1, l'ACCROCHE : la promesse dite en une phrase, lisible sur le titre dès la première image. Pas de bonjour, pas de présentation.",
        "2. Écrans 2 à 6 : un point par écran, numéroté avec une « tuile » (ÉTAPE 1, ERREUR 2, PLAN 3…). Chaque écran montre quelque chose : une liste, deux cartes qui s'opposent, des pictogrammes, une séquence filmée.",
        "3. Un des derniers écrans donne la LIMITE honnête (ce que la méthode ne fait pas, ce qu'il faut avoir) ou récapitule.",
        "4. L'écran de fin (abonne-toi + mot à commenter) est ajouté automatiquement : ne l'écris pas.",
        "Rythme : un élément nouveau à l'écran toutes les 1 à 2 secondes, grâce aux repères dans « say ».",
        "",
        "SÉQUENCES FILMÉES (« rushs ») : la vidéo contient 1 à 3 vraies séquences de banque d'images libres de droits.",
        "- bloc « rush » : une séquence qui ILLUSTRE le geste dont tu parles (un téléphone sur trépied, des mains qui emballent un colis…) ;",
        "- bloc « avant_apres » : la séquence brute, puis la même montée (couleurs, zoom, titre, sous-titres, barre) — c'est une vraie démonstration de montage.",
        "Pour chaque séquence tu donnes « q » : 2 à 5 mots ANGLAIS simples pour la recherche (« hands packing box »), et « voir » : en français, ce qu'on doit voir.",
        "Demande des plans simples et faciles à trouver : mains, objets, téléphone, ordinateur, atelier, produit sur une table. Jamais de célébrité, de marque, d'écran d'application précis.",
        "Une séquence de banque d'images n'est jamais « un client », « mon résultat » ou « un témoignage ».",
        "",
        "RÈGLES DE VÉRITÉ (un contrôle automatique refuse tout écart) :",
        *[f"- {r}" for r in garde.resume()],
        "",
        "FORME — un objet JSON, rien d'autre :",
        '{"title": titre complet (12 à 80 caractères), "famille": ' + " | ".join(schema.FAMILLES) + ', "hook_type": ' + " | ".join(schema.HOOKS) + ",",
        ' "couverture": 2 ou 3 lignes de 15 caractères au plus (le texte de la miniature, un mot fort entre *…*),',
        ' "keyword": UN mot de 3 à 10 lettres à écrire en commentaire, "promesse": ce que la vidéo SUIVANTE apportera (40 caractères au plus, ex. « la partie 2 : le script exact »),',
        ' "suite": {"sujet": le sujet précis de cette vidéo suivante, en une phrase},',
        ' "legende": {"accroche": 1 phrase, "points": 2 à 5 lignes (les étapes), "limite": la limite honnête}, "hashtags": 4 à 9, "faits": identifiants des faits vérifiés utilisés, "outils": outils nommés,',
        ' "scenes": 4 à 7 écrans : {"title": 36 caractères au plus, un ou deux mots entre *…*, "tuile": {"label": ' + " | ".join(schema.TUILES) + ', "n": 1 à 9} (jamais sur l\'écran 1),',
        '   "pose": ' + " | ".join(schema.POSES) + ",",
        '   "say": le texte dit par la voix, avec les repères, "blocks": 0 à 2 blocs}}',
        "Blocs permis :",
        ' {"kind":"liste","items":[2 à 5 textes de 28 caractères au plus]}   {"kind":"check","items":[2 à 4 textes de 30 caractères au plus]}',
        ' {"kind":"cartes","cards":[{"tag":"…","text":"20 caractères au plus","ton":"non","note":"facultatif"},{"tag":"…","text":"…","ton":"oui"}]}',
        ' {"kind":"icones","items":[2 à 4 × {"icon": ' + " | ".join(schema.ICONES) + ', "label":"13 caractères au plus"}]}',
        ' {"kind":"chrono","valeur":"…","unite":"…"} (seulement avec un chiffre qui vient d\'un fait vérifié)   {"kind":"fenetre","titre":"Assistant IA","question":"…","reponse":"…"}',
        ' {"kind":"mot","text":"16 caractères au plus","sous":"facultatif"}   {"kind":"etiquette","text":"26 caractères au plus"}   {"kind":"tuiles_video","n":2 à 4}',
        ' {"kind":"rush","q":"…","voir":"…","cadre":"portrait","label":"facultatif, 26 caractères au plus"}',
        ' {"kind":"avant_apres","q":"…","voir":"…","cadre":"portrait","effets":[2 à 5 parmi ' + ", ".join(schema.EFFETS) + '],"titre":"titre incrusté, 24 caractères au plus","sous_titre":"2 à 4 mots"}',
        "Repères dans « say » : [a] fait apparaître le 1er bloc au mot qui suit, [a1] [a2]… ses éléments dans l'ordre (éléments d'une liste, 2 cartes, pictogrammes ; pour « avant_apres » : [a1] = passage à la version montée, puis [a2]… = chaque effet). [b], [b1]… pour le 2e bloc.",
        f"Longueur : {schema.MOTS[0]} à {schema.MOTS[1]} mots prononcés au total (vise 150 à 185). Écran 1 : 8 à 32 mots. Autres écrans : 12 à 55 mots.",
        "Un écran ne peut pas contenir à la fois une séquence « portrait » et une longue liste : une séquence « avant_apres » occupe l'écran à elle seule.",
        "",
        "EXEMPLE de storyboard accepté (ne recopie ni son sujet ni ses phrases) :",
        _exemple(cfg),
    ])


def demande(idee: dict, faits_ok: dict, memo: str = "", recents: list[str] | None = None) -> str:
    lignes = [f"SUJET À TRAITER : {idee.get('sujet')}", f"Famille : {idee.get('famille')}. Type d'accroche à utiliser : {idee.get('hook_type')}."]
    if idee.get("angle"):
        lignes.append(f"Angle : {idee['angle']}")
    if idee.get("suite_de"):
        lignes.append(f"Cette vidéo est la SUITE promise par la vidéo « {idee['suite_de'].get('title', '')} » (mot « {idee['suite_de'].get('keyword', '')} ») : "
                      "commence l'accroche par le fait que c'est la suite.")
    lignes += ["", "FAITS VÉRIFIÉS utilisables (seuls outils et seuls chiffres permis ; cite l'identifiant dans « faits ») :"]
    if faits_ok:
        for fid, f in faits_ok.items():
            lignes.append(f"- {fid} : {f.get('affirmation')} [outils couverts : {', '.join(f.get('outils') or []) or '—'}"
                          + (" ; « gratuit » permis" if f.get("gratuit") else "") + f"] Limite : {f.get('limite') or '—'}")
    else:
        lignes.append("- aucun aujourd'hui : ne nomme aucun outil, ne donne aucun chiffre avec unité.")
    if recents:
        lignes += ["", "Titres déjà publiés (ne refais ni ces titres ni ces accroches) :"] + [f"- {t}" for t in recents[:12]]
    if memo:
        lignes += ["", "CE QUE DISENT LES MESURES DU COMPTE :", memo]
    lignes += ["", "Écris le storyboard complet, en JSON."]
    return "\n".join(lignes)


def write(brain, idee: dict, faits_ok: dict, cfg: dict, memo: str = "", log=print, recents: list[str] | None = None) -> dict:
    """Storyboard écrit par le modèle, déjà contrôlé (forme, garde-fous) et muni de son écran de fin."""
    def valider(obj):
        obj = dict(obj)
        obj.setdefault("famille", idee.get("famille"))
        obj.setdefault("hook_type", idee.get("hook_type"))
        st, _ = controler(obj, cfg, faits_ok, strict=True)
        return st
    st = brain.ask_json(systeme(cfg), demande(idee, faits_ok, memo, recents), validate=valider, retries=int((cfg.get("llm") or {}).get("reprises", 2)),
                        temperature=float((cfg.get("llm") or {}).get("temperature", 0.8)), max_tokens=8192, purpose="storyboard")
    st["sujet"] = idee.get("sujet")
    st["idee"] = idee.get("id")
    if idee.get("suite_de"):
        st["suite_de"] = idee["suite_de"].get("id")
    return st
