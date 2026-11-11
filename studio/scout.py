"""Veille : trouve des sujets frais et FACTUELS, à partir de sources gratuites et sans clé.

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
import os
import re
import time
import xml.etree.ElementTree as ET

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
