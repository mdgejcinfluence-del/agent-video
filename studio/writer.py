"""Le scénariste : brief + faits sourcés -> storyboard JSON (hook, sections, appel à l'action).

Garde-fous :
  * forme : studio/schema.py répare ou rejette ;
  * fond  : tout nombre affiché ou prononcé doit figurer dans les faits fournis (sinon le
            storyboard est refusé et l'erreur est renvoyée au modèle pour correction) ;
  * panne : si aucun modèle gratuit ne répond, l'agent publie un storyboard « de réserve »
            (examples/evergreen/), écrit à l'avance et vérifié, jamais deux fois le même.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import schema
from .align import MARK, norm
from .strategist import FORMATS, HOOKS, LENGTHS

SYSTEM = """Tu es scénariste de vidéos verticales « motion design » (TikTok, Reels) en français, au tutoiement.
Tu écris un STORYBOARD en JSON, exécuté tel quel par un moteur de rendu : une voix off lit « say », et les éléments visuels apparaissent à l'instant précis où la voix les cite.

STRUCTURE OBLIGATOIRE
- "scenes" contient, dans l'ordre : 1 scène "hook", puis 2 à 4 scènes "section", puis 1 scène "cta".

RÈGLES D'ÉCRITURE (ce qui fait qu'une vidéo est regardée jusqu'au bout)
1. La première phrase du hook est la promesse, en 14 mots maximum, avec un bénéfice ou un chiffre concret. Jamais de bonjour, jamais « dans cette vidéo ».
2. Phrases courtes, mots simples, verbes d'action. Tu parles à UNE personne (« tu »). Zéro remplissage.
3. Une idée par section. Narration d'une section : 18 à 36 mots.
4. Les noms de produits restent tels quels. Les descriptions fournies en anglais sont reformulées en français naturel.
5. Écris les nombres en chiffres dans « say » (« 40 requêtes »), jamais en lettres.

REPÈRES (synchronisation voix / image)
- Dans « say », place un repère entre crochets JUSTE AVANT le mot qui déclenche l'élément : [a] affiche le bloc d'id "a" ; [a1], [a2]… affichent les lignes 1, 2… du bloc "a" ; dans le hook : [stamp] et [pill].
- Chaque bloc doit avoir son repère, dans l'ordre où la voix en parle.

BLOCS POSSIBLES DANS UNE SECTION (1 à 3 par section, textes TRÈS courts)
- {"id":"a","kind":"checklist","label":"NOM DE L'OUTIL","rows":["3 à 5 mots","…"]}            (2 à 4 lignes de 30 caractères max)
- {"id":"b","kind":"stat","label":"CE QUE C'EST","value":550,"unit":"milliards"}              (value = nombre ; unit = 1 ou 2 mots)
- {"id":"c","kind":"pill","text":"3 mots maximum"}
- {"id":"d","kind":"terminal","label":"terminal","text":"commande courte"}                   (seulement pour une vraie commande fournie dans les faits)
- {"id":"e","kind":"chips","items":["Mot","Mot","Mot"]}                                       (2 à 4 mots-clés)
- {"id":"f","kind":"compare","label":"À SAVOIR","rows":[{"text":"…","ok":true},{"text":"…","ok":false}]}   (ok=false affiche une croix rouge)
- {"id":"g","kind":"note","text":"une phrase de 12 mots max avec *un passage* en accent"}
Titres : mets UN passage entre *astérisques* (il sera en italique coloré). Titre de section : 2 à 4 mots.
"icon" de section, au choix : screen, play, pencil, cursor, bulb, star, bolt, coin, chat, chart, rocket, check, gear.

EXACTITUDE (non négociable)
- Tu n'utilises QUE les faits de la rubrique FAITS. Tout nombre affiché ou prononcé doit y figurer tel quel.
- Aucune statistique, aucun prix, aucune date, aucune fonctionnalité inventés. Si une information manque, n'en parle pas.
- Pas de promesse de gain d'argent, pas de « illimité », pas de superlatif invérifiable.

APPEL À L'ACTION
- "keyword" : UN mot en majuscules (10 lettres max), lié au sujet, facile à écrire.
- Dans la scène "cta", « say » contient UNE seule question courte (10 mots max) qui donne envie d'apprendre à le faire soi-même. Elle ne contient pas le mot-clé. La suite (« Commente MOT… », renvoi vers le lien en bio) est ajoutée automatiquement : ne l'écris pas.
- Tu ne promets JAMAIS un envoi (ni guide, ni lien, ni message privé) et tu n'annonces rien à « récupérer » ou à « recevoir ».

Tu réponds UNIQUEMENT par l'objet JSON, sans texte autour."""

SHAPE = """FORME ATTENDUE
{
  "title": "titre de la vidéo (pour la légende)",
  "keyword": "MOT",
  "caption": "légende du post, 1 à 2 phrases, SANS appel à commenter et sans parler de lien (la fin de la légende est ajoutée automatiquement)",
  "hashtags": ["5 mots-clés sans #"],
  "scenes": [
    {"type":"hook","kicker":"sujet · angle","title":"*passage accentué* reste du titre","chips":["élément 1","élément 2","élément 3"],"stamp":"2 mots max","pill":"2 mots max","say":"… [stamp]… [pill]…"},
    {"type":"section","title":"Mot *accent*","icon":"bulb","blocks":[…],"say":"… [a]… [a1]… [a2]… [b]…"},
    {"type":"cta","keyword":"MOT","say":"Une question courte qui donne envie d'apprendre à le faire soi-même ?"}
  ]
}"""


# Fin commune à TOUTES les vidéos. Réglable dans config.yaml (offer.cta_*), jamais laissée au modèle.
CTA_DEFAULT = {
    "cta_comment": "si tu veux la suite",                                 # dit après « Commente MOT »
    "cta_say": "La formation complète est en promo, lien en bio.",        # dernière phrase prononcée
    "cta_sub": "la formation est en promo, lien en bio",                  # écrit à l'écran sous le mot-clé
    "caption_end": "La formation complète est en promo : lien en bio.",   # fin de la légende du post
    "cta_lead": "Tu veux apprendre à le faire toi-même ?",                # question d'amorce par défaut
}
# ce qu'une vidéo ne doit jamais laisser croire : qu'un commentaire déclenche un envoi
PROMISE = re.compile(r"\b(guides?|envoi\w*|t'envoie\w*|dm|messages? priv\w+|re[cç]oi\w*|recev\w+|r[ée]cup[èe]r\w*|offert\w*|cadeau\w*|lien|bio)\b", re.I)
_SENT = re.compile(r"(?<=[.!?…])\s+")


def cta_texts(cfg: dict) -> dict:
    offer = cfg.get("offer") or {}
    return {k: re.sub(r"\s+", " ", str(offer.get(k) or v)).strip() for k, v in CTA_DEFAULT.items()}


def _end(s: str) -> str:
    s = s.strip()
    return s if not s or s[-1] in ".!?…" else s + "."


def apply_cta(story: dict, cfg: dict) -> dict:
    """Impose la même fin à chaque vidéo, qu'elle soit écrite par un modèle, de réserve ou à la main.

    Voix   : « <question d'amorce> Commente MOT si tu veux la suite. La formation complète est en promo, lien en bio. »
    Écran  : la carte « Commente “MOT” » puis la ligne manuscrite (offer.cta_sub).
    Légende: le texte du post, débarrassé de tout appel maison, puis la même fin.
    Rien n'y promet un envoi : commenter ne fait rien recevoir, le lien en bio est celui de la formation.
    La fonction est idempotente (l'appliquer deux fois ne change rien).
    """
    t = cta_texts(cfg)
    kw = story["keyword"]
    cta = story["scenes"][-1]
    nk = norm(kw)
    raw = str(cta.get("say") or "")
    head = raw.split("[kw]")[0] if "[kw]" in raw else re.split(r"(?i)\bcommente", raw)[0]
    first = _SENT.split(schema.plain(MARK.sub(" ", head)))[0].strip()
    lead = first if (first.endswith("?") and 3 <= len(first.split()) <= 14 and not PROMISE.search(first) and nk not in norm(first)) else t["cta_lead"]
    if nk in norm(lead):
        lead = ""
    cta["say"] = re.sub(r"\s+", " ", f"{lead} [kw]Commente {kw} {t['cta_comment'].rstrip('.!? ')}. [sub]{_end(t['cta_say'])}").strip()
    cta["sub"] = schema._cut(t["cta_sub"], schema.LIMITS["sub"], [], "sous-texte") or None
    cta["verb"] = "Commente"
    kept = [x for x in _SENT.split(str(story.get("caption") or story.get("title") or "").strip())
            if x.strip() and not PROMISE.search(x) and not re.search(r"(?i)\bcommente", x)]
    body = _end(" ".join(kept).strip() or schema.plain(story.get("title") or ""))
    story["caption"] = f"{body} Commente {kw} {t['cta_comment'].rstrip('.!? ')}. {_end(t['caption_end'])}"[:300]
    return story


def facts_block(items: list[dict], extra: list[str] | None = None) -> str:
    lines = []
    for c in items:
        lines.append(f"### {c.get('title', '')} — source : {c.get('url', '')}")
        lines += [f"- {f}" for f in c.get("facts", [])]       # pas de numérotation : elle se mélangerait aux chiffres des faits
        if c.get("readme"):
            lines.append(f"- Extrait de la documentation (anglais) : {c['readme']}")
    lines += [f"- {f}" for f in extra or []]
    return "\n".join(lines)


def allowed_numbers(facts_text: str, cfg: dict) -> set[str]:
    blob = facts_text + " | " + json.dumps(cfg.get("offer") or {}, ensure_ascii=False)
    return {str(i) for i in range(0, 11)} | schema.find_numbers(blob)


def user_prompt(brief: dict, topic: dict, facts_text: str, cfg: dict, memo: str = "") -> str:
    niche, offer = cfg.get("niche") or {}, cfg.get("offer") or {}
    lo, hi = LENGTHS.get(brief.get("length", "court"), (28, 40))
    shape = SHAPE
    example = (Path(cfg.get("_root", ".")) / "examples" / "demo_storyboard.json")
    ex = example.read_text(encoding="utf-8") if example.exists() else ""
    brand = ((cfg.get("brand") or {}).get("name") or "").strip()
    parts = ([f"MARQUE : {brand}"] if brand else []) + [
        f"NICHE : {niche.get('description', '')}",
        f"CIBLE : {niche.get('audience', '')}",
        f"TON : {niche.get('tone', '')}",
    ] + ([f"LIGNE ÉDITORIALE (à respecter absolument) : {niche['line']}"] if niche.get("line") else []) + [
        "",
        f"FORMAT DE CETTE VIDÉO : {brief['format']} — {FORMATS.get(brief['format'], '')}",
        f"TYPE D'ACCROCHE : {HOOKS.get(brief.get('hook', 'promesse'), '')}",
        f"DURÉE VISÉE : {lo} à {hi} secondes, soit {int(lo * 3.2) - 16} à {int(hi * 3.4) - 16} mots de narration au total "
        "(la phrase de fin automatique n'est pas comptée).",
    ]
    if topic.get("angle"):
        parts.append(f"ANGLE : {topic['angle']}")
    if brief["format"] == "offre":
        parts += ["", "Cette vidéo présente la formation. Le hook nomme le problème de la cible, les sections montrent ce qu'elle contient. "
                  "Tu n'annonces ni prix ni contenu qui ne figure pas dans les FAITS."]
    if memo:
        parts += ["", "CE QUI MARCHE SUR CE COMPTE (statistiques réelles)", memo]
    parts += ["", "FAITS (seule source autorisée)", facts_text, "", shape]
    if ex:
        parts += ["", "EXEMPLE DE STORYBOARD RÉUSSI (autre sujet — imite la forme et le rythme, pas le contenu)", ex]
    parts += ["", "Écris maintenant le storyboard."]
    return "\n".join(parts)


def make_validator(facts_text: str, cfg: dict, seconds: tuple[float, float], taken: set | None = None):
    ok_numbers = allowed_numbers(facts_text, cfg)
    taken = {str(k).upper() for k in (taken or set()) if k}

    def validate(obj):
        st, notes = schema.check(obj, seconds)
        bad = sorted(n for n in schema.numbers_in(st) if n not in ok_numbers)
        if bad:
            raise schema.StoryError("ces nombres n'apparaissent pas dans les FAITS : " + ", ".join(bad) +
                                    ". Retire-les ou remplace-les par un nombre présent dans les FAITS")
        hook = st["scenes"][0]
        first = re.split(r"(?<=[.!?…])\s", schema.plain(MARK.sub("", hook["say"])))[0]
        if len(first.split()) > 18:
            raise schema.StoryError(f"la première phrase du hook fait {len(first.split())} mots : 14 maximum")
        fixed = norm(" ".join(cta_texts(cfg).values()))
        if st["keyword"] in {"LINK", "LIEN", "INFO", "OUI", "YES", "MOT", "GUIDE", "GRATUIT", "CADEAU"} or norm(st["keyword"]) in fixed:
            raise schema.StoryError("mot-clé trop générique : choisis un mot lié au sujet de la vidéo")
        if st["keyword"] in taken:
            raise schema.StoryError(f"le mot-clé {st['keyword']} est déjà utilisé par une autre vidéo : choisis-en un autre")
        for s in st["scenes"]:
            if s["type"] == "section" and not MARK.search(s["say"]):
                raise schema.StoryError(f"la section « {schema.plain(s['title'])} » n'a aucun repère [a], [a1]… dans « say »")
        st["_notes"] = notes
        return st
    return validate


def write(brain, brief: dict, topic: dict, cfg: dict, memo: str = "", log=print, taken: set | None = None) -> dict:
    """Appelle le LLM. Renvoie un storyboard validé (lève LLMError/StoryError sinon)."""
    offer = cfg.get("offer") or {}
    extra = []
    if brief["format"] == "offre":
        extra = [f"Nom de la formation : {offer.get('name', '')}", f"Promesse : {offer.get('promise', '')}"]
        if offer.get("price"):
            extra.append(f"Prix : {offer['price']}")
        extra += [f"Contenu : {p}" for p in (offer.get("points") or [])]
    facts_text = facts_block(topic.get("items", []), extra)
    lo, hi = LENGTHS.get(brief.get("length", "court"), (28, 40))
    seconds = (max(18, lo - 6), hi + 8)
    validate = make_validator(facts_text, cfg, seconds, taken)
    prompt = user_prompt(brief, topic, facts_text, cfg, memo)
    if taken:
        prompt += "\nMots-clés déjà pris (interdits) : " + ", ".join(sorted(str(k) for k in taken if k)[-40:])
    st = brain.ask_json(SYSTEM, prompt, validate=validate, retries=3,
                        max_tokens=4096, purpose="storyboard")
    for n in st.pop("_notes", []):
        log(f"scénariste : {n}")
    return st


def evergreen(cfg: dict, state, log=print, rehearsal: bool = False) -> dict | None:
    """Storyboard de réserve (aucun LLM nécessaire).

    En publication réelle, chaque fichier ne sert qu'une fois (on ne poste jamais deux fois la même vidéo).
    En mode essai, la réserve tourne en boucle et rien n'est consommé : elle sera intacte le jour du lancement.
    """
    root = Path(cfg.get("_root", ".")) / "examples" / "evergreen"
    files = sorted(root.glob("*.json"))
    used = set(state.load("seen", {"ids": [], "titles": []})["ids"])
    if rehearsal and files:
        k = int(state.load("essais", {"n": 0}).get("n", 0)) % len(files)
        files = files[k:] + files[:k]
    else:
        files = [f for f in files if f"evergreen:{f.stem}" not in used]
    for f in files:
        try:
            st = json.loads(f.read_text(encoding="utf-8"))
            st, _ = schema.check(st, None)
            st["_evergreen"] = f.stem
            log(f"scénariste : storyboard de réserve « {f.stem} »" + (" (essai : la réserve n'est pas consommée)" if rehearsal else ""))
            return st
        except Exception as e:  # noqa: BLE001
            log(f"scénariste : réserve {f.name} invalide ({e})")
    return None
