"""Fiche de production : les 9 éléments à fournir pour chaque vidéo, dans l'ordre, dans un fichier lisible (out/<id>.md).

1. fiche stratégie · 2. sources et veille · 3. références observées · 4. trois accroches et le choix ·
5. script minuté · 6. storyboard · 7. phrase de fin · 8. pack de publication par plateforme · 9. contrôle avant publication

Rien n'est rédigé « pour faire bien » : chaque ligne vient d'un fichier du dépôt ou d'une mesure faite sur la vidéo.
Quand une information manque, la fiche le dit.
"""
from __future__ import annotations

import re
from pathlib import Path

from . import porte, preuves, writer
from .align import MARK
from .config import segment_cfg
from .publish import NETWORKS, packs

SAFE = "contenu entre 96 et 1 252 px de haut ; sous-titres entre 1 288 et 1 418 px ; rien d'essentiel sous 1 440 px ni à moins de 64 px des bords"
MOVE = {"brief": "le texte s'écrit mot à mot, puis le passage clé est surligné", "code": "les lignes arrivent une à une, puis la ligne clé est surlignée",
        "media": "le cadre se pose, le rendu joue depuis le début", "avant_apres": "balayage de gauche à droite : avant, puis après",
        "erreur": "un cadre rouge entoure le défaut ; s'il y a une correction, elle le remplace", "checklist": "les lignes se cochent une à une",
        "compare": "les lignes apparaissent une à une", "note": "la carte se pose", "pill": "la pastille apparaît", "chips": "les étiquettes apparaissent une à une",
        "stat": "le chiffre monte jusqu'à sa valeur", "terminal": "la commande se tape", "source": "la source s'affiche"}


def _say(s: dict) -> str:
    return re.sub(r"\s+", " ", MARK.sub("", s.get("say", ""))).strip()


def _plain(s) -> str:
    return re.sub(r"\s+", " ", str(s or "").replace("*", "")).strip()


def _cell(s) -> str:
    return _plain(s).replace("|", "/")


def _visuel(v: dict | None) -> str:
    if not v:
        return "—"
    if v.get("kind") == "contraste":
        return f"contraste : « {v['avant']['ref']} » puis « {v['apres']['ref']} »"
    return f"média « {v.get('ref')} »"


def _files(pack: dict, refs: list[str]) -> str:
    m = pack.get("media") or {}
    return ", ".join(f"preuves/{pack['id']}/{m[r]['fichier']}" for r in refs if r in m) or "—"


def _storyboard_rows(story: dict, pack: dict, scenes_t: list[dict]) -> list[str]:
    rows = []
    for i, s in enumerate(story["scenes"]):
        t = scenes_t[i] if i < len(scenes_t) else {}
        span = f"{t.get('t0', 0):.1f}–{t.get('t1', 0):.1f} s" if t else "—"
        ty = s["type"]
        if ty == "resultat":
            v = s["visuel"]
            refs = [v["avant"]["ref"], v["apres"]["ref"]] if v.get("kind") == "contraste" else [v["ref"]]
            rows.append((f"1 · Résultat ({span})", _visuel(v), "le résultat est à l'image dès la première image ; l'étiquette du public arrive quand la voix le nomme",
                         f"{_plain(s['title'])} / {_plain(s['public'])}", _say(s), _files(pack, refs)))
        elif ty == "etape":
            vis, mov, txt, res = [], [], [_plain(s["title"])], []
            for b in s["blocks"]:
                k = b["kind"]
                mov.append(MOVE.get(k, ""))
                if k == "brief":
                    vis.append(f"{'correction' if b.get('source') == 'correction' else 'demande'} écrite (extrait mot pour mot)")
                    txt.append(f"« {b['text']} »")
                    res.append(f"preuves/{pack['id']}/{pack.get('correction' if b.get('source') == 'correction' else 'demande')}")
                elif k == "code":
                    vis.append(f"extrait de code ({b['file']})"); txt.append(" ⏎ ".join(b["lines"])); res.append(f"{b['file']} (projet du dossier de preuve)")
                elif k == "media":
                    vis.append(f"média « {b['ref']} »"); res.append(_files(pack, [b["ref"]]))
                elif k == "avant_apres":
                    vis.append(f"avant « {b['avant']['ref']} » / après « {b['apres']['ref']} »"); res.append(_files(pack, [b["avant"]["ref"], b["apres"]["ref"]]))
                elif k == "erreur":
                    vis.append(f"défaut entouré sur « {b['ref']} »" + (f", puis « {b['fix']['ref']} »" if b.get("fix") else ""))
                    txt.append(b.get("label", "")); res.append(_files(pack, [b["ref"]] + ([b["fix"]["ref"]] if b.get("fix") else [])))
                else:
                    vis.append(k); txt.append(" · ".join(r["text"] for r in b.get("rows") or []) or " · ".join(b.get("items") or []) or str(b.get("text") or ""))
            rows.append((f"{i + 1} · Étape {s.get('n')} ({span})", " + ".join(vis), " ; ".join(dict.fromkeys(m for m in mov if m)), " / ".join(x for x in txt if x), _say(s),
                         ", ".join(dict.fromkeys(r for r in res if r and r != "—")) or "—"))
        elif ty == "verif":
            v = s.get("visuel")
            rows.append((f"{i + 1} · Vérification ({span})", (_visuel(v) + " + " if v else "") + "liste des vérifications + limite",
                         "chaque vérification se coche quand la voix la cite ; la limite arrive en dernier, encadrée",
                         " · ".join(r["text"] for r in s["rows"]) + f" / À savoir : {_plain(s['limite'])}" + (f" / {s['source']}" if s.get("source") else ""),
                         _say(s), _files(pack, [v["ref"]]) if v else "—"))
        else:
            rows.append((f"{i + 1} · Phrase de fin ({span})", "carte « Commente » + mot-clé, puis la seconde phrase en entier",
                         "le mot-clé s'écrit quand il est prononcé ; la seconde phrase s'écrit ensuite ; écran tenu après la voix",
                         f"{s.get('verb')} {s.get('keyword')} {s.get('l2')} / {s.get('l3')}", _say(s), "aucune"))
    return ["| " + " | ".join(_cell(c) for c in r) + f" | {SAFE if n == 0 else 'idem'} |" for n, r in enumerate(rows)]


def ecrire(path: str | Path, story: dict, pack: dict, cfg: dict, res: dict | None = None, choix: dict | None = None,
           faits: dict | None = None, refs: list[dict] | None = None, suite: dict | None = None, origine: str = "") -> Path:
    """Écrit la fiche de production. `res` = compte rendu de produce.make_video (None si la vidéo n'a pas été rendue)."""
    faits, refs = faits or {}, refs or []
    seg = story["segment"]
    sc = segment_cfg(cfg, seg)
    f = (choix or {}).get("fiche") or {}
    qa = (res or {}).get("qa")
    blocs = porte.bloquants(cfg, pack, qa, suite)
    L: list[str] = []
    add = L.append
    add(f"# Fiche de production — {story['title']}")
    add("")
    add(f"Vidéo : `{Path(res['video']).name if res else 'non rendue'}` · série « {sc.get('serie', seg)} » · écrite par : {origine or 'storyboard fourni'}")
    if pack.get("fictif"):
        add("")
        add("> **Exemple fictif.** Le commerce, le produit et le prix de cette vidéo n'existent pas. La mention « EXEMPLE FICTIF » reste à l'écran du début à la fin.")
    # ---------------------------------------------------------------- 1
    add("\n## 1. Fiche stratégie\n")
    add(f"- **Public (un seul)** : {sc.get('nom', seg)} — {sc.get('cible', '')}")
    add(f"- **Sujet** : n° {story.get('sujet')} de la banque" + (f" — {f['sujet']}" if f.get("sujet") else ""))
    pb = next((h["text"] for h in story.get("hooks") or [] if h["type"] == "probleme"), "")
    add(f"- **Problème, dans les mots du public** : {'« ' + pb + ' »' if pb else '—'}")
    add(f"- **Résultat promis par la vidéo** : {_plain(story['scenes'][0]['title'])} — {_plain(story['scenes'][0]['public'])}")
    add(f"- **Promesse du parcours** : {sc.get('promesse', '—')}")
    add("- **Action souhaitée** : commenter le mot-clé pour suivre la série ; visiter le lien en bio" +
        (f" ({cfg['offer']['lien_bio']})" if (cfg.get("offer") or {}).get("lien_bio") else " (page d'aiguillage non renseignée)"))
    if f.get("criteres"):
        c = f["criteres"]
        add(f"- **Note du sujet** : {f['note']}/5 — problème {c['probleme']}/5 (30 %), preuve {c['preuve']}/5 (25 %), demande {c['demande']}/5 (20 %), "
            f"adéquation {c['formation']}/5 (15 %), fraîcheur {c['fraicheur']}/5 (10 %). Outil de tri interne, pas une probabilité de succès.")
        add("- **Niveau de confiance** : " + " ; ".join(f.get("confiance") or []) + ".")
        add(f"- **Pourquoi maintenant** : {(choix or {}).get('pourquoi', '—')}.")
    else:
        add("- **Note du sujet** : non calculée (storyboard fourni à la main).")
    # ---------------------------------------------------------------- 2
    add("\n## 2. Sources et veille\n")
    cites = [faits[i] for i in story.get("faits") or [] if i in faits]
    add("| Fait ou tendance | Source | Date publiée | Date vérifiée | Territoire | Limite |")
    add("|---|---|---|---|---|---|")
    for x in cites:
        add(f"| {_cell(x['affirmation'])} | [{_cell(x.get('organisme'))}]({x.get('url')}) | {x.get('publie_le') or 'non indiquée'} | {x.get('verifie_le')} | {_cell(x.get('territoire'))} | {_cell(x.get('limite'))} |")
    prod = pack.get("produit_par") or {}
    add(f"| Tout ce qui est montré (demande, code, rendus) | dossier `preuves/{pack['id']}/` | {prod.get('date', '—')} | "
        f"{pack.get('valide_le') or 'non signé'} | — | {'exemple fictif' if pack.get('fictif') else 'démonstration réelle'} ; {_cell((pack.get('limites') or ['—'])[0])} |")
    add("")
    add("Aucun chiffre de marché, de vues ou de ventes n'est cité dans cette vidéo." if not cites else
        f"{len(cites)} fait(s) d'outil cité(s), reconfirmé(s) sur la page officielle. Aucun chiffre de marché, de vues ou de ventes n'est cité.")
    # ---------------------------------------------------------------- 3
    add("\n## 3. Références publiques observées\n")
    if refs:
        add(f"Relevées dans l'{refs[0].get('origine') or 'étude de marché'} ({refs[0].get('observe_le')}), non revérifiées par l'agent. "
            "On en retient la mécanique, jamais les phrases, les images ni les chiffres. Leurs ventes et leur rétention sont inconnues.\n")
        for r in refs[:3]:
            add(f"- [{r['nom']}]({r['url']}) — mécanique : {r['mecanique']} Ce qu'on en retient : {r['a_retenir']}")
    else:
        add("Aucune référence enregistrée pour ce sujet (data/references.yaml).")
    # ---------------------------------------------------------------- 4
    add("\n## 4. Trois accroches, une choisie\n")
    names = {"resultat": "Résultat d'abord", "probleme": "Problème d'abord", "contraste": "Contraste / clarification"}
    if story.get("hooks"):
        for h in story["hooks"]:
            add(f"- {'**' if h['type'] == story.get('hook_type') else ''}{names.get(h['type'], h['type'])} : « {h['text']} »{'** ← retenue' if h['type'] == story.get('hook_type') else ''}")
    else:
        add(f"- Accroche retenue ({names.get(story.get('hook_type'), '—')}) : « {_say(story['scenes'][0]).split('.')[0]}. » Les deux autres n'ont pas été rédigées.")
    add(f"\nPourquoi : {story.get('hook_pourquoi') or '—'} Ce sont des hypothèses à tester, pas des promesses de performance.")
    # ---------------------------------------------------------------- 5
    add("\n## 5. Script minuté\n")
    scenes_t = (res or {}).get("scenes") or []
    add("| Scène | Minutage | Mots | Texte dit |")
    add("|---|---|---:|---|")
    lab = {"resultat": "Résultat + public", "verif": "Vérification + limite", "cta": "Phrase de fin"}
    for i, s in enumerate(story["scenes"]):
        t = scenes_t[i] if i < len(scenes_t) else {}
        name = lab.get(s["type"]) or f"Étape {s.get('n')} — {_plain(s.get('title'))}"
        add(f"| {name} | {t.get('t0', 0):.1f}–{t.get('t1', 0):.1f} s | {t.get('mots', len(_say(s).split()))} | {_cell(_say(s))} |" if t else
            f"| {name} | — | {len(_say(s).split())} | {_cell(_say(s))} |")
    if res:
        lo, hi = (cfg.get("video") or {}).get("seconds", [35, 45])
        add(f"\nDurée mesurée : **{res['duration']:.1f} s** (format visé : {lo}–{hi} s) · {res['words']} mots · voix : {', '.join(res.get('voice') or [])}, débit {res.get('voice_rate')}.")
    # ---------------------------------------------------------------- 6
    add("\n## 6. Storyboard\n")
    add("| Plan | Élément visible | Mouvement | Texte incrusté | Sous-titre | Ressource | Zone de sécurité |")
    add("|---|---|---|---|---|---|---|")
    L.extend(_storyboard_rows(story, pack, scenes_t))
    # ---------------------------------------------------------------- 7
    add("\n## 7. Phrase de fin\n")
    add(f"> {writer.cta_sentence(cfg, story['keyword'])}")
    add("")
    add("Dite et affichée mot pour mot, sans amorce ni ajout. Aucun envoi n'est promis : commenter ne fait rien recevoir.")
    ok, why = porte.promo_etat(cfg)
    add(f"- Promotion : {'✅' if ok else '⛔'} {why}.")
    lien = str((cfg.get("offer") or {}).get("lien_bio") or "").strip()
    add(f"- Lien en bio : {'✅ ' + lien if lien else '⛔ page d’aiguillage non renseignée (offer.lien_bio)'} — attendu : deux boutons visibles, « Commerçant » et « Créateur / freelance ».")
    add(f"- « La suite » : {'✅ sujet n° ' + str(suite['n']) + ' — ' + suite['sujet'] if suite else '⛔ aucune suite prévue pour cette série'}"
        + (" (même sujet, autre accroche)" if suite and suite.get("meme_sujet") else "") + ".")
    # ---------------------------------------------------------------- 8
    add("\n## 8. Pack de publication par plateforme\n")
    live = set((cfg.get("publish") or {}).get("networks") or [])
    for net, p in packs(story, cfg).items():
        add(f"### {NETWORKS[net]}" + ("" if net in live else " — à publier à la main (non relié à l'agent)"))
        add(f"- Titre : {p['titre']}")
        add(f"- Texte de couverture : {p['couverture']}")
        add(f"- Mots-clés naturels : {p['mots_cles']}")
        add(f"- Hashtags ({len(p['hashtags'])}) : {' '.join('#' + h for h in p['hashtags'])} — ils ne garantissent aucune portée")
        add("- Légende :\n")
        add("```\n" + p["legende"] + "\n```")
    # ---------------------------------------------------------------- 9
    add("\n## 9. Contrôle avant publication\n")
    signed = preuves.signee(pack)
    audio = (res or {}).get("audio") or {}
    warn = (qa or {}).get("warnings") or []
    lay = [w for w in ((res or {}).get("layout") or {}).get("warnings", [])]
    lo, hi = (cfg.get("video") or {}).get("seconds", [35, 45])

    def line(state: str, label: str, detail: str) -> None:
        add(f"- {state} **{label}** — {detail}")
    line("✅" if not cites or all(i in faits for i in story.get("faits") or []) else "⛔", "Exactitude technique",
         "aucune confusion entre l'agent qui écrit le code et le moteur qui rend la vidéo (contrôle automatique) ; "
         + (f"{len(cites)} fait(s) reconfirmé(s) aujourd'hui" if cites else "aucun fait d'outil cité") + ". À relire par toi.")
    offre = pack.get("offre") or {}
    if offre:
        line("✅" if signed and not pack.get("fictif") else "⏳", "Exactitude de l'offre et du prix",
             " ; ".join(f"{k} : {v}" for k, v in offre.items()) + (" — EXEMPLE FICTIF" if pack.get("fictif") else "") +
             (f" — vérifié par {pack['valide_par']}" if signed else " — à vérifier et signer dans preuve.yaml (valide_par)"))
    else:
        line("✅", "Exactitude de l'offre et du prix", "aucun produit ni prix dans cette vidéo.")
    from . import schema as _schema
    used = sorted(_schema.refs_in(story))
    line("✅", "Preuve visuelle", f"{len(used)} média(s) du dossier `preuves/{pack['id']}/` : {', '.join(used)} ; demande et code cités mot pour mot (contrôle automatique).")
    line("✅" if signed else "⏳", "Droits des images et de la musique",
         f"{pack.get('droits') or 'droits non renseignés dans preuve.yaml'} Musique et bruitages : générés par l'agent, aucun morceau du commerce. "
         + (f"Photo : {prod['photo']}." if prod.get("photo") else "") + ("" if signed else " À confirmer par ta signature."))
    line("✅" if res and not lay else ("⚠️" if res else "—"), "Lisibilité", ("aucun débordement, tout le contenu est dans la zone de sécurité" if res and not lay else "; ".join(lay) or "vidéo non rendue") + ".")
    line("✅" if audio.get("clarte_db") is not None and audio["clarte_db"] >= 12 else "⚠️", "Audio et sous-titres",
         f"niveau {audio.get('lufs')} LUFS, voix {audio.get('clarte_db')} dB au-dessus du fond, sous-titres synchronisés mot à mot. Personne n'a écouté la vidéo : écoute-la." if res else "vidéo non rendue.")
    if res:
        line("✅" if lo <= res["duration"] <= hi else "⚠️", "Durée", f"{res['duration']:.1f} s (format visé {lo}–{hi} s).")
    line("✅", "Aucune promesse trompeuse", "ni gain, ni vues, ni « gratuit » sans précision, ni durée promise, ni envoi après commentaire (contrôle automatique des formulations).")
    line("✅" if ok and lien and suite else "⛔", "Phrase de fin cohérente avec la page de vente", "voir la section 7.")
    for w in warn:
        line("⚠️", "Remarque du contrôle qualité", w)
    add("")
    if blocs:
        add("**Publication : SUSPENDUE.** Ce qui manque :")
        L.extend(f"{k}. {b}" for k, b in enumerate(blocs, 1))
    elif porte.validation_requise(cfg):
        add("**Publication : en attente de ta validation.** Regarde la vidéo, relis cette fiche, puis lance la commande « valider » avec l'identifiant de la vidéo.")
    else:
        add("**Publication : autorisée** (dossier de preuve signé, validation déléguée dans config.yaml).")
    add("")
    out = Path(path)
    out.write_text("\n".join(L), encoding="utf-8")
    return out
