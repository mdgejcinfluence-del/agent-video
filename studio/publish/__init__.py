"""Publication sur les réseaux : Buffer en premier (1 clé, TikTok public), API natives en complément."""
from __future__ import annotations

import time
from pathlib import Path

from ..config import secret
from ..state import now


NETWORKS = {"tiktok": "TikTok", "instagram": "Instagram Reels", "youtube": "YouTube Shorts", "facebook": "Facebook Reels"}


def legende(story: dict, cfg: dict, credit: str = "") -> str:
    """La légende, toujours bâtie de la même façon : accroche, étapes, limite honnête, consigne, suite, hashtags, crédit des images."""
    from .. import schema, writer
    leg = story.get("legende") or {}
    chiffres = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
    lignes = [str(leg.get("accroche") or story.get("title") or "").strip()]
    lignes += [f"{chiffres[i]} {p}" for i, p in enumerate((leg.get("points") or [])[:5])]
    if leg.get("limite"):
        lignes.append(f"⚠️ {leg['limite']}")
    kw = str(story.get("keyword") or "").upper()
    prom = schema.visible(story.get("promesse") or "la suite")
    lignes.append(f"💬 Commente {kw} si tu veux {prom}")
    lignes.append("🔔 Abonne-toi pour ne rien rater")
    if writer.promo_active(cfg):
        lignes.append("🎓 La formation complète est en promo : lien en bio")
    return "\n".join(l for l in lignes if l)


def packs(story: dict, cfg: dict, credit: str = "") -> dict[str, dict]:
    """Pack de publication par plateforme : titre, légende, hashtags, texte de couverture."""
    pcfg = cfg.get("publish") or {}
    n = int(pcfg.get("hashtags", 8))
    tags = [h if h.startswith("#") else "#" + h for h in (story.get("hashtags") or [])][:n]
    title = (story.get("title") or "").strip()
    corps = legende(story, cfg)
    cover = " ".join(str(x).replace("*", "") for x in (story.get("couverture") or [title]))[:60]
    cr = credit if pcfg.get("credit_rushs", True) else ""

    def text(k: int = n) -> str:
        return "\n\n".join(p for p in [corps, " ".join(tags[:k]), cr] if p).strip()
    return {
        "facebook": {"titre": title, "legende": text(), "hashtags": tags, "couverture": cover},
        "instagram": {"titre": title, "legende": text(), "hashtags": tags, "couverture": cover},
        "tiktok": {"titre": title, "legende": text(min(n, 6)), "hashtags": tags[:6], "couverture": cover},
        "youtube": {"titre": title[:100], "legende": text(3), "hashtags": tags[:3], "couverture": cover},
    }


def caption_for(story: dict, cfg: dict, network: str, credit: str = "") -> str:
    p = packs(story, cfg, credit)
    return (p.get(network) or p["facebook"])["legende"][:2100]


def publish_all(video: str | Path, story: dict, thumb_ms: int, public_url: str | None, cfg: dict, state, log=print, credit: str = "") -> dict:
    from ..config import essai
    pcfg = cfg.get("publish") or {}
    nets = list(pcfg.get("networks") or [])
    out: dict[str, dict] = {}
    if essai(cfg):
        for n in nets:
            out[n] = {"status": "dry_run", "at": now().isoformat(timespec="seconds")}
        log("publication : mode essai — rien n'a été envoyé. Légende prévue :\n" + caption_for(story, cfg, "facebook", credit))
        return out
    ai = bool(pcfg.get("ai_label", True))
    buf = None
    if pcfg.get("via", "buffer") == "buffer" and secret("BUFFER_API_KEY"):
        from .buffer import Buffer
        buf = Buffer(secret("BUFFER_API_KEY"), state)
    for n in nets:
        text = caption_for(story, cfg, n, credit)
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
