"""Publication native sur TikTok (Content Posting API) et lecture des statistiques (Display API).

À SAVOIR (règle de TikTok, pas de cet agent) : tant que ton application TikTok n'a pas passé
l'AUDIT de TikTok, tout ce qu'elle publie en direct reste PRIVÉ (visible de toi seul), et le
compte doit lui-même être privé. Deux modes ici :
  * inbox  : la vidéo arrive en brouillon dans ton application TikTok ; tu touches « publier ».
             Fonctionne sans audit. (Tu peux alors ajouter un son tendance.)
  * direct : publication publique, uniquement après l'audit.
Pour une publication publique sans audit et sans intervention, passe par Buffer (publish.via: buffer).
Écrit d'après la documentation TikTok ; NON TESTÉ tant que tes identifiants ne sont pas fournis.
"""
from __future__ import annotations

import time
from pathlib import Path

import requests

API = "https://open.tiktokapis.com/v2"


def access_token(client_key: str, client_secret: str, refresh_token: str, http=requests) -> dict:
    r = http.post(f"{API}/oauth/token/", data={"client_key": client_key, "client_secret": client_secret,
                                               "grant_type": "refresh_token", "refresh_token": refresh_token},
                  headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=60)
    d = r.json()
    if "access_token" not in d:
        raise RuntimeError(f"TikTok : jeton refusé : {d.get('error_description') or d}")
    return d


def _post(path: str, token: str, body: dict, http=requests) -> dict:
    r = http.post(f"{API}{path}", headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"},
                  json=body, timeout=60)
    d = r.json()
    err = d.get("error") or {}
    if err.get("code") not in (None, "ok"):
        raise RuntimeError(f"TikTok : {err.get('code')} — {err.get('message')}")
    return d.get("data", {})


def upload(token: str, video: str | Path, title: str, mode: str = "inbox", ai_label: bool = True, http=requests) -> dict:
    video = Path(video); size = video.stat().st_size
    src = {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": size, "total_chunk_count": 1}
    if mode == "direct":
        info = _post("/post/publish/creator_info/query/", token, {}, http)
        levels = info.get("privacy_level_options") or ["SELF_ONLY"]
        level = "PUBLIC_TO_EVERYONE" if "PUBLIC_TO_EVERYONE" in levels else levels[0]
        init = _post("/post/publish/video/init/", token, {"post_info": {"title": title[:2200], "privacy_level": level,
                     "disable_duet": False, "disable_comment": False, "disable_stitch": False, "is_aigc": bool(ai_label)},
                     "source_info": src}, http)
    else:
        init = _post("/post/publish/inbox/video/init/", token, {"source_info": src}, http)
    with open(video, "rb") as f:
        r = http.put(init["upload_url"], data=f, headers={"Content-Type": "video/mp4", "Content-Length": str(size),
                                                          "Content-Range": f"bytes 0-{size - 1}/{size}"}, timeout=900)
    if r.status_code not in (200, 201, 206):
        raise RuntimeError(f"TikTok : envoi du fichier refusé (HTTP {r.status_code})")
    status = "sending"
    for _ in range(18):
        time.sleep(10)
        s = _post("/post/publish/status/fetch/", token, {"publish_id": init["publish_id"]}, http)
        if s.get("status") in ("PUBLISH_COMPLETE", "SEND_TO_USER_INBOX"):
            status = "sent" if s["status"] == "PUBLISH_COMPLETE" else "inbox"; break
        if s.get("status") == "FAILED":
            raise RuntimeError(f"TikTok : publication en échec : {s.get('fail_reason')}")
    return {"id": init["publish_id"], "status": status, "mode": mode}


def videos(token: str, count: int = 20, http=requests) -> list[dict]:
    r = http.post(f"{API}/video/list/?fields=id,title,create_time,duration,view_count,like_count,comment_count,share_count",
                  headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}, json={"max_count": count}, timeout=60)
    d = r.json()
    if (d.get("error") or {}).get("code") not in (None, "ok"):
        raise RuntimeError(f"TikTok : {d['error'].get('code')} — {d['error'].get('message')}")
    return (d.get("data") or {}).get("videos") or []


def public_videos(handle: str, count: int = 30) -> list[dict]:
    """Lecture de la page PUBLIQUE du compte avec yt-dlp (non officiel, peut casser à tout moment)."""
    import json
    import subprocess
    r = subprocess.run(["yt-dlp", "-J", "--flat-playlist", "--no-warnings", "--playlist-end", str(count),
                        f"https://www.tiktok.com/@{handle.lstrip('@')}"], capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        raise RuntimeError("lecture publique TikTok impossible : " + r.stderr.strip()[-200:])
    out = []
    for e in json.loads(r.stdout).get("entries") or []:
        out.append({"id": e.get("id"), "title": e.get("title") or "", "create_time": e.get("timestamp"), "duration": e.get("duration"),
                    "view_count": e.get("view_count"), "like_count": e.get("like_count"), "comment_count": e.get("comment_count"),
                    "share_count": e.get("repost_count")})
    return out
