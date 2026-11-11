"""Publication native sur Facebook (Reels de Page) et Instagram (Reels) — API Graph de Meta.

Gratuit. Il faut une application Meta (type « Business »), un jeton de Page longue durée et,
pour que les vidéos soient visibles par tout le monde, l'application en mode « Live »
(en mode « Développement », ce que publie l'application n'est visible que par ses administrateurs).
Écrit d'après la documentation Meta (v26.0) ; NON TESTÉ tant que tes jetons ne sont pas fournis.
"""
from __future__ import annotations

import time
from pathlib import Path

import requests

V = "v26.0"
GRAPH = f"https://graph.facebook.com/{V}"
RUPLOAD = f"https://rupload.facebook.com"


def _ok(r: requests.Response) -> dict:
    try:
        d = r.json()
    except ValueError:
        r.raise_for_status()
        raise
    if isinstance(d, dict) and d.get("error"):
        e = d["error"]
        raise RuntimeError(f"Meta : {e.get('message', e)} (code {e.get('code')}, sous-code {e.get('error_subcode')})")
    r.raise_for_status()
    return d


def facebook_reel(page_id: str, token: str, video: str | Path, description: str, http=requests) -> dict:
    video = Path(video); size = video.stat().st_size
    start = _ok(http.post(f"{GRAPH}/{page_id}/video_reels", data={"upload_phase": "start", "access_token": token}, timeout=60))
    vid = start["video_id"]
    with open(video, "rb") as f:
        _ok(http.post(start.get("upload_url") or f"{RUPLOAD}/video-upload/{V}/{vid}",
                      headers={"Authorization": f"OAuth {token}", "offset": "0", "file_size": str(size)}, data=f, timeout=600))
    _ok(http.post(f"{GRAPH}/{page_id}/video_reels", data={"upload_phase": "finish", "video_id": vid, "video_state": "PUBLISHED",
                                                         "description": description, "access_token": token}, timeout=120))
    status = "sending"
    for _ in range(20):
        time.sleep(9)
        d = _ok(http.get(f"{GRAPH}/{vid}", params={"fields": "status", "access_token": token}, timeout=60)).get("status", {})
        if (d.get("publishing_phase") or {}).get("status") == "complete" or d.get("video_status") == "ready":
            status = "sent"; break
        if d.get("video_status") == "error":
            raise RuntimeError(f"Meta : traitement du Reel en erreur : {d}")
    return {"id": vid, "status": status}


def instagram_reel(ig_id: str, token: str, video: str | Path, caption: str, thumb_ms: int = 1500, http=requests) -> dict:
    video = Path(video); size = video.stat().st_size
    c = _ok(http.post(f"{GRAPH}/{ig_id}/media", data={"media_type": "REELS", "upload_type": "resumable", "caption": caption,
                                                     "share_to_feed": "true", "thumb_offset": str(int(thumb_ms)), "access_token": token}, timeout=60))
    cid = c["id"]
    with open(video, "rb") as f:
        _ok(http.post(c.get("uri") or f"{RUPLOAD}/ig-api-upload/{V}/{cid}",
                      headers={"Authorization": f"OAuth {token}", "offset": "0", "file_size": str(size)}, data=f, timeout=600))
    for _ in range(24):
        time.sleep(12)
        s = _ok(http.get(f"{GRAPH}/{cid}", params={"fields": "status_code,status", "access_token": token}, timeout=60))
        if s.get("status_code") == "FINISHED":
            break
        if s.get("status_code") in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Instagram : conteneur en erreur : {s.get('status')}")
    else:
        raise RuntimeError("Instagram : traitement trop long (plus de 5 minutes)")
    m = _ok(http.post(f"{GRAPH}/{ig_id}/media_publish", data={"creation_id": cid, "access_token": token}, timeout=120))
    return {"id": m["id"], "status": "sent"}


def facebook_stats(video_id: str, token: str, http=requests) -> dict:
    out = {"views": None, "likes": None, "comments": None, "shares": None, "saves": None}
    d = _ok(http.get(f"{GRAPH}/{video_id}", params={"fields": "views,likes.limit(0).summary(true),comments.limit(0).summary(true)",
                                                    "access_token": token}, timeout=60))
    out["views"] = d.get("views")
    out["likes"] = ((d.get("likes") or {}).get("summary") or {}).get("total_count")
    out["comments"] = ((d.get("comments") or {}).get("summary") or {}).get("total_count")
    try:
        ins = _ok(http.get(f"{GRAPH}/{video_id}/video_insights", params={"metric": "fb_reels_total_plays,post_video_social_actions",
                                                                       "access_token": token}, timeout=60))
        for it in ins.get("data", []):
            val = (it.get("values") or [{}])[0].get("value")
            if it.get("name") == "fb_reels_total_plays" and isinstance(val, (int, float)):
                out["views"] = int(val)
            if it.get("name") == "post_video_social_actions" and isinstance(val, dict):
                out["shares"] = val.get("SHARE", out["shares"])
    except Exception:  # noqa: BLE001 — métriques détaillées indisponibles : on garde les compteurs de base
        pass
    return out


def instagram_stats(media_id: str, token: str, http=requests) -> dict:
    out = {"views": None, "likes": None, "comments": None, "shares": None, "saves": None}
    try:
        ins = _ok(http.get(f"{GRAPH}/{media_id}/insights", params={"metric": "views,reach,likes,comments,shares,saved",
                                                                 "access_token": token}, timeout=60))
        m = {it["name"]: (it.get("values") or [{}])[0].get("value") for it in ins.get("data", [])}
        out.update({"views": m.get("views"), "likes": m.get("likes"), "comments": m.get("comments"), "shares": m.get("shares"),
                    "saves": m.get("saved"), "reach": m.get("reach")})
    except Exception:  # noqa: BLE001
        d = _ok(http.get(f"{GRAPH}/{media_id}", params={"fields": "like_count,comments_count", "access_token": token}, timeout=60))
        out.update({"likes": d.get("like_count"), "comments": d.get("comments_count")})
    return out
