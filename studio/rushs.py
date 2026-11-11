"""Rushs : de vraies séquences filmées, prises dans des banques libres de droits.

L'agent les cherche lui-même (API officielles de Pexels et de Pixabay, clés gratuites), les télécharge,
vérifie qu'elles respectent le format et la qualité, vérifie qu'elles montrent bien ce que dit la voix,
puis les découpe au cadre voulu. Sans clé, il se sert de la bibliothèque de départ (data/rushs.yaml).

Trois contrôles avant qu'une séquence entre dans une vidéo :
  1. technique  : durée, définition, netteté, mouvement, luminosité, pas de bandes noires ;
  2. cohérence  : un modèle regarde trois images de la séquence et dit ce qu'il voit (Gemini) ;
                  sans modèle, on compare les mots de la recherche aux étiquettes de la banque ;
  3. droits     : source et page d'origine notées pour chaque séquence (crédit dans la légende et la fiche),
                  personne reconnaissable jamais associée à un passage négatif, pas d'image générée par IA.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import subprocess
import unicodedata
from pathlib import Path

import numpy as np
import requests
import yaml

from .config import secret

UA = {"User-Agent": "agent-video/3 (rushs libres de droits ; https://github.com)"}
CADRES = {"paysage": (888, 500), "portrait": (396, 704), "carre": (586, 586)}       # taille d'affichage dans le moteur
MAX_MO = 60                # on ne télécharge pas un fichier plus lourd
STOP = {"a", "an", "the", "of", "on", "in", "with", "and", "to", "for", "at", "by", "from", "her", "his", "is", "up", "video", "free", "stock", "footage"}
NEGATIF = re.compile(r"arnaqu|escroc|vol[eé]|pi[eè]ge|erreur|[eé]chec|rat[eé]|nul|pauvre|menteu|danger|interdit|faux|fraude|honte|perd", re.I)


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s).lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def mots(s: str) -> list[str]:
    out = []
    for w in re.findall(r"[a-z]{3,}", _norm(s)):
        if w in STOP:
            continue
        for suf in ("ing", "es", "s"):                       # racine grossière : typing -> typ, products -> product
            if len(w) > len(suf) + 3 and w.endswith(suf):
                w = w[: -len(suf)]
                break
        out.append(w)
    return out


# --------------------------------------------------------------------------- sources
def bibliotheque(root: str | Path) -> list[dict]:
    p = Path(root) / "data" / "rushs.yaml"
    if not p.exists():
        return []
    d = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    out = []
    for r in d.get("rushs") or []:
        out.append({**r, "tags": [str(t) for t in r.get("tags") or []], "auteur": r.get("auteur") or "", "origine": "bibliotheque",
                    "licence": d.get("licence") or "Licence Pexels"})
    return out


def _pexels(q: str, orientation: str, http, n: int = 12) -> list[dict]:
    key = secret("PEXELS_API_KEY")
    if not key:
        return []
    params = {"query": q, "per_page": n, "size": "medium", "locale": "en-US"}
    if orientation in ("portrait", "landscape"):
        params["orientation"] = orientation
    r = http.get("https://api.pexels.com/v1/videos/search", params=params, headers={**UA, "Authorization": key}, timeout=30)
    r.raise_for_status()
    out = []
    for v in r.json().get("videos") or []:
        files = [f for f in v.get("video_files") or [] if (f.get("file_type") or "").endswith("mp4") and f.get("width") and f.get("height")]
        if not files:
            continue
        # la plus proche de 1080 px sur le petit côté, sans descendre sous 720
        ok = [f for f in files if min(f["width"], f["height"]) >= 720] or files
        f = min(ok, key=lambda f: (abs(min(f["width"], f["height"]) - 1080), -(f.get("fps") or 0)))
        slug = re.sub(r"-?\d+/?$", "", (v.get("url") or "").rstrip("/").split("/")[-1])
        out.append({"id": f"px-{v['id']}", "source": "pexels", "page": v.get("url") or "", "url": f["link"], "w": f["width"], "h": f["height"],
                    "dur": float(v.get("duration") or 0), "tags": [t for t in slug.split("-") if t], "montre": slug.replace("-", " "),
                    "auteur": (v.get("user") or {}).get("name") or "", "origine": "recherche", "licence": "Licence Pexels"})
    return out


def _pixabay(q: str, orientation: str, http, n: int = 20) -> list[dict]:
    key = secret("PIXABAY_API_KEY")
    if not key:
        return []
    r = http.get("https://pixabay.com/api/videos/", params={"key": key, "q": q[:100], "video_type": "film", "safesearch": "true", "per_page": n, "lang": "en"},
                 headers=UA, timeout=30)
    r.raise_for_status()
    out = []
    for v in r.json().get("hits") or []:
        vs = v.get("videos") or {}
        f = next((vs[k] for k in ("medium", "large", "small") if (vs.get(k) or {}).get("url") and min(vs[k].get("width") or 0, vs[k].get("height") or 0) >= 720), None) \
            or next((vs[k] for k in ("medium", "small", "tiny") if (vs.get(k) or {}).get("url")), None)
        if not f:
            continue
        tags = [t.strip() for t in (v.get("tags") or "").split(",") if t.strip()]
        out.append({"id": f"pb-{v['id']}", "source": "pixabay", "page": v.get("pageURL") or "", "url": f["url"], "w": f.get("width") or 0, "h": f.get("height") or 0,
                    "dur": float(v.get("duration") or 0), "tags": tags, "montre": ", ".join(tags), "auteur": v.get("user") or "",
                    "origine": "recherche", "licence": "Licence de contenu Pixabay"})
    return out


def sources_actives() -> list[str]:
    return [n for n, k in (("pexels", "PEXELS_API_KEY"), ("pixabay", "PIXABAY_API_KEY")) if secret(k)]


def chercher(q: str, orientation: str, state=None, log=print, http=None) -> list[dict]:
    """Résultats des banques pour cette recherche. Mis en mémoire 24 h (exigé par Pixabay, et inutile de redemander)."""
    http = http or requests
    key = f"{_norm(q)}|{orientation}"
    reg = state.load("rushs", {}) if state is not None else {}
    cache = reg.setdefault("recherches", {})
    now = dt.datetime.now(dt.timezone.utc)
    hit = cache.get(key)
    if hit and (now - dt.datetime.fromisoformat(hit["t"])).total_seconds() < 86400:
        return hit["resultats"]
    out = []
    for name, fn in (("pexels", _pexels), ("pixabay", _pixabay)):
        try:
            got = fn(q, orientation, http)
            out += got
            if got or name in sources_actives():
                log(f"rushs : {name} — « {q} » : {len(got)} séquence(s)")
        except Exception as e:  # noqa: BLE001 — une banque en panne ne doit pas arrêter l'agent
            log(f"rushs : {name} indisponible ({type(e).__name__}: {str(e)[:90]})")
    if out and state is not None:
        for k in [k for k, v in cache.items() if (now - dt.datetime.fromisoformat(v["t"])).days >= 3]:
            del cache[k]
        cache[key] = {"t": now.isoformat(timespec="seconds"), "resultats": out}
        state.save("rushs", reg)
    return out


# --------------------------------------------------------------------------- choix
def orientation_de(cadre: str) -> str:
    return {"paysage": "landscape", "portrait": "portrait"}.get(cadre, "")


def note_mots(besoin: dict, c: dict) -> float:
    """Part des mots de la recherche retrouvés dans les étiquettes de la séquence (0 à 1)."""
    want = list(dict.fromkeys(mots(besoin.get("q", ""))))
    have = set(mots(" ".join(c.get("tags") or []) + " " + c.get("montre", "")))
    if not want:
        return 0.0
    return sum(1 for w in want if w in have) / len(want)


def convient(besoin: dict, c: dict) -> tuple[bool, str]:
    """Contrôles sans téléchargement : durée, définition, orientation, droits."""
    w, h = CADRES.get(besoin.get("cadre") or "portrait", CADRES["portrait"])
    if c.get("dur") and c["dur"] < 4:
        return False, "trop courte"
    if c.get("w") and c.get("h"):
        # après recadrage au format du cadre, il doit rester assez de pixels (rendu 1080 px de large)
        k = min(c["w"] / w, c["h"] / h)
        if k < 1.2:
            return False, "définition insuffisante une fois recadrée"
        ar_src, ar_dst = c["w"] / c["h"], w / h
        if max(ar_src, ar_dst) / min(ar_src, ar_dst) > 3.4:
            return False, "format trop éloigné du cadre"
    tags = " ".join(c.get("tags") or []).lower()
    if "ai generated" in tags or "ai-generated" in tags or "aigenerated" in tags:
        return False, "image générée par IA (on veut du réel)"
    if besoin.get("sensible") and c.get("personnes"):
        return False, "personne reconnaissable dans un passage négatif"
    return True, ""


def classer(besoin: dict, cands: list[dict], deja: set[str] | None = None) -> list[tuple[float, dict]]:
    w, h = CADRES.get(besoin.get("cadre") or "portrait", CADRES["portrait"])
    rows = []
    for c in cands:
        ok, _why = convient(besoin, c)
        if not ok:
            continue
        s = note_mots(besoin, c)
        if c.get("w") and c.get("h"):
            ar_src, ar_dst = c["w"] / c["h"], w / h
            s += 0.15 if max(ar_src, ar_dst) / min(ar_src, ar_dst) < 1.25 else 0.0         # même orientation que le cadre
            s += 0.05 if min(c["w"], c["h"]) >= 1080 else 0.0
        if c.get("origine") == "bibliotheque":
            s += 0.05                                                                     # déjà regardée à l'œil
        if deja and c["id"] in deja:
            s -= 0.35                                                                     # déjà utilisée récemment
        rows.append((round(s, 3), c))
    rows.sort(key=lambda r: -r[0])
    return rows


# --------------------------------------------------------------------------- fichiers
def telecharger(c: dict, cache: str | Path, http=None) -> Path:
    http = http or requests
    cache = Path(cache); cache.mkdir(parents=True, exist_ok=True)
    out = cache / f"{c['id']}.mp4"
    if out.exists() and out.stat().st_size > 50_000:
        return out
    with http.get(c["url"], headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"},
                  stream=True, timeout=120) as r:
        r.raise_for_status()
        size = 0
        tmp = out.with_suffix(".part")
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 16):
                size += len(chunk)
                if size > MAX_MO * 1e6:
                    raise RuntimeError(f"fichier de plus de {MAX_MO} Mo")
                f.write(chunk)
        tmp.replace(out)
    return out


def sonder(path: str | Path) -> dict:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,r_frame_rate,codec_name:stream_side_data=rotation",
                        "-show_entries", "format=duration", "-of", "json", str(path)], capture_output=True, text=True)
    d = json.loads(r.stdout or "{}")
    s = (d.get("streams") or [{}])[0]
    w, h = int(s.get("width") or 0), int(s.get("height") or 0)
    rot = 0
    for sd in s.get("side_data_list") or []:
        rot = int(abs(float(sd.get("rotation") or 0))) or rot
    if rot in (90, 270):
        w, h = h, w
    num, _, den = (s.get("r_frame_rate") or "0/1").partition("/")
    return {"w": w, "h": h, "fps": float(num) / float(den or 1) if float(den or 1) else 0.0, "dur": float((d.get("format") or {}).get("duration") or 0),
            "codec": s.get("codec_name") or ""}


def _gris(path: Path, t: float, w: int = 320) -> np.ndarray | None:
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", str(path), "-frames:v", "1", "-vf", f"scale={w}:-2,format=gray", "-f", "rawvideo", "-"],
                       capture_output=True)
    if not r.stdout:
        return None
    h = len(r.stdout) // w
    return np.frombuffer(r.stdout[: w * h], dtype=np.uint8).reshape(h, w).astype(np.float32)


def analyser(path: str | Path) -> dict:
    """Mesures sur le fichier : format, netteté, mouvement, luminosité, bandes noires. Renvoie {ok, problemes, mesures}."""
    path = Path(path)
    p = sonder(path)
    pb = []
    if not p["w"] or p["dur"] < 3.5:
        return {"ok": False, "problemes": ["fichier illisible ou trop court"], **p}
    if min(p["w"], p["h"]) < 700:
        pb.append(f"définition {p['w']}×{p['h']} trop faible")
    ts = [p["dur"] * k for k in (0.2, 0.5, 0.8)]
    fr = [g for g in (_gris(path, t) for t in ts) if g is not None]
    fr2 = [g for g in (_gris(path, t + 0.4) for t in ts) if g is not None]
    if len(fr) < 2:
        return {"ok": False, "problemes": ["images illisibles"], **p}
    lap = []
    for g in fr:
        l = -4 * g[1:-1, 1:-1] + g[:-2, 1:-1] + g[2:, 1:-1] + g[1:-1, :-2] + g[1:-1, 2:]
        lap.append(float(l.var()))
    net = float(np.median(lap))
    mouv = float(np.mean([np.abs(a - b).mean() for a, b in zip(fr, fr2)])) if fr2 else 0.0
    lum = float(np.mean([g.mean() for g in fr]))
    bandes = float(np.mean([min(g[:6].mean(), g[-6:].mean()) for g in fr]))
    cote = float(np.mean([min(g[:, :6].mean(), g[:, -6:].mean()) for g in fr]))
    if net < 12:
        pb.append(f"image floue (netteté {net:.0f})")
    if mouv < 0.25:
        pb.append("image fixe : ce n'est pas une séquence filmée")
    if mouv > 45:
        pb.append("image trop agitée ou coupes rapides")
    if lum < 30 or lum > 232:
        pb.append(f"image {'trop sombre' if lum < 30 else 'brûlée'} (luminosité {lum:.0f})")
    if (bandes < 4 and lum > 45) or (cote < 4 and lum > 45):
        pb.append("bandes noires autour de l'image")
    return {"ok": not pb, "problemes": pb, **p, "nettete": round(net, 1), "mouvement": round(mouv, 2), "luminosite": round(lum, 1)}


def temoins(path: str | Path, n: int = 3, w: int = 384) -> list[bytes]:
    """Quelques images de la séquence, en JPEG, pour le contrôle de cohérence."""
    p = sonder(path)
    out = []
    for k in range(n):
        t = p["dur"] * (k + 1) / (n + 1)
        r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", str(path), "-frames:v", "1", "-vf", f"scale={w}:-2", "-q:v", "5", "-f", "image2pipe", "-vcodec", "mjpeg", "-"],
                           capture_output=True)
        if r.stdout:
            out.append(r.stdout)
    return out


def preparer(path: str | Path, cadre: str, duree: float, dest: str | Path, fps: int = 30) -> dict:
    """Découpe la séquence au cadre voulu et l'écrit image par image (lue ensuite par le moteur de rendu)."""
    path, dest = Path(path), Path(dest)
    w, h = CADRES.get(cadre, CADRES["portrait"])
    p = sonder(path)
    duree = max(1.0, min(float(duree), p["dur"] - 0.2))
    depart = max(0.0, min(0.6, (p["dur"] - duree) / 2))
    if dest.exists():
        for f in dest.glob("*.jpg"):
            f.unlink()
    dest.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{depart:.2f}", "-i", str(path), "-t", f"{duree:.2f}", "-an",
                    "-vf", f"fps={fps},scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos,crop={w}:{h}", "-q:v", "3", str(dest / "%04d.jpg")], check=True)
    n = len(list(dest.glob("*.jpg")))
    if not n:
        raise RuntimeError("aucune image extraite")
    return {"dir": dest.resolve().as_uri() + "/", "n": n, "fps": fps, "w": w, "h": h, "ext": "jpg", "duree": round(n / fps, 2)}


# --------------------------------------------------------------------------- cohérence
VISION = """Tu contrôles des séquences vidéo de banque d'images avant leur utilisation dans une vidéo courte.
Pour chaque séquence tu reçois 3 images (début, milieu, fin), dans l'ordre annoncé.
Réponds UNIQUEMENT par un objet JSON : {"sequences": [{"n": 1, "montre": "ce qu'on voit, en une phrase, en français",
"note": 0 à 10 (10 = montre exactement ce qui est attendu, 0 = sans rapport), "texte_ou_logo": true si un texte incrusté, un filigrane,
une marque ou un logo est lisible, "visage_reconnaissable": true si le visage d'une personne est reconnaissable,
"image_de_synthese": true si l'image semble générée par ordinateur ou par IA}]}
Sois sévère : une séquence qui illustre vaguement le thème mais ne montre pas ce qui est attendu a une note inférieure à 6."""


def controle_vision(brain, lots: list[dict], log=print) -> dict[str, dict]:
    """lots : [{id, attendu, phrase, images: [bytes]}] -> {id: verdict}. Un seul appel pour toute la vidéo."""
    if not lots:
        return {}
    lignes, images = [], []
    for i, l in enumerate(lots, 1):
        lignes.append(f"Séquence {i} (images {len(images) + 1} à {len(images) + len(l['images'])}) — attendu : « {l['attendu']} » ; "
                      f"phrase prononcée pendant qu'elle est à l'écran : « {l['phrase'][:220]} »")
        images += l["images"]
    obj = brain.ask_json(VISION, "\n".join(lignes), images=images, niveau="controle", temperature=0.1, max_tokens=2048, retries=1, purpose="rushs")
    out = {}
    for row in obj.get("sequences") or []:
        try:
            l = lots[int(row.get("n")) - 1]
        except (TypeError, ValueError, IndexError):
            continue
        out[l["id"]] = {"montre": str(row.get("montre") or "")[:160], "note": float(row.get("note") or 0), "texte_ou_logo": bool(row.get("texte_ou_logo")),
                        "visage": bool(row.get("visage_reconnaissable")), "synthese": bool(row.get("image_de_synthese"))}
    return out


def choisir(besoins: list[dict], cfg: dict, state, brain, root: str | Path, log=print, http=None) -> dict[str, dict]:
    """Pour chaque besoin {ref, q, voir, cadre, phrase, sensible} : la meilleure séquence qui passe les trois contrôles.

    Renvoie {ref: {..candidat, fichier, verdict, controle}} ; un besoin sans séquence acceptable est absent du résultat.
    """
    root = Path(root)
    rcfg = cfg.get("rushs") or {}
    cache = root / ".cache" / "rushs"
    lib = bibliotheque(root)
    reg = state.load("rushs", {}) if state is not None else {}
    recents = {k for k, v in (reg.get("utilises") or {}).items() if v and v[-1] >= (dt.date.today() - dt.timedelta(days=int(rcfg.get("repos_jours", 10)))).isoformat()}
    seuil_mots = float(rcfg.get("seuil_mots", 0.5))
    seuil_vision = float(rcfg.get("seuil_vision", 7))
    vision = bool(brain is not None and brain.vision() and rcfg.get("vision", True))
    n_vision = int(rcfg.get("candidats_regardes", 3)) if vision else 1      # sans modèle pour regarder, la première séquence qui passe les contrôles suffit
    pris: set[str] = set()
    pre: dict[str, list[tuple[float, dict, Path, dict]]] = {}
    for b in besoins:
        cands = {}
        if sources_actives():
            for c in chercher(b["q"], orientation_de(b.get("cadre", "")), state, log, http):
                cands[c["id"]] = c
        for c in lib:
            cands.setdefault(c["id"], c)
        rows = [(s, c) for s, c in classer(b, list(cands.values()), recents | pris) if note_mots(b, c) >= seuil_mots or (vision and c.get("origine") == "recherche")]
        ok_rows = []
        for s, c in rows[: n_vision + 3]:
            if len(ok_rows) >= n_vision:
                break
            try:
                f = telecharger(c, cache, http)
                a = analyser(f)
            except Exception as e:  # noqa: BLE001
                log(f"rushs : {c['id']} écartée — téléchargement impossible ({type(e).__name__}: {str(e)[:80]})")
                continue
            if not a["ok"]:
                log(f"rushs : {c['id']} écartée — {' ; '.join(a['problemes'])}")
                continue
            ok_rows.append((s, c, f, a))
        pre[b["ref"]] = ok_rows
        if ok_rows:
            pris.add(ok_rows[0][1]["id"])
    # cohérence : un modèle regarde les séquences (un seul appel), sinon on s'en tient aux étiquettes
    verdicts: dict[str, dict] = {}
    if vision:
        lots = []
        for b in besoins:
            for s, c, f, a in pre.get(b["ref"], []):
                lots.append({"id": f"{b['ref']}|{c['id']}", "attendu": b.get("voir") or b["q"], "phrase": b.get("phrase", ""), "images": temoins(f)})
        try:
            verdicts = controle_vision(brain, lots, log)
        except Exception as e:  # noqa: BLE001
            log(f"rushs : contrôle par l'image indisponible ({type(e).__name__}: {str(e)[:110]}) — contrôle par étiquettes")
            vision = False
    out: dict[str, dict] = {}
    donnes: set[str] = set()
    for b in besoins:
        best = None
        for s, c, f, a in pre.get(b["ref"], []):
            if c["id"] in donnes:
                continue
            v = verdicts.get(f"{b['ref']}|{c['id']}")
            if vision and v is not None:
                if v["note"] < seuil_vision or v["texte_ou_logo"] or v["synthese"] or (b.get("sensible") and v["visage"]):
                    why = "note %.0f/10" % v["note"] + (", texte ou logo" if v["texte_ou_logo"] else "") + (", image de synthèse" if v["synthese"] else "") \
                          + (", visage dans un passage négatif" if b.get("sensible") and v["visage"] else "")
                    log(f"rushs : {c['id']} refusée pour « {b['q']} » — le modèle voit « {v['montre']} » ({why})")
                    continue
                rank, controle = v["note"] / 10 + s * 0.2, f"image regardée par le modèle : « {v['montre']} » (note {v['note']:.0f}/10)"
            else:
                if note_mots(b, c) < seuil_mots:
                    continue
                rank = s
                controle = ("séquence de la bibliothèque de départ, regardée à l'œil : « " + c.get("montre", "") + " »") if c.get("origine") == "bibliotheque" \
                    else f"étiquettes de la banque : {', '.join(c.get('tags') or [])[:90]} (aucun modèle n'a regardé l'image)"
            if best is None or rank > best[0]:
                best = (rank, c, f, a, controle)
        if best is None:
            log(f"rushs : rien d'acceptable pour « {b['q']} » ({b.get('voir', '')[:60]})")
            continue
        _, c, f, a, controle = best
        donnes.add(c["id"])
        out[b["ref"]] = {**c, "fichier": str(f), "mesures": {k: a.get(k) for k in ("w", "h", "fps", "dur", "nettete", "mouvement", "luminosite")}, "controle": controle}
        log(f"rushs : « {b['q']} » -> {c['id']} ({c['source']}, {a['w']}×{a['h']}, {a['dur']:.0f} s) — {controle[:130]}")
    return out


def noter_usage(state, ids: list[str]) -> None:
    if state is None or not ids:
        return
    reg = state.load("rushs", {})
    u = reg.setdefault("utilises", {})
    today = dt.date.today().isoformat()
    for i in ids:
        u.setdefault(i, []).append(today)
        u[i] = u[i][-5:]
    state.save("rushs", reg)


def credits(choix: dict[str, dict]) -> list[dict]:
    """Une ligne par séquence utilisée : source, auteur, page d'origine, licence."""
    seen, out = set(), []
    for c in choix.values():
        if c["id"] in seen:
            continue
        seen.add(c["id"])
        out.append({"id": c["id"], "source": {"pexels": "Pexels", "pixabay": "Pixabay"}.get(c["source"], c["source"]), "auteur": c.get("auteur") or "",
                    "page": c.get("page") or "", "licence": c.get("licence") or ""})
    return out


def ligne_credit(choix: dict[str, dict]) -> str:
    """Pour la légende : « Images : Pexels (Prénom Nom), Pixabay (pseudo) »."""
    cr = credits(choix)
    if not cr:
        return ""
    par: dict[str, list[str]] = {}
    for c in cr:
        par.setdefault(c["source"], [])
        if c["auteur"] and c["auteur"] not in par[c["source"]]:
            par[c["source"]].append(c["auteur"])
    return "Images : " + ", ".join(s + (f" ({', '.join(a[:3])})" if a else "") for s, a in par.items())


def besoins_de(story: dict) -> list[dict]:
    """Les séquences dont ce storyboard a besoin, avec la phrase prononcée pendant qu'elles sont à l'écran."""
    out = []
    for i, sc in enumerate(story.get("scenes") or []):
        for j, b in enumerate(sc.get("blocks") or []):
            if b.get("kind") in ("rush", "avant_apres"):
                phrase = re.sub(r"\[[a-z_]+\d*\]", "", sc.get("say") or "")
                texte = " ".join([sc.get("title") or "", phrase])
                out.append({"ref": b.get("ref") or f"r{i + 1}{'ab'[j] if j < 2 else j}", "q": b.get("q", ""), "voir": b.get("voir", ""), "cadre": b.get("cadre") or "portrait",
                            "phrase": phrase.strip(), "sensible": bool(NEGATIF.search(texte)), "essentiel": b.get("kind") == "avant_apres", "scene": i, "bloc": j})
    return out
