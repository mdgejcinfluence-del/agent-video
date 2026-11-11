"""Veille quotidienne, à partir de sources publiques, gratuites et sans clé.

Deux rôles :
  1. FAITS VÉRIFIÉS (data/faits.yaml) : chaque jour, l'agent rouvre la page officielle de chaque chiffre, prix ou
     licence qu'une vidéo peut citer, et vérifie que la phrase attendue y figure encore. Un fait non reconfirmé
     n'est plus publiable, et tout changement est signalé (voir verifier_faits).
  2. ACTUALITÉ DES OUTILS : dépôts récents liés aux sujets, pour noter la fraîcheur d'un sujet.

Seules des pages publiques sont lues, sans compte ni contournement. Détail de l'actualité des outils :

  * GitHub (API de recherche)  -> dépôts populaires/récents liés à la niche, avec leurs chiffres réels
  * Hacker News (API Algolia)  -> ce dont on parle cette semaine (désactivé par défaut : actualité souvent polémique)
  * Flux RSS                   -> annonces officielles

Filtre de ligne éditoriale : un candidat n'est retenu que si son nom, sa description ou ses thèmes
contiennent l'un des mots exigés (research.require_any, ex. « claude », « remotion ») et aucun des
mots refusés (research.exclude_any, ex. « security », « watermark »).

Chaque candidat porte ses « faits » (chiffres + source). Le scénariste n'a le droit d'utiliser
que ces faits : c'est ce qui empêche le modèle d'inventer des chiffres.
"""
from __future__ import annotations

import datetime as dt
import html
import os
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

UA = {"User-Agent": "studio-agent/1.0 (veille)", "Accept": "application/json"}


def _get(url: str, params: dict | None = None, headers: dict | None = None, timeout: int = 20):
    r = requests.get(url, params=params, headers={**UA, **(headers or {})}, timeout=timeout)
    r.raise_for_status()
    return r


def _latin(text: str) -> bool:
    """Faux si le texte COMMENCE dans un autre alphabet (le scénariste ne saurait pas le reformuler).
    Une description en anglais suivie de sa traduction reste acceptée."""
    letters = [c for c in text or "" if c.isalpha()][:24]
    return not letters or sum(ord(c) < 0x250 for c in letters) / len(letters) >= 0.9


def relevant(name: str, description: str | None, topics: list[str] | None, require: list[str] | None,
             exclude: list[str] | None = None) -> bool:
    """Le candidat est-il dans la ligne du compte ? (mots exigés, mots refusés, description lisible)"""
    blob = " ".join([name or "", description or "", " ".join(topics or [])]).lower().replace("-", " ")
    if any(re.search(rf"\b{re.escape(x.lower())}(?:s|es|ed|ing|er|ers)?\b", blob) for x in exclude or []):
        return False
    return _latin(description or "") and (not require or any(r.lower().replace("-", " ") in blob for r in require))


def fr_int(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def github(keywords: list[str], min_stars: int = 300, days: int = 60, per_kw: int = 10, log=print,
           require: list[str] | None = None, exclude: list[str] | None = None) -> list[dict]:
    out, seen, dropped = [], set(), 0
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    headers = {"Accept": "application/vnd.github+json", **({"Authorization": f"Bearer {tok}"} if tok else {})}
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).strftime("%Y-%m-%d")
    for kw in keywords[:5]:
        try:
            r = _get("https://api.github.com/search/repositories",
                     {"q": f"{kw} in:name,description,topics stars:>={min_stars} pushed:>={since}", "sort": "stars", "order": "desc",
                      "per_page": per_kw}, headers)
            for it in r.json().get("items", []):
                if it["full_name"] in seen or it.get("archived") or it.get("fork"):
                    continue
                seen.add(it["full_name"])
                if not relevant(it["full_name"], it.get("description"), it.get("topics"), require, exclude):
                    dropped += 1
                    continue
                facts = [f"Nom du dépôt GitHub : {it['full_name']}",
                         f"Étoiles GitHub : {fr_int(it['stargazers_count'])}",
                         f"Description officielle (anglais) : {(it.get('description') or '').strip()[:260]}"]
                if it.get("language"):
                    facts.append(f"Langage principal : {it['language']}")
                if (it.get("license") or {}).get("spdx_id") not in (None, "NOASSERTION"):
                    facts.append(f"Licence : {it['license']['spdx_id']}")
                if it.get("topics"):
                    facts.append("Thèmes : " + ", ".join(it["topics"][:8]))
                facts.append(f"Dernière mise à jour : {it['pushed_at'][:10]}")
                out.append({"id": "gh:" + it["full_name"].lower(), "source": "github", "kw": kw, "title": it["name"],
                            "url": it["html_url"], "stars": it["stargazers_count"], "date": it["pushed_at"][:10], "facts": facts})
            time.sleep(1.2 if tok else 6.5)          # recherche GitHub : 10 requêtes/min sans jeton
        except Exception as e:  # noqa: BLE001 — une source en panne ne bloque pas la veille
            log(f"veille : GitHub « {kw} » indisponible ({type(e).__name__})")
    if dropped:
        log(f"veille : {dropped} dépôt(s) écarté(s) car hors de la ligne du compte")
    return out


def readme(full_name: str, limit: int = 2600) -> str:
    try:
        r = _get(f"https://raw.githubusercontent.com/{full_name}/HEAD/README.md", headers={"Accept": "text/plain"})
        txt = re.sub(r"<[^>]+>|!\[[^\]]*\]\([^)]*\)", " ", r.text)
        txt = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", txt)
        return re.sub(r"\s+", " ", txt).strip()[:limit]
    except Exception:  # noqa: BLE001
        return ""


def hackernews(keywords: list[str], days: int = 10, min_points: int = 60, log=print, require: list[str] | None = None,
               exclude: list[str] | None = None) -> list[dict]:
    out, seen = [], set()
    ts = int(time.time()) - days * 86400
    for kw in keywords[:4]:
        try:
            r = _get("https://hn.algolia.com/api/v1/search", {"query": kw, "tags": "story", "hitsPerPage": 6,
                                                               "numericFilters": f"created_at_i>{ts},points>{min_points}"})
            for h in r.json().get("hits", []):
                if h["objectID"] in seen or not h.get("title") or not relevant(h["title"], "", [], require, exclude):
                    continue
                seen.add(h["objectID"])
                out.append({"id": "hn:" + h["objectID"], "source": "hackernews", "kw": kw, "title": h["title"],
                            "url": h.get("url") or f"https://news.ycombinator.com/item?id={h['objectID']}",
                            "stars": h.get("points", 0), "date": (h.get("created_at") or "")[:10],
                            "facts": [f"Titre de l'actualité (anglais) : {h['title']}",
                                      f"Points sur Hacker News : {h.get('points', 0)}",
                                      f"Commentaires : {h.get('num_comments', 0)}", f"Date : {(h.get('created_at') or '')[:10]}"]})
        except Exception as e:  # noqa: BLE001
            log(f"veille : Hacker News « {kw} » indisponible ({type(e).__name__})")
    return out


def rss(urls: list[str], limit: int = 5, log=print) -> list[dict]:
    out = []
    for u in urls or []:
        try:
            root = ET.fromstring(_get(u, headers={"Accept": "application/rss+xml, application/xml, text/xml"}).content)
            items = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
            for it in items[:limit]:
                def f(*tags):
                    for t in tags:
                        e = it.find(t)
                        if e is not None and (e.text or e.get("href")):
                            return (e.text or e.get("href") or "").strip()
                    return ""
                title = f("title", "{http://www.w3.org/2005/Atom}title")
                link = f("link", "{http://www.w3.org/2005/Atom}link")
                date = f("pubDate", "{http://www.w3.org/2005/Atom}updated", "{http://www.w3.org/2005/Atom}published")
                desc = re.sub(r"<[^>]+>", " ", f("description", "{http://www.w3.org/2005/Atom}summary"))[:300]
                if title:
                    summary = re.sub(r"\s+", " ", desc).strip()
                    out.append({"id": "rss:" + (link or title)[:120], "source": "rss", "kw": "", "title": title, "url": link,
                                "stars": 0, "date": date[:16],
                                "facts": [f"Titre de l'annonce : {title}", f"Résumé : {summary}", f"Source : {u}"]})
        except Exception as e:  # noqa: BLE001
            log(f"veille : flux {u} indisponible ({type(e).__name__})")
    return out


def gather(cfg: dict, log=print) -> list[dict]:
    rc = cfg.get("research", {})
    kws = (cfg.get("niche") or {}).get("keywords", [])
    out: list[dict] = []
    require = [str(r) for r in (rc.get("require_any") or []) if str(r).strip()]
    exclude = [str(r) for r in (rc.get("exclude_any") or []) if str(r).strip()]
    if rc.get("github", True):
        out += github(kws, int(rc.get("min_stars", 300)), log=log, require=require, exclude=exclude)
    if rc.get("hackernews", False):
        out += hackernews(kws, log=log, require=require, exclude=exclude)
    out += rss(rc.get("rss") or [], log=log)
    log(f"veille : {len(out)} candidats ({sum(c['source'] == 'github' for c in out)} GitHub, "
        f"{sum(c['source'] == 'hackernews' for c in out)} Hacker News, {sum(c['source'] == 'rss' for c in out)} RSS)")
    return out


# --------------------------------------------------------------------------- faits vérifiés (pages officielles)
def _texte_page(url: str) -> tuple[int, str]:
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (compatible; veille-editoriale/1.0)", "Accept": "text/html"}, timeout=25)
    t = re.sub(r"<script\b.*?</script>|<style\b.*?</style>", " ", r.text, flags=re.S | re.I)
    return r.status_code, re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", t)))


def charger_faits(root: str | Path, state=None) -> dict:
    """Les faits du dépôt (data/faits.yaml) et, si la mémoire est fournie, ceux que l'agent a trouvés lui-même (state/faits_auto.json)."""
    import yaml
    p = Path(root) / "data" / "faits.yaml"
    d = (yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}) or {}
    faits = {str(f["id"]): f for f in d.get("faits") or [] if f.get("id")}
    if state is not None:
        for fid, f in ((state.load("faits_auto", {}) or {}).get("faits") or {}).items():
            faits.setdefault(str(fid), f)
    return {"fraicheur_jours": int(d.get("fraicheur_jours", 3)), "faits": faits}


def verifier_faits(root: str | Path, state, log=print, force: bool = False, fetch=_texte_page) -> dict:
    """Rouvre chaque page officielle (une fois par jour) et note si la phrase attendue y figure encore.

    Mémoire : state/veille.json = {"date", "faits": {id: {"ok", "le", "http", "manque"}}, "changements": [...]}.
    """
    base = charger_faits(root, state)
    mem = state.load("veille", {"date": "", "faits": {}, "changements": []})
    today = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    if mem.get("date") == today and not force:
        return mem
    pages: dict[str, tuple[int, str] | None] = {}
    for fid, f in base["faits"].items():
        if f.get("verification") == "manuelle":            # page fermée aux robots : lue à la main, valable un temps limité (valable_jours)
            continue
        url = str(f.get("url") or "")
        if url not in pages:
            try:
                pages[url] = fetch(url)
            except Exception as e:  # noqa: BLE001 — page injoignable : le fait garde son dernier état, sans nouvelle date
                pages[url] = None
                log(f"veille : {url} injoignable ({type(e).__name__}) — les faits de cette page ne sont pas reconfirmés aujourd'hui")
        page = pages[url]
        if page is None:
            continue
        code, text = page
        low = text.lower()
        manque = [s for s in (f.get("doit_contenir") or []) if str(s).lower() not in low]
        ok = code == 200 and not manque
        prev = mem["faits"].get(fid)
        was = True if prev is None else bool(prev.get("ok"))          # l'état initial est celui du fichier (vérifié à la main)
        mem["faits"][fid] = {"ok": ok, "le": today, "http": code, "manque": manque}
        if was and not ok:
            msg = f"CHANGEMENT sur {url} : « {'» , « '.join(map(str, manque)) or 'page en erreur ' + str(code)} » introuvable — fait « {fid} » suspendu"
            mem.setdefault("changements", []).append({"le": today, "fait": fid, "detail": msg})
            log("veille : " + msg)
        elif not was and ok:
            mem.setdefault("changements", []).append({"le": today, "fait": fid, "detail": "de nouveau confirmé"})
            log(f"veille : fait « {fid} » de nouveau confirmé sur la page officielle")
    mem["changements"] = mem.get("changements", [])[-60:]
    if any(p is not None for p in pages.values()):
        mem["date"] = today
    state.save("veille", mem)
    auto = [fid for fid, f in base["faits"].items() if f.get("verification") != "manuelle"]
    n_ok = sum(1 for fid in auto if (mem["faits"].get(fid) or {}).get("ok") and mem["faits"][fid].get("le") == today)
    log(f"veille : {n_ok}/{len(auto)} faits reconfirmés aujourd'hui sur {len([p for p in pages.values() if p])} page(s) officielle(s)"
        + (f" ; {len(base['faits']) - len(auto)} fait(s) lus à la main (pages fermées aux robots)" if len(auto) < len(base["faits"]) else ""))
    return mem


def faits_confirmes(root: str | Path, state, today: str | None = None) -> dict[str, dict]:
    """{id: fait} pour les faits utilisables aujourd'hui (dernier contrôle réussi et assez récent)."""
    base = charger_faits(root, state)
    mem = state.load("veille", {"date": "", "faits": {}, "changements": []})
    now_ = dt.date.fromisoformat(today) if today else dt.datetime.now(dt.timezone.utc).date()
    out = {}
    for fid, f in base["faits"].items():
        manuel = f.get("verification") == "manuelle"
        chk = None if manuel else mem["faits"].get(fid)
        if chk is not None and not chk.get("ok"):
            continue
        last = str((chk or {}).get("le") or f.get("verifie_le") or "")
        try:
            age = (now_ - dt.date.fromisoformat(last)).days
        except ValueError:
            continue
        if age <= (int(f.get("valable_jours", 90)) if manuel else base["fraicheur_jours"]):
            out[fid] = {**f, "verifie_le": last}
    return out


# --------------------------------------------------------------------------- nouveaux faits, trouvés par l'agent
PROPOSER = """Tu aides un compte de vidéos courtes (astuces pour filmer, monter et publier des vidéos avec un téléphone et l'IA) à ne dire que des choses vraies.
Propose des FAITS vérifiables sur des outils utiles à ce public (montage, sous-titres, images, voix, publication).
Chaque fait doit pouvoir être relu sur une page OFFICIELLE de l'outil (son site, sa documentation, sa page de tarifs ou de licence), accessible sans compte.
Réponds par un objet JSON : {"faits": [{"id": "outil-sujet" en minuscules, "outil": nom de l'outil, "affirmation": le fait en français, 160 caractères au plus,
"url": adresse https de la page officielle, "citation": une phrase EXACTE de cette page (4 à 16 mots, dans la langue de la page) qui prouve le fait,
"gratuit": true seulement si la citation dit que c'est gratuit, "nombres": les chiffres cités, "limite": ce que le fait ne dit pas ou la condition à connaître}]}
L'affirmation traduit fidèlement la citation, rien de plus. Aucun chiffre qui n'est pas dans la citation. Si tu n'es pas sûr de la phrase exacte, ne propose pas le fait."""


def _domaine_officiel(url: str, outil: str) -> bool:
    m = re.match(r"https://([^/]+)/?", url or "")
    if not m:
        return False
    host = m.group(1).lower()
    cle = re.sub(r"[^a-z0-9]", "", outil.lower())
    return bool(cle) and len(cle) >= 3 and cle in re.sub(r"[^a-z0-9]", "", host)


def proposer_faits(brain, root: str | Path, state, cfg: dict, log=print, fetch=_texte_page) -> int:
    """Demande au modèle de nouveaux faits ; ne garde que ceux dont la citation est retrouvée mot pour mot sur la page officielle."""
    rcfg = cfg.get("research") or {}
    if not rcfg.get("nouveaux_faits", True) or brain is None or not brain.available():
        return 0
    mem = state.load("faits_auto", {}) or {}
    sem = dt.datetime.now(dt.timezone.utc).strftime("%G-W%V")
    if mem.get("semaine") == sem and mem.get("demandes", 0) >= 2:
        return 0                                                    # deux demandes par semaine suffisent
    connus = charger_faits(root, state)["faits"]
    try:
        obj = brain.ask_json(PROPOSER, "Faits déjà connus (n'y reviens pas) : " + ", ".join(connus) + f"\nPropose au plus {int(rcfg.get('nouveaux_faits_par_semaine', 6))} nouveaux faits.",
                             niveau="controle", temperature=0.3, max_tokens=3000, retries=0, purpose="faits")
    except Exception as e:  # noqa: BLE001
        log(f"veille : proposition de nouveaux faits impossible ({type(e).__name__}: {str(e)[:100]})")
        return 0
    mem = {"semaine": sem, "demandes": (mem.get("demandes", 0) if mem.get("semaine") == sem else 0) + 1, "faits": dict(mem.get("faits") or {})}
    today = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    gardes = 0
    for f in (obj.get("faits") or [])[:8]:
        if not isinstance(f, dict):
            continue
        fid = re.sub(r"[^a-z0-9-]", "", str(f.get("id") or "").lower())[:40]
        outil, aff, url, cit = (str(f.get(k) or "").strip() for k in ("outil", "affirmation", "url", "citation"))
        if not fid or fid in connus or not (10 <= len(aff) <= 170) or not (4 <= len(cit.split()) <= 18):
            continue
        if not _domaine_officiel(url, outil):
            log(f"veille : fait proposé « {fid} » écarté — {url[:60]} n'est pas le site de {outil}")
            continue
        if any(n not in cit for n in re.findall(r"\d+(?:[.,]\d+)?", aff)):
            log(f"veille : fait proposé « {fid} » écarté — un chiffre de l'affirmation n'est pas dans la citation")
            continue
        try:
            code, text = fetch(url)
        except Exception:  # noqa: BLE001
            continue
        if code != 200 or re.sub(r"\s+", " ", cit).lower() not in text.lower():
            log(f"veille : fait proposé « {fid} » écarté — citation introuvable sur la page (HTTP {code})")
            continue
        gratuit = bool(f.get("gratuit")) and bool(re.search(r"free|gratuit", cit, re.I))
        mem["faits"][fid] = {"id": fid, "affirmation": aff, "organisme": f"{outil} (site officiel)", "titre": "", "url": url, "doit_contenir": [cit],
                             "verification": "automatique", "publie_le": "", "verifie_le": today, "territoire": "international",
                             "limite": str(f.get("limite") or "")[:200], "affichage": re.sub(r"^https://(www\.)?", "", url)[:60], "outils": [outil],
                             "gratuit": gratuit, "nombres": [str(n) for n in (f.get("nombres") or []) if str(n) in cit], "origine": "modele"}
        gardes += 1
        log(f"veille : nouveau fait vérifié « {fid} » — {aff[:90]} ({url[:60]})")
    state.save("faits_auto", mem)
    return gardes
