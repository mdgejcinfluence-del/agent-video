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
FIN_EBOOK = (" [promo]Et si tu veux découvrir tous les prompts pour ChatGPT, Gemini, Claude, le business, les images, les vidéos, les études et bien plus encore, "
             "notre e-book complet est disponible à seulement PRIX. Clique sur le lien en bio pour le découvrir.")
ECRAN_EBOOK = "E-book complet · *PRIX* · lien en bio"


def ebook_actif(cfg: dict, today: dt.date | None = None) -> bool:
    """L'e-book n'est annoncé que s'il est réellement en vente : offer.ebook.en_vente à true ET un lien en bio renseigné.
    (Annoncer un produit qui n'existe pas encore serait une fausse disponibilité.)"""
    o = cfg.get("offer") or {}
    e = o.get("ebook") or {}
    return bool(e.get("en_vente")) and bool(str(o.get("lien_bio") or "").strip()) and bool(str(e.get("prix") or "").strip())


promo_active = ebook_actif          # ancien nom (la « formation en promo » de la première version), gardé pour les appels existants


def phrase_ebook(cfg: dict, graine: str = "") -> str:
    """La phrase commerciale : la formulation imposée, ou l'une de ses variantes (mêmes trois informations : e-book complet, prix, lien en bio)."""
    e = (cfg.get("offer") or {}).get("ebook") or {}
    prix = str(e.get("prix") or "").strip()
    choix = [str(e.get("cta") or FIN_EBOOK)] + [str(v) for v in (e.get("variantes") or []) if str(v).strip()]
    ok = []
    for c in choix:
        c = c.replace("PRIX", prix)
        if "e-book" in c.lower() and prix in c and "lien en bio" in c.lower():
            ok.append(c if c.startswith(" ") else " " + c)
    if not ok:
        ok = [FIN_EBOOK.replace("PRIX", prix)]
    return ok[sum(map(ord, graine)) % len(ok)]


def fin_scene(story: dict, cfg: dict) -> dict:
    """L'écran de fin, imposé : abonne-toi + mot à commenter + ce que la suite apportera (+ l'e-book quand il est réellement en vente)."""
    o = cfg.get("offer") or {}
    kw = (str(o.get("cta_mot_fixe") or "").strip() or story["keyword"]).upper()
    prom = schema.visible(story.get("promesse") or "la suite").rstrip(".! ")
    say = (o.get("cta") or FIN_SUITE).replace("MOT", kw).replace("PROMESSE", prom)
    sc = {"type": "fin", "keyword": kw, "promesse": prom, "pose": "pouce"}
    if ebook_actif(cfg):
        e = o.get("ebook") or {}
        say += phrase_ebook(cfg, str(story.get("title") or ""))
        if "[promo]" not in say:
            say = say.replace(" Et si ", " [promo]Et si ", 1) if " Et si " in say else say
        sc["promo"] = str(e.get("ecran") or ECRAN_EBOOK).replace("PRIX", str(e.get("prix") or ""))
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
    r = reserve(cfg, "p1_business") or (reserves(cfg) or [{}])[0]
    r = {k: v for k, v in r.items() if k not in ("_reserve", "suite")}
    for f in r.get("prompts") or []:
        f.pop("resultat_exemple", None)
    return json.dumps(r, ensure_ascii=False)


QUESTIONS_SUJET = [
    "Ce sujet peut-il réellement intéresser un jeune ?",
    "Le spectateur va-t-il découvrir quelque chose d'utile ?",
    "Y a-t-il un prompt ou une commande concrète à montrer ?",
    "La démonstration se comprend-elle rapidement ?",
    "Le résultat donne-t-il envie de tester ?",
    "Le sujet a-t-il sa place dans la future bibliothèque de prompts ?",
    "Existe-t-il déjà une vidéo trop proche dans l'historique ?",
]


def systeme(cfg: dict) -> str:
    brand = cfg.get("brand") or {}
    ed = cfg.get("editorial") or {}
    v = cfg.get("video") or {}
    lo, hi = (v.get("seconds") or [40, 70])[:2]
    base = ", ".join(ed.get("outils_de_base") or ["ChatGPT", "Gemini", "Claude"])
    return "\n".join([
        f"Tu écris les vidéos courtes (verticales, {lo} à {hi} secondes) du compte « {brand.get('name') or 'le compte'} » : {brand.get('promesse') or 'chaque jour, un prompt, une commande ou une technique d’IA à copier'}.",
        f"Public : {brand.get('public') or 'des jeunes francophones, débutants avec l’intelligence artificielle'}.",
        "Le compte est spécialisé dans les PROMPTS, les COMMANDES et les TECHNIQUES d'utilisation des intelligences artificielles. "
        "Il ne publie plus de conseils généraux de commerce, de réglages de caméra ou de montage vidéo.",
        "Ton : tu tutoies, phrases courtes, concrètes, sans jargon, en français simple. Ne suppose jamais que le spectateur connaît déjà l'outil. Un personnage dessiné (la mascotte) présente la vidéo.",
        "",
        "CHAQUE VIDÉO EST UNE DÉMONSTRATION que le spectateur peut refaire : « Ouvre l'outil. Copie exactement cette instruction. Voici ce que tu obtiens. »",
        "Jamais une vidéo qui dit seulement « l'IA peut faire ceci ». Jamais de définition, jamais de conseil général sans instruction à copier.",
        "Une vidéo = UN outil nommé. Ne mélange pas les fonctions de plusieurs plateformes.",
        "",
        "FORMAT DE LA VIDÉO — toujours le même :",
        "1. Écran 1, l'ACCROCHE : le problème du spectateur ou le résultat, en une phrase, lisible sur le titre dès la première image. Pas de bonjour.",
        "2. Écran « ouvre l'outil et copie ceci » : un bloc « prompt » affiche le TEXTE EXACT de l'instruction (il vient de la fiche « prompts »). La voix en dit l'essentiel, pas forcément chaque mot.",
        "3. Écran « adapte » : ce que le spectateur remplace (les [champs entre crochets]) ou l'endroit précis où saisir l'instruction.",
        "4. Écran « résultat » : un bloc « reponse » montre un extrait de ce que l'IA répond (2 à 5 lignes courtes). L'agent teste réellement l'instruction et remplace ces lignes par un extrait de la vraie réponse : écris des lignes plausibles, sans chiffre inventé.",
        "   (Pour un réglage ou une commande qui ne produit pas de réponse, remplace cet écran par « ce que ça change » : deux cartes avant / après, ou une liste.)",
        "5. Un des derniers écrans dit la LIMITE honnête : ce qu'il faut vérifier, ce qui dépend de l'offre, de la version ou du pays.",
        "6. L'écran de fin (abonne-toi + mot à commenter) est ajouté automatiquement : ne l'écris pas, et ne parle jamais d'e-book ni de lien en bio.",
        "Rythme : un élément nouveau à l'écran toutes les 1 à 2 secondes, grâce aux repères dans « say ».",
        "",
        "LES FICHES « prompts » (1 à 5) — c'est ce qui entre dans la bibliothèque du compte :",
        ' {"titre": ce que fait l\'instruction, "outil": UN outil, "type": "prompt" | "commande" | "reglage", "fonction": à quoi elle sert, '
        f'"texte": l\'instruction EXACTE à copier ({schema.PROMPT_MAX} caractères au plus), "exemple": {{une valeur pour chaque [champ]}}, '
        '"resultat_attendu": ce que l\'IA rend, "personnalisation": ce qu\'il faut remplacer ou ajouter}',
        "Écris des instructions précises et directement utilisables : un rôle, le contexte de la personne, la demande, la forme de la réponse, et une garde-fou "
        "(« ne promets pas de gain », « pose-moi une question si ce n'est pas clair »). Mets entre [crochets] ce que chacun doit remplacer : [ville], [montant], [matière].",
        "Ancre les exemples dans la vie du public : Cotonou, Lomé, Abidjan, Dakar ; des montants en FCFA ; un étudiant, une vendeuse en ligne, un couturier, un créateur de contenu.",
        "",
        "AVANT D'ÉCRIRE, le sujet doit passer ces questions (sinon change d'angle) :",
        *[f"- {q}" for q in QUESTIONS_SUJET],
        "",
        f"OUTILS : {base} peuvent être nommés librement comme l'endroit où coller une instruction. "
        "Pour parler d'une FONCTION précise (un menu, une commande, un réglage, « gratuit », une limite), il faut un fait vérifié de la liste fournie, cité dans « faits ». "
        "Quand une fonction dépend d'une offre, d'un pays, d'une version ou d'une application, dis-le.",
        "",
        "SÉQUENCES FILMÉES (« rushs ») : la vidéo contient 1 à 3 vraies séquences de banque d'images libres de droits, qui montrent la SITUATION du spectateur "
        "(des mains sur un clavier, un étudiant qui révise, une vendeuse et ses colis, un téléphone tenu en main). Place la première sur l'écran d'accroche.",
        "Pour chaque séquence tu donnes « q » : 2 à 5 mots ANGLAIS simples pour la recherche (« student studying laptop »), et « voir » : en français, ce qu'on doit voir.",
        "Jamais de célébrité, de marque, d'écran d'application précis. Une séquence de banque d'images n'est jamais « un client », « mon résultat » ou « un témoignage ».",
        "",
        "RÈGLES DE VÉRITÉ (un contrôle automatique refuse tout écart) :",
        *[f"- {r}" for r in garde.resume()],
        "",
        "FORME — un objet JSON, rien d'autre :",
        '{"title": titre complet (12 à 80 caractères), "famille": ' + " | ".join(schema.FAMILLES) + ', "hook_type": ' + " | ".join(schema.HOOKS) + ",",
        ' "couverture": 2 ou 3 lignes de 15 caractères au plus (le texte de la miniature, un mot fort entre *…*),',
        ' "keyword": UN mot de 3 à 10 lettres à écrire en commentaire, "promesse": ce que la vidéo SUIVANTE apportera (40 caractères au plus, ex. « la suite : le prompt pour tes clients »),',
        ' "suite": {"sujet": le sujet précis de cette vidéo suivante, en une phrase},',
        ' "prompts": [1 à 5 fiches, voir plus haut],',
        ' "legende": {"accroche": 1 phrase, "points": 2 à 5 lignes (les étapes), "limite": la limite honnête}, "hashtags": 4 à 9, "faits": identifiants des faits vérifiés utilisés, "outils": outils nommés,',
        ' "scenes": 4 à 7 écrans : {"title": 36 caractères au plus, un ou deux mots entre *…*, "tuile": {"label": ' + " | ".join(schema.TUILES) + ', "n": 1 à 9} (jamais sur l\'écran 1),',
        '   "pose": ' + " | ".join(schema.POSES) + ",",
        '   "say": le texte dit par la voix, avec les repères, "blocks": 0 à 2 blocs}}',
        "Blocs permis :",
        ' {"kind":"prompt","n":1} affiche le texte exact de la fiche n° 1 (fenêtre de l\'outil, texte tapé au clavier, [champs] surlignés) — seul sur son écran',
        f' {{"kind":"reponse","n":1,"titre":"40 caractères au plus","lignes":[{schema.LIGNES_REPONSE[0]} à {schema.LIGNES_REPONSE[1]} lignes de {schema.LIGNE_MAX} caractères au plus]}} extrait de la réponse à la fiche n° 1 — seul sur son écran',
        ' {"kind":"liste","items":[2 à 5 textes de 28 caractères au plus]}   {"kind":"check","items":[2 à 4 textes de 30 caractères au plus]}',
        ' {"kind":"cartes","cards":[{"tag":"…","text":"20 caractères au plus","ton":"non","note":"facultatif"},{"tag":"…","text":"…","ton":"oui"}]}',
        ' {"kind":"icones","items":[2 à 4 × {"icon": ' + " | ".join(schema.ICONES) + ', "label":"13 caractères au plus"}]}',
        ' {"kind":"chrono","valeur":"…","unite":"…"} (seulement avec un chiffre qui vient d\'un fait vérifié)',
        ' {"kind":"mot","text":"16 caractères au plus","sous":"facultatif"}   {"kind":"etiquette","text":"26 caractères au plus"}',
        ' {"kind":"rush","q":"…","voir":"…","cadre":"portrait","label":"facultatif, 26 caractères au plus"}',
        "Repères dans « say » : [a] fait apparaître le 1er bloc au mot qui suit, [a1] [a2]… ses éléments dans l'ordre (éléments d'une liste, 2 cartes, lignes d'une réponse). [b], [b1]… pour le 2e bloc.",
        f"Longueur : {schema.MOTS[0]} à {schema.MOTS[1]} mots prononcés au total (vise 150 à 185). Écran 1 : 8 à 32 mots. Autres écrans : 12 à 55 mots.",
        "Écris les nombres dits par la voix en toutes lettres quand ils viennent de l'exemple (« cinquante mille francs »).",
        "",
        "EXEMPLE de storyboard accepté (ne recopie ni son sujet ni ses phrases) :",
        _exemple(cfg),
    ])


def demande(idee: dict, faits_ok: dict, memo: str = "", recents: list[str] | None = None) -> str:
    lignes = [f"SUJET À TRAITER : {idee.get('sujet')}", f"Famille : {idee.get('famille')}. Type d'accroche à utiliser : {idee.get('hook_type')}."]
    if idee.get("outil"):
        lignes.append(f"Outil de cette vidéo : {idee['outil']} (un seul outil).")
    if idee.get("angle"):
        lignes.append(f"Angle : {idee['angle']}")
    if idee.get("suite_de"):
        lignes.append(f"Cette vidéo a été annoncée à la fin de la vidéo « {idee['suite_de'].get('title', '')} » (mot « {idee['suite_de'].get('keyword', '')} ») : "
                      "tu peux le rappeler en quelques mots (« comme promis »), mais elle doit se comprendre seule.")
    if idee.get("prochaine"):
        lignes.append(f"LA VIDÉO SUIVANTE du compte sera : « {idee['prochaine'].get('sujet')} ». « promesse » doit l'annoncer (40 caractères au plus, "
                      "commence par « la suite : »), et « suite » vaut {\"sujet\": ce sujet}.")
    lignes += ["", "FAITS VÉRIFIÉS utilisables (seules fonctions, seules commandes et seuls chiffres permis ; cite l'identifiant dans « faits ») :"]
    hors_ligne = {"remotion", "pexels", "pixabay"}                 # faits de l'ancienne ligne (montage, banques d'images) : gardés, mais plus proposés
    utiles = {fid: f for fid, f in (faits_ok or {}).items()
              if fid in (idee.get("faits") or []) or not {str(o).lower() for o in (f.get("outils") or [])} & hors_ligne}
    if utiles:
        for fid, f in utiles.items():
            lignes.append(f"- {fid} : {f.get('affirmation')} [outils couverts : {', '.join(f.get('outils') or []) or '—'}"
                          + (f" ; commandes permises : {', '.join(f.get('commandes') or [])}" if f.get("commandes") else "")
                          + (f" ; menus : {' › '.join(f.get('menus') or [])}" if f.get("menus") else "")
                          + (" ; « gratuit » permis" if f.get("gratuit") else "") + f"] Limite : {f.get('limite') or '—'}")
    else:
        lignes.append("- aucun aujourd'hui : ne décris aucune fonction précise d'un outil, ne montre aucune commande, ne donne aucun chiffre avec unité.")
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
    if idee.get("prochaine"):                                    # la suite annoncée est un sujet déjà choisi dans la banque
        st["suite"] = {"sujet": idee["prochaine"].get("sujet"), "idee": idee["prochaine"].get("id")}
    if idee.get("suite_de"):
        st["suite_de"] = idee["suite_de"].get("id")
    return st
