"""Relevé des statistiques de chaque vidéo publiée (24 h, 72 h, 7 jours par défaut)."""
from __future__ import annotations

import datetime as dt

from .config import secret
from .state import now

MAX_FETCH = 14      # par exécution, pour rester loin des quotas


def _age_h(iso: str) -> float:
    return (now() - dt.datetime.fromisoformat(iso)).total_seconds() / 3600


def collect(state, cfg: dict, log=print) -> int:
    checks = sorted((cfg.get("stats") or {}).get("check_after_hours") or [24, 72, 168])
    buf = None
    tiktok_list = None
    fetched = 0
    for post in state.posts:
        for net, pub in (post.get("published") or {}).items():
            if fetched >= MAX_FETCH:
                break
            if pub.get("status") not in ("sent", "sending", "inbox") or not pub.get("id") or not pub.get("at"):
                continue
            age = _age_h(pub["at"])
            snaps = post.setdefault("stats", {}).setdefault(net, [])
            due = [c for c in checks if age >= c and not any(s["h"] >= c for s in snaps)]
            if not due or age > checks[-1] + 72:
                continue
            try:
                if pub.get("via") == "buffer":
                    if buf is None:
                        from .publish.buffer import Buffer
                        key = secret("BUFFER_API_KEY")
                        if not key:
                            continue
                        buf = Buffer(key, state)
                    m = buf.metrics(pub["id"])
                    if m.get("status"):
                        pub["status"] = m["status"]
                elif net == "facebook":
                    from .publish import meta
                    m = meta.facebook_stats(pub["id"], secret("FB_PAGE_TOKEN"))
                elif net == "instagram":
                    from .publish import meta
                    m = meta.instagram_stats(pub["id"], secret("IG_TOKEN") or secret("FB_PAGE_TOKEN"))
                elif net == "tiktok":
                    from .publish import tiktok
                    if tiktok_list is None:
                        if (cfg.get("stats") or {}).get("source_tiktok") == "public":
                            tiktok_list = tiktok.public_videos((cfg.get("brand") or {}).get("handle", ""))
                        else:
                            tok = tiktok.access_token(secret("TIKTOK_CLIENT_KEY"), secret("TIKTOK_CLIENT_SECRET"), secret("TIKTOK_REFRESH_TOKEN"))
                            tiktok_list = tiktok.videos(tok["access_token"])
                    t_pub = dt.datetime.fromisoformat(pub["at"]).timestamp()
                    cand = [v for v in tiktok_list if v.get("create_time") and abs(v["create_time"] - t_pub) < 6 * 3600]
                    if not cand:
                        continue
                    v = min(cand, key=lambda v: abs(v["create_time"] - t_pub))
                    m = {"views": v.get("view_count"), "likes": v.get("like_count"), "comments": v.get("comment_count"),
                         "shares": v.get("share_count"), "saves": None}
                else:
                    continue
            except Exception as e:  # noqa: BLE001 — une lecture en échec ne bloque pas les autres
                log(f"statistiques : {net} / {post['id']} illisible ({str(e)[:140]})")
                continue
            fetched += 1
            if m.get("views") is None:
                continue
            snaps.append({"h": round(age, 1), "t": now().isoformat(timespec="seconds"),
                          **{k: m.get(k) for k in ("views", "likes", "comments", "shares", "saves", "reach", "watch") if m.get(k) is not None}})
            log(f"statistiques : {net} / « {post.get('title', '')[:40]} » à {age:.0f} h — {m.get('views')} vues, "
                f"{m.get('comments')} commentaires, {m.get('shares')} partages")
    if fetched:
        state.save_posts()
    return fetched
