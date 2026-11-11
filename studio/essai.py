"""L'essai de chaque instruction avant de la montrer.

La règle de la ligne éditoriale : « chaque prompt doit être vérifié ». L'agent ne sait vérifier que deux façons :

  * un PROMPT (texte donné à une IA) : il est réellement envoyé à Gemini, [champs] remplis par les valeurs d'exemple.
    La réponse est gardée dans la fiche ; l'écran « réponse » de la vidéo montre un extrait de CETTE réponse, et la
    mention dit d'où elle vient (« Réponse de Gemini · testée le … »).
  * une COMMANDE ou un RÉGLAGE d'un outil (ChatGPT, Claude Code…) : l'agent ne peut pas cliquer dans l'application.
    Il vérifie que la page officielle citée (un fait de data/faits.yaml) a été relue et confirmée aujourd'hui.

Sans clé GEMINI_API_KEY, un prompt reste « à vérifier » : la vidéo peut être fabriquée en essai (l'écran « réponse »
porte alors la mention « Exemple de réponse »), mais elle n'est jamais publiée (voir porte.py).
"""
from __future__ import annotations

import copy
import datetime as dt
import re
import unicodedata

from . import align, schema

MENTION_EXEMPLE = "Exemple de réponse · elle varie à chaque essai"

EXTRAIRE = """Tu prépares l'écran « réponse » d'une vidéo courte. On te donne la VRAIE réponse d'une IA à une instruction.
Rends un objet JSON {"titre": "...", "lignes": ["...", ...], "dit": "..."}.
- « titre » : 40 caractères au plus, ce que contient la réponse (ex. « 5 idées avec 50 000 FCFA »).
- « lignes » : exactement le nombre de lignes demandé, 48 caractères au plus chacune. Chaque ligne REPREND un élément de la réponse, avec ses mots
  et ses chiffres. Tu peux raccourcir, jamais ajouter : aucun mot important ni aucun chiffre qui ne figure pas dans la réponse.
- « dit » : la phrase que la voix prononce pendant que les lignes apparaissent (20 à 45 mots, français simple, tutoiement), avec un repère [a1] juste
  avant le passage qui correspond à la ligne 1, [a2] pour la ligne 2, etc. Commence par [a] (« [a]Voici ce que l'IA répond : [a1]… »).
  N'écris pas « j'ai testé ». Ne promets aucun gain. Écris les nombres en toutes lettres."""


def _n(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s).lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def nom_public(modele: str) -> str:
    """« gemini/gemini-3.8-flash » -> « Gemini »."""
    m = str(modele or "").lower()
    return "Gemini" if "gemini" in m else (modele.split("/")[0].capitalize() if modele else "une IA")


def fidele(ligne: str, reponse: str) -> bool:
    """Une ligne d'extrait est fidèle si ses mots importants (4 lettres et plus) et tous ses nombres figurent dans la réponse."""
    rep = " " + _n(reponse) + " "
    mots = [w for w in _n(schema.visible(ligne)).split() if len(w) >= 4 or w.isdigit()]
    if not mots:
        return True
    nombres = [w for w in mots if w.isdigit()]
    if any(f" {w} " not in rep and w not in rep.replace(" ", "") for w in nombres):
        return False
    vus = sum(1 for w in mots if w in rep)
    return vus / len(mots) >= 0.8


def extrait_simple(reponse: str, n: int) -> tuple[str, list[str]]:
    """Sans modèle pour choisir : les premières lignes « à puce », « numérotées » ou « en gras » de la réponse, coupées à la bonne longueur."""
    out = []
    for raw in str(reponse).splitlines():
        t = re.sub(r"[*_`#>]+", "", raw).strip()
        if not re.match(r"^(\d+[.)]|[-•–])\s+\S", t) and not re.match(r"^\*\*", raw.strip()):
            continue
        t = re.sub(r"^[-•–]\s+", "", t).strip()
        t = re.split(r"\s[:—–]\s|\s\(", t)[0].strip() if len(t) > schema.LIGNE_MAX else t
        if len(t) > schema.LIGNE_MAX:
            t = t[:schema.LIGNE_MAX - 1].rsplit(" ", 1)[0] + "…"
        if len(t) >= 4 and t not in out:
            out.append(t)
        if len(out) == n:
            break
    if len(out) < n:                                             # réponse sans liste : ses premières phrases
        for ph in re.split(r"(?<=[.!?])\s+", re.sub(r"[*_`#>]+", "", str(reponse)).strip()):
            ph = ph.strip()
            if len(ph) > schema.LIGNE_MAX:
                ph = ph[:schema.LIGNE_MAX - 1].rsplit(" ", 1)[0] + "…"
            if len(ph) >= 8 and ph not in out:
                out.append(ph)
            if len(out) == n:
                break
    return "Extrait de la réponse", out[:n]


def _dit_simple(n: int) -> str:
    ordres = ["la première ligne", "la deuxième", "la troisième", "la quatrième", "la cinquième"]
    return "[a]Voici un extrait de la vraie réponse, obtenue aujourd'hui : " + ", ".join(f"[a{i + 1}]{ordres[i]}" for i in range(n)) + ". Lis-la en entier chez toi : elle change un peu à chaque essai."


def _blocs(story: dict, kind: str, n: int):
    for sc in story.get("scenes") or []:
        for b in sc.get("blocks") or []:
            if b.get("kind") == kind and int(b.get("n") or 1) == n:
                yield sc, b


def tester(story: dict, cfg: dict, brain, faits_ok: dict | None, log=print, today: str | None = None) -> dict:
    """Renvoie le storyboard avec, pour chaque fiche : statut, vérification, date, et l'écran « réponse » mis à jour."""
    st = copy.deepcopy(story)
    today = today or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    jour = f"{today[8:10]}/{today[5:7]}/{today[0:4]}"
    actif = bool((cfg.get("editorial") or {}).get("test_prompts", True)) and brain is not None and brain.available()
    cites = [f for f in (st.get("faits") or [])]
    faits_ok = faits_ok or {}
    for i, f in enumerate(st.get("prompts") or []):
        n = i + 1
        typ = f.get("type") or "prompt"
        if typ in ("commande", "reglage"):
            # l'agent ne peut pas cliquer dans l'application : la preuve est la page officielle, relue par la veille
            confirmes = [fid for fid in cites if fid in faits_ok]
            if cites and len(confirmes) == len(cites):
                src = "; ".join(str(faits_ok[fid].get("affichage") or faits_ok[fid].get("url") or fid) for fid in confirmes)
                f.update({"statut": "testé", "verification": "page officielle relue", "teste_sur": src[:160],
                          "teste_le": max(str(faits_ok[fid].get("verifie_le") or today) for fid in confirmes)})
                log(f"essai : « {f['titre']} » ({typ}) — confirmé sur la page officielle ({src[:80]})")
            else:
                f.update({"statut": "à vérifier", "verification": "aucune page officielle confirmée"})
                log(f"essai : « {f['titre']} » ({typ}) — aucune page officielle confirmée aujourd'hui : reste « à vérifier »")
            continue
        if not actif:
            f["statut"] = "à vérifier"
            f["verification"] = "non testé (aucune clé GEMINI_API_KEY)"
            for _sc, b in _blocs(st, "reponse", n):
                b["source"] = MENTION_EXEMPLE
            log(f"essai : « {f['titre']} » — non testé (aucune clé GEMINI_API_KEY) : l'écran « réponse » montre un exemple, la vidéo ne sera pas publiée")
            continue
        envoi = schema.remplir(f["texte"], f.get("exemple") or {})
        try:
            reponse, modele = brain.repondre(envoi)
        except Exception as e:  # noqa: BLE001 — pas de réponse : la fiche est rejetée pour aujourd'hui, la vidéo ne part pas
            f.update({"statut": "rejeté", "verification": f"essai impossible ({type(e).__name__}: {str(e)[:120]})", "teste_le": today})
            for _sc, b in _blocs(st, "reponse", n):
                b["source"] = MENTION_EXEMPLE
            log(f"essai : « {f['titre']} » — l'essai a échoué ({str(e)[:140]})")
            continue
        outil = nom_public(modele)
        f.update({"statut": "testé", "verification": "essai réel", "teste_sur": f"{outil} ({modele.split('/')[-1]}, par l'API)", "teste_le": today,
                  "resultat_exemple": reponse.strip()[:6000]})
        log(f"essai : « {f['titre']} » — réponse réelle de {outil} ({len(reponse)} caractères)")
        for sc, b in _blocs(st, "reponse", n):
            nb = len(b.get("lignes") or []) or 3
            titre, lignes, dit = None, None, None
            try:
                def valider(o, nb=nb, reponse=reponse):
                    ls = [re.sub(r"\s+", " ", str(x)).strip() for x in (o.get("lignes") or [])]
                    pb = []
                    if len(ls) != nb:
                        pb.append(f"il faut exactement {nb} lignes, il y en a {len(ls)}")
                    for x in ls:
                        if len(schema.visible(x)) > schema.LIGNE_MAX:
                            pb.append(f"ligne trop longue ({len(schema.visible(x))} caractères, maximum {schema.LIGNE_MAX}) : « {x} »")
                        elif not fidele(x, reponse):
                            pb.append(f"ligne infidèle à la réponse (un mot important ou un chiffre n'y figure pas) : « {x} »")
                    t = re.sub(r"\s+", " ", str(o.get("titre") or "")).strip()
                    if not 2 <= len(t) <= 40:
                        pb.append("« titre » : 2 à 40 caractères")
                    d = re.sub(r"\s+", " ", str(o.get("dit") or "")).strip()
                    _c, toks, cues = align.parse_say(d)
                    permis = {"a"} | {f"a{k + 1}" for k in range(nb)}
                    if not 12 <= len(toks) <= 55 or any(c not in permis for c in cues):
                        pb.append(f"« dit » : 12 à 55 mots, repères permis {sorted(permis)}")
                    if pb:
                        raise ValueError("\n".join(f"- {x}" for x in pb))
                    return {"titre": t, "lignes": ls, "dit": d}
                o = brain.ask_json(EXTRAIRE, f"INSTRUCTION ENVOYÉE :\n{envoi}\n\nRÉPONSE DE L'IA :\n{reponse[:5000]}\n\nNombre de lignes demandé : {nb}.",
                                   niveau="controle", validate=valider, retries=1, temperature=0.2, max_tokens=1200, purpose="extrait de réponse")
                titre, lignes, dit = o["titre"], o["lignes"], o["dit"]
            except Exception as e:  # noqa: BLE001 — sans modèle pour choisir : extrait mécanique, phrase neutre
                log(f"essai : extrait par le modèle impossible ({str(e)[:100]}) — extrait mécanique")
                titre, lignes = extrait_simple(reponse, nb)
                dit = _dit_simple(len(lignes))
            if len(lignes) >= schema.LIGNES_REPONSE[0]:
                b["titre"], b["lignes"] = titre, lignes
                b["source"] = f"Réponse de {outil} · testée le {jour}"
                if len(sc.get("blocks") or []) == 1:               # l'écran ne montre que la réponse : la voix suit les vraies lignes
                    sc["say"] = dit
            else:
                b["source"] = MENTION_EXEMPLE
                f["statut"] = "rejeté"
                f["verification"] = "réponse trop courte pour être montrée"
    st["essai"] = {"le": today, "statuts": [f.get("statut") for f in st.get("prompts") or []]}
    return st


def verifie(story: dict) -> list[str]:
    """Les fiches qui empêchent la publication (statut autre que « testé » ou « validé »)."""
    return [f"« {f.get('titre')} » ({f.get('statut') or 'à vérifier'} — {f.get('verification') or 'non vérifié'})"
            for f in story.get("prompts") or [] if f.get("statut") not in ("testé", "validé")]
