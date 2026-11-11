"""Dossiers de preuve (preuves/<id>/) : ce que les vidéos ont le droit de montrer et d'affirmer.

Règle de l'agent : pas de preuve, pas de vidéo. Un storyboard ne peut afficher que
  * un extrait de la demande écrite, retrouvé mot pour mot dans demande.md ou correction.md ;
  * des lignes de code retrouvées telles quelles dans les fichiers « sources » du dossier ;
  * des images et des vidéos qui existent dans le dossier (les vidéos sont lues image par image).
Un dossier « fictif: true » est un exemple : la vidéo le dit du début à la fin.
Un dossier sans signature (« valide_par ») sert aux essais, jamais à une publication.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

import yaml

SEGMENTS = ("commercant", "createur_freelance")
FRAME_W = 540                # largeur des images extraites d'un rendu (affiché au plus à 600 px de large)
FPS = 15                     # cadence de lecture des rendus à l'intérieur de la vidéo
VIDEO = (".mp4", ".mov", ".webm")
IMAGE = (".jpg", ".jpeg", ".png", ".webp")


def _norm(s: str) -> str:
    s = str(s or "").replace("’", "'").replace("“", '"').replace("”", '"').replace("\u00a0", " ").replace("\u202f", " ")
    return re.sub(r"\s+", " ", s).strip()


def dossier(root: str | Path) -> Path:
    return Path(root) / "preuves"


def charger(root: str | Path, pid: str) -> dict:
    d = dossier(root) / str(pid)
    y = d / "preuve.yaml"
    if not y.exists():
        raise FileNotFoundError(f"dossier de preuve introuvable : preuves/{pid}/preuve.yaml")
    pack = yaml.safe_load(y.read_text(encoding="utf-8")) or {}
    pack.setdefault("id", str(pid))
    pack["_dir"] = str(d)

    def read(name):
        p = d / str(name) if name else None
        return p.read_text(encoding="utf-8").strip() if p and p.is_file() else ""
    pack["_demande"] = read(pack.get("demande"))
    pack["_correction"] = read(pack.get("correction"))
    proj = (d / str(pack.get("projet") or ".")).resolve()
    pack["_sources"] = {str(n): (proj / str(n)).read_text(encoding="utf-8") for n in (pack.get("sources") or []) if (proj / str(n)).is_file()}
    return pack


def tous(root: str | Path) -> dict[str, dict]:
    out = {}
    base = dossier(root)
    for y in sorted(base.glob("*/preuve.yaml")) if base.is_dir() else []:
        try:
            out[y.parent.name] = charger(root, y.parent.name)
        except Exception as e:  # noqa: BLE001 — un dossier illisible ne doit pas bloquer les autres
            out[y.parent.name] = {"id": y.parent.name, "_erreur": f"{type(e).__name__}: {e}", "_dir": str(y.parent)}
    return out


def problemes(pack: dict) -> list[str]:
    """Ce qui manque pour que le dossier soit utilisable (liste vide = bon)."""
    if pack.get("_erreur"):
        return [f"fichier preuve.yaml illisible ({pack['_erreur']})"]
    out = []
    d = Path(pack["_dir"])
    if pack.get("segment") not in SEGMENTS:
        out.append(f"segment « {pack.get('segment')} » inconnu (attendu : {' ou '.join(SEGMENTS)})")
    if not [n for n in (pack.get("sujets") or []) if isinstance(n, int)]:
        out.append("« sujets » doit lister au moins un numéro de data/sujets.yaml")
    if not pack.get("_demande"):
        out.append("demande écrite absente (demande.md)")
    if not (pack.get("faits") or []):
        out.append("« faits » est vide : la vidéo n'aurait rien le droit d'affirmer")
    if not (pack.get("media") or {}):
        out.append("aucun média : il n'y a pas de résultat à montrer")
    for ref, m in (pack.get("media") or {}).items():
        f = d / str((m or {}).get("fichier") or "")
        if not f.is_file():
            out.append(f"média « {ref} » : fichier {(m or {}).get('fichier')} introuvable")
        elif f.suffix.lower() not in VIDEO + IMAGE:
            out.append(f"média « {ref} » : format {f.suffix} non pris en charge")
    for n in pack.get("sources") or []:
        if str(n) not in pack.get("_sources", {}):
            out.append(f"fichier source {n} introuvable dans le projet")
    if pack.get("segment") == "commercant":
        offre = pack.get("offre") or {}
        for k in ("produit", "prix", "consigne"):
            if not str(offre.get(k) or "").strip():
                out.append(f"offre.{k} manquant : la vidéo ne doit rien inventer sur le produit")
    return out


def signee(pack: dict) -> bool:
    return bool(str(pack.get("valide_par") or "").strip())


def note(pack: dict | None) -> int:
    """Critère « preuve visuelle réelle » de la fiche sujet, de 0 à 5."""
    if not pack or problemes(pack):
        return 0
    if pack.get("fictif"):
        return 2
    return 5 if signee(pack) else 4


def pour_sujet(packs: dict[str, dict], n: int, segment: str) -> list[dict]:
    """Dossiers utilisables pour ce sujet, le plus solide d'abord (réel signé > réel > exemple fictif)."""
    ok = [p for p in packs.values() if not problemes(p) and p.get("segment") == segment and n in (p.get("sujets") or [])]
    return sorted(ok, key=lambda p: (-note(p), p["id"]))


# --------------------------------------------------------------------------- contrôles « mot pour mot »
def extrait_ok(pack: dict, text: str) -> str | None:
    """Renvoie « demande » ou « correction » si chaque morceau de l'extrait s'y trouve mot pour mot, sinon None."""
    parts = [p for p in (_norm(x) for x in re.split(r"…|\.\.\.|\n", str(text or ""))) if len(p) >= 4]
    if not parts:
        return None
    for name in ("demande", "correction"):
        ref = _norm(pack.get("_" + name, ""))
        if ref and all(p in ref for p in parts):
            return name
    return None


def code_faux(pack: dict, fichier: str, lines: list[str]) -> list[str]:
    """Lignes affichées qui ne se retrouvent pas telles quelles dans le fichier source."""
    src = pack.get("_sources", {}).get(str(fichier))
    if src is None:
        return [f"fichier {fichier} absent des sources du dossier ({', '.join(pack.get('_sources', {})) or 'aucune'})"]
    have = [_norm(x) for x in src.splitlines()]
    return [ln for ln in lines if _norm(ln) and not any(_norm(ln) in h for h in have)]


def texte_faits(pack: dict) -> str:
    """Tout ce que la vidéo a le droit de reprendre (sert aussi au contrôle des nombres)."""
    lines = [f"- {f}" for f in pack.get("faits") or []]
    offre = pack.get("offre") or {}
    if offre:
        lines.append("- Offre : " + " ; ".join(f"{k} = {v}" for k, v in offre.items()))
    lines += [f"- Limite : {x}" for x in pack.get("limites") or []]
    return "\n".join(lines)


def texte_nombres(pack: dict) -> str:
    """Faits + demande + correction + code : tout nombre qui s'y trouve peut apparaître dans la vidéo."""
    return "\n".join([texte_faits(pack), pack.get("_demande", ""), pack.get("_correction", ""),
                      "\n".join(pack.get("_sources", {}).values()),
                      json.dumps(pack.get("media") or {}, ensure_ascii=False)])


# --------------------------------------------------------------------------- médias pour le moteur de rendu
def _probe(path: Path) -> dict:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height:format=duration",
                        "-of", "json", str(path)], capture_output=True, text=True, check=True)
    d = json.loads(r.stdout)
    s = d["streams"][0]
    return {"w": int(s["width"]), "h": int(s["height"]), "dur": float(d.get("format", {}).get("duration") or 0)}


def _images(video: Path, work: Path, key: str) -> dict:
    """Vidéo -> suite d'images JPEG lues une à une par le moteur. Mises en cache dans work/<key>/."""
    d = work / key
    meta = d / "meta.json"
    if meta.exists():
        m = json.loads(meta.read_text(encoding="utf-8"))
        if m.get("files") and all((d / f).exists() for f in m["files"]):
            return m
    d.mkdir(parents=True, exist_ok=True)
    for old in d.glob("*.jpg"):
        old.unlink()
    info = _probe(video)
    h = int(round(FRAME_W * info["h"] / info["w"] / 2) * 2)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-vf", f"fps={FPS},scale={FRAME_W}:{h}:flags=lanczos",
                    "-q:v", "3", str(d / "%04d.jpg")], check=True)
    files = sorted(p.name for p in d.glob("*.jpg"))
    if not files:
        raise RuntimeError(f"aucune image extraite de {video.name}")
    m = {"files": files, "w": FRAME_W, "h": h}
    meta.write_text(json.dumps(m), encoding="utf-8")
    return m


def medias(pack: dict, work: str | Path, refs: set[str] | None = None) -> dict:
    """{repère: description lue par engine/player.js} pour les médias du dossier (tous, ou seulement `refs`)."""
    out = {}
    d = Path(pack["_dir"])
    for ref, m in (pack.get("media") or {}).items():
        if refs is not None and ref not in refs:
            continue
        f = d / str(m.get("fichier"))
        if not f.is_file():
            continue
        if f.suffix.lower() in VIDEO:
            st = f.stat()
            key = f"{pack['id']}_{ref}_{hashlib.sha1(f'{st.st_size}:{FPS}:{FRAME_W}'.encode()).hexdigest()[:8]}"
            im = _images(f, Path(work), key)
            base = (Path(work) / key).resolve()
            out[ref] = {"kind": "video", "srcs": [(base / n).as_uri() for n in im["files"]], "fps": FPS, "w": im["w"], "h": im["h"],
                        "dur": round(len(im["files"]) / FPS, 3)}
        else:
            info = _probe(f)
            out[ref] = {"kind": "image", "srcs": [f.resolve().as_uri()], "w": info["w"], "h": info["h"]}
        for k in ("depart", "zone"):
            if m.get(k) is not None:
                out[ref][k] = m[k]
    return out


def resume(pack: dict) -> str:
    """Une ligne lisible pour les journaux et la commande « preuves »."""
    etat = "exemple fictif" if pack.get("fictif") else ("réelle, signée par " + str(pack.get("valide_par"))) if signee(pack) else "réelle, non signée"
    return f"{pack['id']} [{pack.get('segment')}] — {etat} — sujets {pack.get('sujets')} — médias : {', '.join(pack.get('media') or {})}"
