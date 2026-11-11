"""Hébergement public et gratuit des vidéos : branche `studio-media` servie par GitHub Pages.

Buffer (et Instagram en mode « URL ») ne reçoivent pas de fichier : ils viennent chercher la
vidéo à une adresse publique, directe et stable. GitHub Pages remplit ces trois conditions.
La branche `studio-media` ne contient que des fichiers dérivés ; elle est réécrite à chaque fois
(un seul commit) pour ne pas grossir : seules les N dernières vidéos sont conservées.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

import requests


# identité officielle des commits faits par GitHub Actions : aucun compte de personne n'est cité dans l'historique
BOT = ("github-actions[bot]", "41898282+github-actions[bot]@users.noreply.github.com")


def _git(args: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, check=check)


def repo_slug(root: Path) -> str | None:
    if os.environ.get("GITHUB_REPOSITORY"):
        return os.environ["GITHUB_REPOSITORY"]
    r = _git(["remote", "get-url", "origin"], root, check=False)
    url = r.stdout.strip()
    if "github.com" not in url:
        return None
    return url.split("github.com")[-1].lstrip(":/").removesuffix(".git")


def base_url(cfg: dict, root: Path) -> str | None:
    custom = ((cfg.get("publish") or {}).get("media_base_url") or "").strip()
    if custom:
        return custom.rstrip("/")
    slug = repo_slug(root)
    if not slug or "/" not in slug:
        return None
    owner, repo = slug.split("/", 1)
    return f"https://{owner.lower()}.github.io" if repo.lower() == f"{owner.lower()}.github.io" else f"https://{owner.lower()}.github.io/{repo}"


def publish(files: dict[str, Path], cfg: dict, root: Path, keep: int = 30, log=print) -> str | None:
    """Pousse `files` ({chemin relatif: fichier local}) sur la branche `studio-media`. Renvoie l'adresse de base."""
    base = base_url(cfg, root)
    if not base or _git(["rev-parse", "--is-inside-work-tree"], root, check=False).returncode != 0:
        log("hébergement : pas de dépôt GitHub détecté — étape ignorée")
        return None
    work = root / ".media_work"
    if work.exists():
        _git(["worktree", "remove", "--force", str(work)], root, check=False)
        shutil.rmtree(work, ignore_errors=True)
    has_remote = _git(["fetch", "origin", "studio-media", "--depth", "1"], root, check=False).returncode == 0
    if has_remote:
        _git(["worktree", "add", "--force", "--detach", str(work), "FETCH_HEAD"], root)
    else:
        _git(["worktree", "add", "--force", "--detach", str(work)], root)
        for p in work.iterdir():
            if p.name != ".git":
                shutil.rmtree(p) if p.is_dir() else p.unlink()
    (work / ".nojekyll").write_text("")
    for rel, src in files.items():
        dst = work / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
    vids = sorted((work / "v").glob("*.mp4")) if (work / "v").exists() else []
    for old in vids[:-keep] if keep and len(vids) > keep else []:
        old.unlink(); old.with_suffix(".jpg").unlink(missing_ok=True)
    (work / "index.html").write_text("<!doctype html><meta charset=\"utf-8\"><meta name=\"robots\" content=\"noindex\"><title>.</title>", encoding="utf-8")
    # un seul commit, sans historique
    _git(["checkout", "--orphan", "media_tmp"], work)
    _git(["add", "-A"], work)
    _git(["-c", f"user.name={BOT[0]}", "-c", f"user.email={BOT[1]}", "commit", "-q", "-m", "media"], work)
    sha = _git(["rev-parse", "HEAD"], work).stdout.strip()
    # l'envoi part du dépôt principal et non du dossier de travail : c'est là que GitHub Actions range ses droits d'écriture
    push = _git(["push", "--force", "origin", f"{sha}:refs/heads/studio-media"], root, check=False)
    _git(["worktree", "remove", "--force", str(work)], root, check=False)
    shutil.rmtree(work, ignore_errors=True)
    _git(["branch", "-D", "media_tmp"], root, check=False)
    if push.returncode != 0:
        log("hébergement : envoi refusé — " + push.stderr.strip()[-200:])
        return None
    return base


def wait_public(url: str, size: int, timeout: int = 420, log=print) -> bool:
    """Attend que l'adresse réponde 200 avec la bonne taille (GitHub Pages met 1 à 2 minutes à publier)."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            r = requests.head(url, timeout=20, allow_redirects=False, headers={"Accept-Encoding": "identity"})
            if r.status_code == 200 and int(r.headers.get("content-length", -1)) == size:
                return True
        except requests.RequestException:
            pass
        time.sleep(12)
    log(f"hébergement : {url} toujours inaccessible après {timeout} s (GitHub Pages est-il activé sur la branche « studio-media » ?)")
    return False


def selftest(cfg: dict, root: Path, keep: int = 30, timeout: int = 300) -> tuple[bool, str]:
    """Essai réel de l'hébergement : envoie un petit fichier sur la branche, puis vérifie qu'il ressort
    tel quel à l'adresse publique. C'est exactement le chemin que suit une vidéo avant sa publication."""
    import tempfile
    msgs: list[str] = []
    token = f"essai {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {os.urandom(4).hex()}\n"
    t0 = time.time()
    with tempfile.TemporaryDirectory() as td:
        probe = Path(td) / "essai.txt"
        probe.write_text(token, encoding="utf-8")
        base = publish({"essai.txt": probe}, cfg, root, keep, msgs.append)
    if not base:
        return False, (" ; ".join(msgs) or "envoi impossible")[-300:]
    url = f"{base}/essai.txt"
    while time.time() - t0 < timeout:
        try:
            r = requests.get(url, timeout=20, headers={"Cache-Control": "no-cache"})
            if r.status_code == 200 and r.text == token:
                return True, f"fichier d'essai envoyé, puis relu à {url} au bout de {time.time() - t0:.0f} s"
        except requests.RequestException:
            pass
        time.sleep(8)
    return False, f"fichier envoyé, mais {url} ne le sert pas après {timeout} s (Settings > Pages : branche « studio-media », dossier « / (root) »)"


# --------------------------------------------------------------------------- Cloudinary (alternative)
def cloudinary_upload(video: Path, public_id: str, log=print) -> str | None:
    """Envoie la vidéo sur Cloudinary (offre gratuite, hébergeur cité par la documentation de Buffer).

    Secret attendu : CLOUDINARY_URL = cloudinary://<api_key>:<api_secret>@<cloud_name>
    Écrit d'après la documentation Cloudinary ; NON TESTÉ sans compte.
    """
    import hashlib
    import re
    m = re.match(r"cloudinary://([^:]+):([^@]+)@(.+)", os.environ.get("CLOUDINARY_URL", "").strip())
    if not m:
        log("hébergement : secret CLOUDINARY_URL absent ou mal formé")
        return None
    key, sec, cloud = m.groups()
    ts = str(int(time.time()))
    params = {"overwrite": "true", "public_id": public_id, "timestamp": ts}
    sig = hashlib.sha1(("&".join(f"{k}={v}" for k, v in sorted(params.items())) + sec).encode()).hexdigest()
    with open(video, "rb") as f:
        r = requests.post(f"https://api.cloudinary.com/v1_1/{cloud}/video/upload", data={**params, "api_key": key, "signature": sig},
                          files={"file": (video.name, f, "video/mp4")}, timeout=900)
    if not r.ok:
        log(f"hébergement : Cloudinary a refusé l'envoi (HTTP {r.status_code}) {r.text[:160]}")
        return None
    return r.json().get("secure_url")


def cloudinary_delete(public_id: str) -> None:
    import hashlib
    import re
    m = re.match(r"cloudinary://([^:]+):([^@]+)@(.+)", os.environ.get("CLOUDINARY_URL", "").strip())
    if not m:
        return
    key, sec, cloud = m.groups()
    ts = str(int(time.time()))
    sig = hashlib.sha1(f"public_id={public_id}&timestamp={ts}{sec}".encode()).hexdigest()
    try:
        requests.post(f"https://api.cloudinary.com/v1_1/{cloud}/video/destroy",
                      data={"public_id": public_id, "timestamp": ts, "api_key": key, "signature": sig}, timeout=60)
    except requests.RequestException:
        pass
