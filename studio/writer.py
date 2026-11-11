"""Le scénariste : fiche sujet + dossier de preuve + faits vérifiés -> storyboard JSON.

Le modèle n'invente rien de ce qui se voit : il choisit, dans un dossier de preuve, les extraits de la demande
écrite, les lignes de code et les rendus à montrer, et il écrit la narration qui les relie.

Garde-fous :
  * forme : studio/schema.py répare ou rejette ;
  * fond  : studio/garde.py (extraits mot pour mot, nombres sourcés, formulations, un seul public) ;
            chaque refus est renvoyé au modèle pour correction ;
  * fin   : la phrase de fin est imposée par `apply_cta`, jamais écrite par le modèle ;
  * panne : si aucun modèle ne répond, l'agent prend un storyboard « de réserve » (examples/reserve/),
            écrit à l'avance sur les mêmes dossiers de preuve et soumis aux mêmes contrôles.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import garde, preuves, schema
from .align import MARK, norm
from .config import segment_cfg

# La phrase de fin de TOUTES les vidéos. « MOT » est remplacé par le mot-clé de la vidéo ; rien d'autre ne change.
CTA = "Commente MOT si tu veux la suite. La formation complète est en promo, lien en bio."
HOOKS = {
    "resultat": "résultat d'abord — on montre ce qui a été produit (« Voici ce que cette photo devient… »)",
    "probleme": "problème d'abord — on nomme la difficulté de la personne (« Tu passes trop de temps à refaire… »)",
    "contraste": "contraste ou clarification — on corrige une idée fausse (« Claude n'exporte pas la vidéo lui-même : voilà qui fait quoi. »)",
}
GENERIC_KW = {"LINK", "LIEN", "INFO", "OUI", "YES", "MOT", "GUIDE", "GRATUIT", "CADEAU", "PROMO", "FORMATION", "SUITE", "BIO", "COMMENTE"}
_SENT = re.compile(r"(?<=[.!?…])\s+")

SYSTEM = """Tu es un agent éditorial spécialisé dans les démonstrations FIABLES de création de vidéos, de visuels et de motion design avec Claude, Claude Code, Remotion et les outils associés. Tu écris en français simple, au tutoiement.
Tu ne fais pas de contenu de hype. Tu aides UNE personne précise à comprendre un résultat, à voir comment il a été obtenu, et à choisir un prochain pas.

Tu écris un STORYBOARD en JSON, exécuté tel quel par un moteur de rendu : une voix lit « say », et chaque élément visuel apparaît à l'instant où la voix le cite.

CE QUE TU AS LE DROIT DE MONTRER
Tout ce qui apparaît à l'écran vient du DOSSIER DE PREUVE fourni : la demande écrite, le code réellement écrit, les images et les vidéos réellement rendues. Tu ne simules aucune sortie, tu n'inventes aucun écran, aucun avis, aucun client, aucun résultat de vente.
- Un bloc "brief" recopie un passage de la demande (ou de la correction) MOT POUR MOT. Tu peux couper avec « … », jamais reformuler.
- Un bloc "code" recopie des lignes TELLES QUELLES d'un fichier source du dossier.
- Un média se cite par son repère (ex. "rendu", "v1") : seuls ceux de la liste existent.

STRUCTURE OBLIGATOIRE — "scenes", dans cet ordre
1. "resultat" (0 à 5 s) : la première image montre ce qui a été produit ("visuel"). La première phrase est l'accroche (12 mots maximum, comprise sans contexte). Puis tu nommes la personne et le bénéfice : place le repère [public] juste avant.
2. trois scènes "etape" (5 à 25 s) : trois étapes LIÉES par une progression (par exemple : préparer, demander, vérifier). Chaque étape montre une chose : 1 ou 2 blocs, dont au moins une preuve. Pas de paragraphe.
3. "verif" (25 à 33 s) : on revient au résultat ; 2 ou 3 vérifications réellement faites ("rows") et UNE limite utile ("limite") : un prérequis, un coût, ce qui n'est pas inclus.
La scène finale (appel à l'action) est ajoutée automatiquement : ne l'écris pas, et n'invite nulle part à commenter, à cliquer, à s'abonner ou à recevoir quoi que ce soit.

BLOCS D'UNE ÉTAPE
- {"id":"a","kind":"brief","source":"demande","text":"passage mot pour mot (190 caractères max)","hl":["3 à 6 mots du passage à surligner"]}
- {"id":"a","kind":"code","file":"src/charte.ts","lines":["ligne exacte","ligne exacte"],"hl":2}        (5 lignes max ; hl = numéro de la ligne à surligner)
- {"id":"a","kind":"media","ref":"rendu","label":"Le rendu"}
- {"id":"a","kind":"avant_apres","avant":{"ref":"…","label":"Avant"},"apres":{"ref":"…","label":"Après"}}
- {"id":"a","kind":"erreur","ref":"v1","label":"le défaut en 3 mots","fix":{"ref":"v2","label":"corrigé"}}   (seulement si le média indique où est le défaut)
- {"id":"a","kind":"checklist","label":"TITRE COURT","rows":["3 à 5 mots","…"]}                              (4 lignes max)
- {"id":"a","kind":"compare","rows":[{"text":"…","ok":true},{"text":"…","ok":false}]}
- {"id":"a","kind":"note","text":"une phrase de 12 mots max avec *un passage* accentué"}
- {"id":"a","kind":"pill","text":"3 mots max"}   {"id":"a","kind":"chips","items":["Mot","Mot","Mot"]}
Titres : UN passage entre *astérisques* (il sera accentué). Titre d'étape : un verbe d'action, 2 à 5 mots.

REPÈRES (synchronisation voix / image)
Dans « say », place le repère entre crochets JUSTE AVANT le mot qui déclenche l'élément :
[a] affiche le bloc "a" ; [a1] [a2] déclenchent ses détails (surlignages d'un brief, ligne de code surlignée, lignes d'une liste) ; pour "avant_apres", [a1] lance le passage à « après » ; pour "erreur", [a1] entoure le défaut et [a2] montre la correction.
Dans "verif" : [r1] [r2] [r3] pour les vérifications, [limite] pour la limite.

RÈGLES D'ÉCRITURE
- Une phrase = une idée. Phrases courtes et concrètes. Pas de salutation, pas de « dans cette vidéo », pas de nom de marque avant la démonstration.
- Le texte parlé, le texte à l'écran et l'image disent la même chose. Aucune curiosité qui ne soit pas payée par la vidéo.
- Écris les nombres en chiffres. Tout nombre affiché ou prononcé doit figurer dans le dossier de preuve ou dans un FAIT VÉRIFIÉ que tu cites dans "faits". Une statistique au plus.
- Interdits : « sans effort », « en deux minutes », « explose tes ventes », « détruit », « viral », « garanti », « illimité », « remplace un monteur », « sans coder », toute promesse de revenu, de vues ou de ventes, tout superlatif.
- « gratuit » et « open source » : seulement avec leur précision exacte, dans la même phrase, et en citant le fait vérifié correspondant.
- Vérité technique : un agent de code ÉCRIT le code ; un moteur de rendu comme Remotion CALCULE les images de la vidéo à partir de ce code. Ne dis jamais que Claude ou Claude Code « filme », « monte », « exporte » ou « génère directement » la vidéo.
- Si une information manque (prix, lieu, caractéristique), tu ne l'inventes pas : tu n'en parles pas.

Tu réponds UNIQUEMENT par l'objet JSON, sans texte autour."""

SHAPE = """FORME ATTENDUE
{
  "segment": "%(segment)s",
  "sujet": %(sujet)s,
  "preuve": "%(preuve)s",
  "hooks": [{"type":"resultat","text":"…"},{"type":"probleme","text":"…"},{"type":"contraste","text":"…"}],
  "hook_type": "%(hook)s",
  "hook_pourquoi": "pourquoi cette accroche convient à ce public et à cette preuve, en une phrase (sans promettre de performance)",
  "title": "titre de la vidéo, avec les mots que cette personne taperait dans la recherche",
  "couverture": "texte de couverture, 30 caractères max",
  "keyword": "UNMOT",
  "caption": "légende : 1 à 2 phrases qui décrivent ce que la vidéo montre (la phrase de fin est ajoutée automatiquement)",
  "hashtags": ["3 à 5 mots-clés pertinents, sans #"],
  "faits": ["identifiants des FAITS VÉRIFIÉS réellement utilisés (liste vide si aucun)"],
  "scenes": [
    {"type":"resultat","title":"accroche à l'écran avec *un passage* accentué (40 caractères max)","public":"Si tu … (36 caractères max)","visuel":{"ref":"rendu"},"say":"Accroche. [public]Si tu …, voilà …"},
    {"type":"etape","title":"Verbe *accent*","blocks":[…],"say":"… [a]… [a1]…"},
    {"type":"etape","title":"…","blocks":[…],"say":"…"},
    {"type":"etape","title":"…","blocks":[…],"say":"…"},
    {"type":"verif","title":"Ce que j'ai *vérifié*","visuel":{"ref":"…"},"rows":["vérification faite","vérification faite"],"limite":"la limite utile","source":"adresse courte de la source, si un fait vérifié est cité","say":"… [r1]… [r2]… [limite]…"}
  ]
}
"visuel" de la première scène : {"ref":"…"} pour un seul média, ou {"avant":{"ref":"…","label":"…"},"apres":{"ref":"…","label":"…"}} pour un contraste."""


# --------------------------------------------------------------------------- phrase de fin imposée
def cta_template(cfg: dict) -> str:
    t = re.sub(r"\s+", " ", str((cfg.get("offer") or {}).get("cta") or CTA)).strip()
    if not re.search(r"\bMOT\b", t):
        raise ValueError("offer.cta doit contenir le mot MOT (il est remplacé par le mot-clé de la vidéo)")
    return t


def cta_sentence(cfg: dict, kw: str) -> str:
    return re.sub(r"\bMOT\b", kw, cta_template(cfg), count=1)


def cta_parts(cfg: dict) -> dict:
    """Découpe la phrase imposée pour l'écran : verbe, [mot-clé], fin de la première phrase, seconde phrase."""
    t = cta_template(cfg)
    m = re.match(r"^(?P<verb>.*?)\s*\bMOT\b\s*(?P<l2>[^.!?…]*[.!?…]?)\s*(?P<l3>.*)$", t)
    return {"verb": m.group("verb").strip() or "Commente", "l2": m.group("l2").strip(), "l3": m.group("l3").strip()}


def apply_cta(story: dict, cfg: dict) -> dict:
    """Impose la même fin à chaque vidéo, qu'elle soit écrite par un modèle, de réserve ou à la main.

    Voix    : la phrase imposée, mot pour mot, sans amorce ni ajout.
    Écran   : « Commente » + le mot-clé + « si tu veux la suite. », puis la seconde phrase en entier.
    Légende : le texte du post, débarrassé de tout appel maison, puis la même phrase.
    Rien n'y promet un envoi : commenter ne fait rien recevoir. La fonction est idempotente.
    """
    fixe = re.sub(r"[^A-Z0-9]", "", str((cfg.get("offer") or {}).get("cta_mot_fixe") or "").upper())[: schema.LIMITS["keyword"]]
    kw = fixe or story["keyword"]
    story["keyword"] = kw
    p = cta_parts(cfg)
    cta = story["scenes"][-1]
    if cta.get("type") != "cta":
        cta = {"type": "cta"}
        story["scenes"].append(cta)
    cta.clear()
    cta.update({"type": "cta", "keyword": kw, "verb": p["verb"], "l2": p["l2"], "l3": p["l3"],
                "say": re.sub(r"\s+", " ", f"[kw]{p['verb']} {kw} {p['l2']} [sub]{p['l3']}").strip()})
    sentence = cta_sentence(cfg, kw)
    body = str(story.get("caption") or story.get("title") or "").strip()
    if body.endswith(sentence):
        body = body[: -len(sentence)].strip()
    kept = [x for x in _SENT.split(body) if x.strip() and not any(re.search(rx, x.lower()) for rx, _ in garde.APPEL)]
    body = " ".join(kept).strip() or schema.plain(story.get("title") or "")
    if body and body[-1] not in ".!?…":
        body += "."
    story["caption_corps"] = body[:300 - len(sentence) - 1]
    story["caption"] = f"{story['caption_corps']} {sentence}".strip()
    return story


# --------------------------------------------------------------------------- consigne donnée au modèle
def _segment_block(cfg: dict, segment: str) -> str:
    s = segment_cfg(cfg, segment)
    lines = [f"PUBLIC DE CETTE VIDÉO (un seul) : {s.get('nom', segment)} — {s.get('cible', '')}",
             f"Ce que cette personne veut : {s.get('veut', '')}",
             f"Ce qu'elle ne veut pas : {s.get('ne_veut_pas', '')}",
             "Ses priorités : " + " ; ".join(s.get("priorites") or []),
             "Règles propres à ce public :"] + [f"- {r}" for r in s.get("regles") or []]
    return "\n".join(lines)


def _pack_block(pack: dict) -> str:
    lines = [f"DOSSIER DE PREUVE « {pack['id']} » — {pack.get('titre', '')}"]
    if pack.get("fictif"):
        lines.append("ATTENTION : EXEMPLE FICTIF. Le moteur affiche « EXEMPLE FICTIF » pendant toute la vidéo. Ne le présente jamais comme un vrai "
                     "commerce, un vrai client ou une vraie vente ; dis « exemple » ou « imaginons » une fois dans la narration.")
    if pack.get("offre"):
        lines.append("Offre (seules informations autorisées sur le produit) : " + " ; ".join(f"{k} = {v}" for k, v in pack["offre"].items()))
    lines += ["", "DEMANDE ÉCRITE (demande.md) — à citer mot pour mot :", pack.get("_demande", "")]
    if pack.get("_correction"):
        lines += ["", "CORRECTION DEMANDÉE ENSUITE (correction.md) — à citer mot pour mot :", pack["_correction"]]
    lines += ["", "MÉDIAS DISPONIBLES (repère : ce qu'on y voit)"]
    for ref, m in (pack.get("media") or {}).items():
        kind = "vidéo" if str(m.get("fichier", "")).lower().endswith(preuves.VIDEO) else "image"
        zone = " — indique où est le défaut : utilisable dans un bloc « erreur »" if m.get("zone") else ""
        lines.append(f"- {ref} ({kind}) : {m.get('description', '')}{zone}")
    if pack.get("_sources"):
        lines += ["", "CODE SOURCE (à citer tel quel, lignes courtes de préférence)"]
        for name, src in pack["_sources"].items():
            lines += [f"--- {name}", src.strip()[:2600]]
    lines += ["", "CE QUI EST ÉTABLI PAR CE DOSSIER", preuves.texte_faits(pack)]
    return "\n".join(lines)


def _facts_block(faits: dict[str, dict], ids: list[str]) -> str:
    rows = [faits[i] for i in ids if i in faits]
    if not rows:
        return "FAITS VÉRIFIÉS : aucun pour ce sujet. Tu ne cites donc aucun prix, aucune licence, aucune statistique d'outil."
    out = ["FAITS VÉRIFIÉS PAR LA VEILLE (les seuls prix, licences et fonctionnalités d'outils que tu peux citer)"]
    for f in rows:
        mots = "; ".join(f"« {k} » seulement avec « {' » ou « '.join(v)} »" for k, v in (f.get("mots") or {}).items())
        out.append(f"- [{f['id']}] {f['affirmation']} (source : {f.get('organisme')}, vérifié le {f.get('verifie_le')} ; "
                   f"à l'écran : {f.get('affichage')}). Limite : {f.get('limite')}" + (f" Formulation : {mots}." if mots else ""))
    return "\n".join(out)


def user_prompt(fiche: dict, pack: dict, faits: dict[str, dict], cfg: dict, memo: str = "", refs: list[dict] | None = None) -> str:
    seg = fiche["segment"]
    lo, hi = (cfg.get("video") or {}).get("seconds", [35, 45])
    parts = [_segment_block(cfg, seg), "",
             f"SUJET n° {fiche['n']} : {fiche['sujet']}",
             f"Preuve à montrer : {fiche['preuve_a_montrer']}",
             f"Lien avec la formation (à ne pas citer dans la vidéo) : {fiche['formation']}",
             f"Accroche d'origine à tester (hypothèse, à réécrire avec tes mots) : « {fiche['hook']} »", "",
             "ACCROCHES : écris-en trois, une par type :"] + [f"- {k} : {v}" for k, v in HOOKS.items()] + [
             f"Pour le script final, utilise celle du type « {fiche['hook_type']} » : c'est le seul facteur que l'on change par rapport aux vidéos précédentes.", "",
             f"DURÉE VISÉE : {lo} à {hi} secondes. Écris 72 à 90 mots de narration au total pour tes 5 scènes "
             "(la phrase de fin, 17 mots, s'ajoute ensuite) : environ 14 mots pour « resultat », 16 à 20 par étape, 18 à 22 pour « verif ».", ""]
    if refs:
        parts += ["RÉFÉRENCES PUBLIQUES OBSERVÉES (n'en retiens que la mécanique ; ne recopie ni phrase, ni visuel, ni chiffre)"]
        parts += [f"- {r['nom']} : {r['mecanique']} -> {r['a_retenir']}" for r in refs[:3]] + [""]
    if memo:
        parts += ["CE QUE DISENT LES MESURES DE CE COMPTE", memo, ""]
    parts += [_pack_block(pack), "", _facts_block(faits, fiche.get("faits") or []), "",
              SHAPE % {"segment": seg, "sujet": fiche["n"], "preuve": pack["id"], "hook": fiche["hook_type"]}]
    ex = example_for(cfg, seg)
    if ex:
        parts += ["", "EXEMPLE DE STORYBOARD ACCEPTÉ (autre sujet ou autre accroche — imite la forme et le rythme, pas le contenu)", ex]
    parts += ["", "Écris maintenant le storyboard."]
    return "\n".join(parts)


def example_for(cfg: dict, segment: str) -> str:
    root = Path(cfg.get("_root", ".")) / "examples" / "reserve"
    for f in sorted(root.glob("*.json")):
        try:
            st = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if st.get("segment") == segment:
            st["scenes"] = [s for s in st["scenes"] if s.get("type") != "cta"]
            return json.dumps(st, ensure_ascii=False, indent=1)
    return ""


def controler(story: dict, cfg: dict, pack: dict, faits: dict[str, dict], seconds=None, taken: set | None = None) -> tuple[dict, list[str]]:
    """Forme + fin imposée + fond. Renvoie (storyboard prêt, notes) ou lève StoryError avec TOUS les refus."""
    st, notes = schema.check(story, seconds)
    st = apply_cta(st, cfg)
    problems = garde.controle(st, pack, faits)
    kw = st["keyword"]
    fixe = bool(str((cfg.get("offer") or {}).get("cta_mot_fixe") or "").strip())
    if not fixe:
        if kw in GENERIC_KW or norm(kw) in norm(cta_template(cfg).replace("MOT", "")):
            problems.append("mot-clé trop générique : choisis un mot lié au sujet de la vidéo")
        if taken and kw in {str(k).upper() for k in taken if k}:
            problems.append(f"le mot-clé {kw} est déjà utilisé par une autre vidéo : choisis-en un autre")
    first = _SENT.split(schema.plain(MARK.sub("", st["scenes"][0]["say"])))[0]
    if len(first.split()) > 15:
        problems.append(f"la première phrase fait {len(first.split())} mots : 12 maximum, comprise sans contexte")
    for s in st["scenes"]:
        if s["type"] == "etape" and not MARK.search(s["say"]):
            problems.append(f"l'étape « {schema.plain(s['title'])} » n'a aucun repère [a], [a1]… dans « say »")
    if problems:
        raise schema.StoryError(" ; ".join(dict.fromkeys(problems)))
    return st, notes


def write(brain, fiche: dict, pack: dict, faits: dict[str, dict], cfg: dict, memo: str = "", log=print, taken: set | None = None,
          refs: list[dict] | None = None) -> dict:
    """Appelle le LLM. Renvoie un storyboard contrôlé (lève LLMError/StoryError sinon)."""
    seconds = tuple((cfg.get("video") or {}).get("seconds", [35, 45]))

    def validate(obj):
        if isinstance(obj, dict):
            obj.update({"segment": fiche["segment"], "sujet": fiche["n"], "preuve": pack["id"], "hook_type": fiche["hook_type"]})
        st, notes = controler(obj, cfg, pack, faits, seconds, taken)
        st["_notes"] = notes
        return st
    prompt = user_prompt(fiche, pack, faits, cfg, memo, refs)
    if taken:
        prompt += "\nMots-clés déjà pris (interdits) : " + ", ".join(sorted(str(k) for k in taken if k)[-40:])
    st = brain.ask_json(SYSTEM, prompt, validate=validate, retries=3, max_tokens=4096, purpose="storyboard")
    for n in st.pop("_notes", []):
        log(f"scénariste : {n}")
    return st


# --------------------------------------------------------------------------- réserve
def reserves(cfg: dict) -> list[dict]:
    """Storyboards écrits à l'avance (aucun LLM nécessaire), dans l'ordre des fichiers."""
    out = []
    root = Path(cfg.get("_root", ".")) / "examples" / "reserve"
    for f in sorted(root.glob("*.json")):
        try:
            st = json.loads(f.read_text(encoding="utf-8"))
            st["_reserve"] = f.stem
            out.append(st)
        except json.JSONDecodeError:
            continue
    return out


def reserve_for(cfg: dict, segment: str, sujet: int | None = None, preuve: str | None = None, hook_type: str | None = None,
                skip: set[str] | None = None) -> dict | None:
    """La réserve la plus proche de ce qui était demandé : même sujet et même accroche d'abord, puis même sujet, puis même public."""
    pool = [s for s in reserves(cfg) if s.get("segment") == segment and s["_reserve"] not in (skip or set())]
    if preuve:
        pool = [s for s in pool if s.get("preuve") == preuve] or pool
    for test in (lambda s: s.get("sujet") == sujet and s.get("hook_type") == hook_type, lambda s: s.get("sujet") == sujet, lambda s: True):
        hit = [s for s in pool if test(s)]
        if hit:
            return hit[0]
    return None
