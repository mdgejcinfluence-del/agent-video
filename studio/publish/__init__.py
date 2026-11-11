"""Publication sur les réseaux : Buffer en premier (1 clé, TikTok public), API natives en complément."""
from __future__ import annotations

import time
from pathlib import Path

from ..config import secret
from ..state import now


def caption_for(story: dict, cfg: dict, network: str) -> str:
    n = int((cfg.get("publish") or {}).get("hashtags", 5))
    tags = " ".join("#" + h for h in (story.get("hashtags") or [])[:n])
    text = (story.get("caption") or story.get("title") or "").strip()
    return (text + ("\n\n" + tags if tags else "")).strip()[:2100]


def publish_all(video: str | Path, story: dict, thumb_ms: int, public_url: str | None, cfg: dict, state, log=print) -> dict:
    pcfg = cfg.get("publish") or {}
    nets = list(pcfg.get("networks") or [])
    out: dict[str, dict] = {}
    if pcfg.get("dry_run", True):
        for n in nets:
            out[n] = {"status": "dry_run", "at": now().isoformat(timespec="seconds")}
        log("publication : mode essai (dry_run) — rien n'a été envoyé. Légende prévue :\n" + caption_for(story, cfg, "tiktok"))
        return out
    ai = bool(pcfg.get("ai_label", True))
    buf = None
    if pcfg.get("via", "buffer") == "buffer" and secret("BUFFER_API_KEY"):
        from .buffer import Buffer
        buf = Buffer(secret("BUFFER_API_KEY"), state)
    for n in nets:
        text = caption_for(story, cfg, n)
        try:
            done = None
            if buf is not None and buf.channel_for(n):
                if not public_url:
                    raise RuntimeError("pas d'adresse publique pour la vidéo (GitHub Pages non prêt)")
                done = {"via": "buffer", **buf.post_video(n, text, public_url, thumb_ms, ai)}
            elif n == "facebook" and secret("FB_PAGE_ID") and secret("FB_PAGE_TOKEN"):
                from . import meta
                done = {"via": "native", **meta.facebook_reel(secret("FB_PAGE_ID"), secret("FB_PAGE_TOKEN"), video, text)}
            elif n == "instagram" and secret("IG_USER_ID") and (secret("IG_TOKEN") or secret("FB_PAGE_TOKEN")):
                from . import meta
                done = {"via": "native", **meta.instagram_reel(secret("IG_USER_ID"), secret("IG_TOKEN") or secret("FB_PAGE_TOKEN"), video, text, thumb_ms)}
            elif n == "tiktok" and secret("TIKTOK_CLIENT_KEY") and secret("TIKTOK_CLIENT_SECRET") and secret("TIKTOK_REFRESH_TOKEN"):
                from . import tiktok
                tok = tiktok.access_token(secret("TIKTOK_CLIENT_KEY"), secret("TIKTOK_CLIENT_SECRET"), secret("TIKTOK_REFRESH_TOKEN"))
                done = {"via": "native", **tiktok.upload(tok["access_token"], video, text, pcfg.get("tiktok_native_mode", "inbox"), ai)}
            if done is None:
                out[n] = {"status": "skipped", "error": "aucun accès configuré pour ce réseau"}
                log(f"publication : {n} ignoré (aucun accès configuré)")
                continue
            done["at"] = now().isoformat(timespec="seconds")
            out[n] = done
            log(f"publication : {n} envoyé via {done['via']} (id {done['id']}, état {done.get('status')})")
        except Exception as e:  # noqa: BLE001 — un réseau en échec ne bloque pas les autres
            out[n] = {"status": "error", "error": str(e)[:300], "at": now().isoformat(timespec="seconds")}
            log(f"publication : {n} ÉCHEC — {str(e)[:200]}")
    # Buffer publie en arrière-plan : on attend l'état final (au plus ~2 minutes)
    if buf is not None:
        pending = [n for n, d in out.items() if d.get("via") == "buffer" and d.get("status") not in ("sent", "error")]
        for _ in range(6):
            if not pending:
                break
            time.sleep(20)
            for n in list(pending):
                try:
                    stt = buf.status(out[n]["id"])["status"]
                    out[n]["status"] = stt
                    if stt in ("sent", "error"):
                        pending.remove(n)
                        log(f"publication : {n} — état Buffer « {stt} »")
                except Exception as e:  # noqa: BLE001
                    log(f"publication : état {n} illisible ({str(e)[:100]})")
                    pending.remove(n)
    return out
