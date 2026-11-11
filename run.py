#!/usr/bin/env python3
"""Agent autonome de vidéos motion design — point d'entrée.

  python3 run.py tick              ce que le serveur lance à chaque réveil (statistiques -> décision -> vidéo -> publication)
  python3 run.py make              fabrique (et publie, sauf mode essai) une vidéo tout de suite
  python3 run.py make --story f    idem, à partir d'un storyboard JSON écrit à la main
  python3 run.py demo              rend la vidéo d'exemple (aucune clé nécessaire, rien n'est publié)
  python3 run.py stats             relève les statistiques et recalcule les scores
  python3 run.py plan              affiche le plan du jour et ce que le stratège a appris
  python3 run.py doctor            vérifie l'installation, les clés et les quotas

Mode essai (publish.dry_run: true, ou --no-publish) : la vidéo est fabriquée et contrôlée, rien n'est publié
et rien n'est « consommé » (ni sujet, ni storyboard de réserve) : tout reste disponible pour le vrai lancement.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import random
import shutil
import sys
import time
import traceback
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from studio import config, llm, mediahost, notify, produce, schema, scout, stats, strategist, writer  # noqa: E402
from studio.config import secret  # noqa: E402
from studio.publish import caption_for, publish_all  # noqa: E402
from studio.state import State, now  # noqa: E402

LINES: list[str] = []


def log(msg: str) -> None:
    line = f"[{dt.datetime.now().strftime('%H:%M:%S')}] {msg}"
    LINES.append(line)
    print(line, flush=True)


def local_now(cfg: dict) -> dt.datetime:
    return dt.datetime.now(ZoneInfo((cfg.get("schedule") or {}).get("timezone", "UTC")))


def candidates(state: State, cfg: dict) -> list[dict]:
    """Veille du jour, mise en cache (une seule série d'appels par jour)."""
    cache = state.load("candidates", {})
    today = now().strftime("%Y-%m-%d")
    if cache.get("date") == today and cache.get("items"):
        return cache["items"]
    items = scout.gather(cfg, log)
    if items:
        state.save("candidates", {"date": today, "items": items})
    return items or cache.get("items", [])


def is_rehearsal(cfg: dict, publish: bool = True) -> bool:
    """Vrai tant que rien ne part sur les réseaux : réglage dry_run, ou vidéo demandée sans publication."""
    return (not publish) or bool((cfg.get("publish") or {}).get("dry_run", True))


def write_story(state: State, cfg: dict, brief: dict, brain, rehearsal: bool = False) -> tuple[dict, dict]:
    """Décide du sujet puis écrit le storyboard ; bascule sur la réserve si aucun modèle ne répond."""
    topic = {"items": [], "angle": "", "why": ""}
    try:
        cands = candidates(state, cfg) if brief["format"] != "offre" else []
        topic = strategist.pick_topic(state, cfg, cands, brief, brain if brain.available() else None, log)
        log(f"stratège : format « {brief['format']} », accroche « {brief['hook']} », longueur « {brief['length']} » — "
            f"sujet : {', '.join(i.get('title', '') for i in topic['items']) or '(offre)'} ({topic.get('why') or 'sans commentaire'})")
        if brief["format"] != "offre" and not topic["items"]:
            raise RuntimeError("aucun sujet nouveau trouvé par la veille")
        for it in topic["items"][:4]:
            if it.get("source") == "github" and not it.get("readme"):
                it["readme"] = scout.readme(it["id"][3:], 1500)
        taken = {p.get("keyword") for p in state.posts}
        story = writer.write(brain, brief, topic, cfg, strategist.memo(state), log, taken=taken)
        return story, topic
    except Exception as e:  # noqa: BLE001 — pas de cerveau disponible : on publie une vidéo de réserve
        log(f"scénariste : écriture par le LLM impossible ({type(e).__name__}: {str(e)[:220]})")
        story = writer.evergreen(cfg, state, log, rehearsal)
        if story is None:
            raise RuntimeError("aucun modèle disponible et plus aucun storyboard de réserve") from e
        # une réserve n'a pas été écrite pour ce format ni pour cette accroche : elle ne doit pas fausser l'apprentissage
        brief.update({"format": "reserve", "hook": None})
        return story, {"items": [{"id": f"evergreen:{story['_evergreen']}", "title": story["title"], "url": "", "facts": []}], "angle": "", "why": "réserve"}


def make_one(state: State, cfg: dict, slot: str, story: dict | None = None, publish: bool = True) -> dict | None:
    t0 = time.time()
    rng = random.Random(int(time.time()))
    brain = llm.Brain(cfg, state, log)
    brief = strategist.sample_brief(state, cfg, rng, slot)
    topic = {"items": [], "angle": "", "why": "storyboard fourni"}
    pcfg = cfg.get("publish") or {}
    essai = is_rehearsal(cfg, publish)
    if story is None:
        story, topic = write_story(state, cfg, brief, brain, essai)
    else:
        brief.update({"format": "manuel", "hook": None})      # scénario écrit à la main : ni format ni accroche à créditer
    stamp = local_now(cfg).strftime("%Y%m%d-%H%M")
    story, _ = schema.check(story, None)
    story = writer.apply_cta(story, cfg)          # même fin pour toutes les vidéos : commentaire + formation en promo, lien en bio
    post_id = f"{stamp}-{story['keyword'].lower()}"
    out_dir = ROOT / "out"
    res = produce.make_video(story, cfg, out_dir, post_id, log)
    story = res["story"]
    # l'apprentissage porte sur ce que la vidéo EST (durée réelle), pas sur ce qui avait été demandé
    asked = brief.get("length")
    brief["length"] = strategist.length_bucket(res["duration"])
    if asked and asked != brief["length"]:
        brief["length_asked"] = asked
    post = {"id": post_id, "created": now().isoformat(timespec="seconds"), "slot": slot, "brief": brief, "title": story["title"],
            "keyword": story["keyword"], "duration": round(res["duration"], 1), "words": res["words"], "llm": brain.used[-1:] or ["aucun"],
            "why": topic.get("why", ""), "facts": [{k: c.get(k) for k in ("id", "title", "url", "facts")} for c in topic.get("items", [])],
            "qa": {"ok": res["qa"]["ok"], "problems": res["qa"]["problems"], "warnings": res["qa"]["warnings"]}, "published": {}, "stats": {}}
    if essai:
        # répétition générale : on montre ce qui serait publié, mais on ne retient rien (ni sujet, ni réserve, ni vidéo comptée)
        if res["qa"]["ok"] and publish:
            post["published"] = publish_all(res["video"], story, res["thumb_ms"], None, cfg, state, log)
        elif res["qa"]["ok"]:
            log("légende prévue :\n" + caption_for(story, cfg, "tiktok"))
        else:
            log("contrôle qualité en échec : cette vidéo ne serait PAS publiée")
        n = state.load("essais", {"n": 0}); n["n"] = int(n.get("n", 0)) + 1; state.save("essais", n)
        state.log("essai", id=post_id, title=story["title"], seconds=round(time.time() - t0), qa=res["qa"]["ok"], reserve=story.get("_evergreen"))
        log(f"MODE ESSAI — terminé en {time.time() - t0:.0f} s : « {story['title']} » ({post['duration']} s). Rien n'a été publié ni compté.")
        return post
    if not res["qa"]["ok"]:
        log("contrôle qualité en échec : la vidéo n'est PAS publiée")
        state.add_post(post)
        return post
    # publication réelle : la vidéo doit d'abord être en ligne à une adresse publique (Buffer vient la chercher)
    public_url = None
    keep = int(pcfg.get("keep_videos", 30))
    if pcfg.get("media_host", "github_pages") == "cloudinary":
        public_url = mediahost.cloudinary_upload(Path(res["video"]), f"studio/{post_id}", log)
        hosted = state.load("hosted", [])
        if public_url:
            hosted.append(f"studio/{post_id}")
            for old_id in hosted[:-keep]:
                mediahost.cloudinary_delete(old_id)
            state.save("hosted", hosted[-keep:])
    else:
        base = mediahost.publish({f"v/{post_id}.mp4": Path(res["video"]), f"v/{post_id}.jpg": Path(res["thumb"])}, cfg, ROOT, keep, log)
        if base:
            url = f"{base}/v/{post_id}.mp4"
            if mediahost.wait_public(url, Path(res["video"]).stat().st_size, log=log):
                public_url = url
    if public_url:
        log(f"hébergement : {public_url}")
    post["published"] = publish_all(res["video"], story, res["thumb_ms"], public_url, cfg, state, log)
    if not any(v.get("status") not in ("skipped", "error") for v in post["published"].values()):
        # personne n'a reçu la vidéo : on ne compte rien (le sujet et la réserve restent disponibles) et l'exécution passe en échec
        detail = " ; ".join(f"{n} : {v.get('error') or v.get('status')}" for n, v in post["published"].items()) or "aucun réseau dans publish.networks"
        raise RuntimeError(f"aucun réseau n'a reçu la vidéo ({detail[:220]})")
    if story.get("_evergreen"):
        strategist.mark_seen(state, [{"id": f"evergreen:{story['_evergreen']}"}], story["title"])
    else:
        strategist.mark_seen(state, topic.get("items", []), story["title"])
    if brief.get("remake_of"):
        for p in state.posts:
            if p["id"] == brief["remake_of"]:
                p["remade"] = True
    state.add_post(post)
    state.log("video", id=post_id, title=story["title"], seconds=round(time.time() - t0), published={k: v.get("status") for k, v in post["published"].items()})
    log(f"terminé en {time.time() - t0:.0f} s : « {story['title']} » ({post['duration']} s)")
    return post


def due_slot(state: State, cfg: dict, when: dt.datetime) -> str | None:
    """Créneau du jour à traiter maintenant (au plus un par réveil), ou None."""
    rng = random.Random(when.strftime("%Y%m%d"))
    date = when.strftime("%Y-%m-%d")
    plan = strategist.plan_day(state, cfg, date, rng)
    grace = float((cfg.get("schedule") or {}).get("grace_hours", 4))
    for s in plan["slots"]:
        h, m = map(int, s.split(":"))
        t = when.replace(hour=h, minute=m, second=0, microsecond=0)
        done = plan["done"].get(s)
        if done and (done.get("ok") or done.get("tries", 0) >= 2):
            continue
        if t - dt.timedelta(minutes=12) <= when <= t + dt.timedelta(hours=grace):
            return s
    return None


def cmd_tick(args, cfg, state) -> int:
    try:
        n = stats.collect(state, cfg, log)
        strategist.score_posts(state, cfg)
        if n:
            log(f"statistiques : {n} relevé(s), scores recalculés")
    except Exception as e:  # noqa: BLE001 — les statistiques ne doivent jamais empêcher de produire
        log(f"statistiques : erreur ignorée ({type(e).__name__}: {str(e)[:160]})")
    when = local_now(cfg)
    date = when.strftime("%Y-%m-%d")
    plan = strategist.plan_day(state, cfg, date, random.Random(when.strftime("%Y%m%d")))     # le plan du jour existe toujours
    slot = when.strftime("%H:%M") if args.force else due_slot(state, cfg, when)
    if not slot:
        log(f"aucun créneau à traiter maintenant ({when.strftime('%H:%M')} ; plan du jour : {', '.join(plan['slots'])})")
        return 0
    days = state.load("day", {})
    # une vidéo forcée à la main s'ajoute au plan du jour sans le remplacer
    entry = days[date]["done"].setdefault(("manuel-" + slot) if args.force else slot, {"tries": 0, "ok": False})
    entry["tries"] += 1
    state.save("day", days)
    code = 0
    try:
        post = make_one(state, cfg, slot)
        entry["ok"] = bool(post and post["qa"]["ok"])
        entry["post"] = post and post["id"]
    except Exception as e:  # noqa: BLE001
        log(f"ÉCHEC de la production : {type(e).__name__}: {str(e)[:300]}")
        traceback.print_exc()
        state.log("error", slot=slot, error=f"{type(e).__name__}: {str(e)[:300]}")
        code = 1
    state.save("day", days)
    summary(cfg)
    return code


def summary(cfg: dict) -> None:
    text = "\n".join(LINES[-40:])
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write("### Agent vidéo\n```\n" + text + "\n```\n")
    notify.telegram("🎬 Agent vidéo\n" + "\n".join(LINES[-12:]), cfg, log)


def cmd_make(args, cfg, state) -> int:
    story = json.loads(Path(args.story).read_text(encoding="utf-8")) if args.story else None
    post = make_one(state, cfg, local_now(cfg).strftime("%H:%M"), story, publish=not args.no_publish)
    summary(cfg)
    return 0 if post and post["qa"]["ok"] else 1


def cmd_demo(args, cfg, state) -> int:
    story = json.loads((ROOT / "examples" / "demo_storyboard.json").read_text(encoding="utf-8"))
    story, _ = schema.check(story, None)
    res = produce.make_video(writer.apply_cta(story, cfg), cfg, ROOT / "out", "demo", log)
    return 0 if res["qa"]["ok"] else 1


def cmd_stats(args, cfg, state) -> int:
    n = stats.collect(state, cfg, log)
    strategist.score_posts(state, cfg)
    log(f"{n} relevé(s)")
    print(strategist.memo(state))
    return 0


def cmd_plan(args, cfg, state) -> int:
    when = local_now(cfg)
    plan = strategist.plan_day(state, cfg, when.strftime("%Y-%m-%d"), random.Random(when.strftime("%Y%m%d")))
    print(f"Aujourd'hui ({when.strftime('%Y-%m-%d')}, {cfg['schedule']['timezone']}) : créneaux {plan['slots']} — faits : {plan['done']}")
    print(f"Vidéos en mémoire : {len(state.posts)} (dont notées : {sum(p.get('score') is not None for p in state.posts)})\n")
    for dim, values in (("format", [f for f in strategist.FORMATS if f != "offre"]), ("hook", list(strategist.HOOKS)),
                        ("length", list(strategist.LENGTHS)), ("slot", ["matin", "midi", "soir"])):
        post = strategist.posterior(values, dim, state)
        obs = strategist.arm_stats(state, dim)
        print(f"{dim:8s} " + "  ".join(f"{v}={m:+.2f}±{s:.2f}(n={len(obs.get(v, []))})" for v, (m, s) in sorted(post.items(), key=lambda kv: -kv[1][0])))
    print("\n" + strategist.memo(state))
    return 0


def cmd_doctor(args, cfg, state) -> int:
    ok = True

    def line(good, label, detail=""):
        nonlocal ok
        ok = ok and (good is not False)
        print(f"  {'✅' if good else ('⚠️ ' if good is None else '❌')} {label}{(' — ' + detail) if detail else ''}")
    print("Outils")
    line(bool(shutil.which("ffmpeg")), "ffmpeg")
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch(args=["--no-sandbox"]); v = b.version; b.close()
        line(True, "Chromium (rendu)", v)
    except Exception as e:  # noqa: BLE001
        line(False, "Chromium (rendu)", f"{type(e).__name__} — lance : python3 -m playwright install --with-deps chromium-headless-shell")
    try:
        import edge_tts  # noqa: F401
        line(True, "edge-tts (voix)")
    except ImportError:
        line(False, "edge-tts (voix)", "pip install edge-tts")
    print("Cerveau (modèles gratuits)")
    brain = llm.Brain(cfg, state, lambda *_: None)
    for p in cfg["llm"]["providers"]:
        has = bool(secret(p["key_env"]))
        used = state.quota_used(f"llm:{p['name']}")
        line(True if has else None, f"{p['name']} ({p['key_env']})", f"{used}/{p.get('rpd')} appels aujourd'hui" if has else "clé absente")
    if not brain.available():
        line(None, "aucune clé de modèle", "l'agent n'utilisera que ses storyboards de réserve")
    elif args.live:
        try:
            txt = brain.chat([{"role": "user", "content": "Réponds par le seul mot : prêt"}], max_tokens=600)
            line(True, "appel d'essai", f"{brain.used[-1]} a répondu « {txt.strip()[:30]} »")
        except Exception as e:  # noqa: BLE001
            line(False, "appel d'essai", str(e)[:200])
    print("Publication")
    pcfg = cfg.get("publish") or {}
    line(None if pcfg.get("dry_run", True) else True, "mode", "ESSAI (dry_run: true) : rien n'est publié" if pcfg.get("dry_run", True) else "publication réelle")
    if secret("BUFFER_API_KEY"):
        if args.live:
            try:
                from studio.publish.buffer import Buffer
                ch = Buffer(secret("BUFFER_API_KEY"), state).channels()
                have = {c["service"] for c in ch}
                line(True, "Buffer", "canaux : " + ", ".join(f"{c['service']} ({c['name']})" for c in ch))
                for n_ in pcfg.get("networks", []):
                    if n_ not in have:
                        line(None, f"réseau {n_}", "pas de canal Buffer correspondant")
            except Exception as e:  # noqa: BLE001
                line(False, "Buffer", str(e)[:200])
        else:
            line(True, "Buffer (BUFFER_API_KEY)", "clé présente (ajoute --live pour la tester)")
    else:
        line(None, "Buffer (BUFFER_API_KEY)", "clé absente")
    for name, keys in (("Facebook natif", ["FB_PAGE_ID", "FB_PAGE_TOKEN"]), ("Instagram natif", ["IG_USER_ID"]),
                       ("TikTok natif", ["TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET", "TIKTOK_REFRESH_TOKEN"])):
        if any(secret(k) for k in keys):
            line(all(secret(k) for k in keys), name, "clés : " + ", ".join(k for k in keys if secret(k)))
    base = mediahost.base_url(cfg, ROOT)
    line(True if base else None, "hébergement des vidéos", base or "pas de dépôt GitHub détecté ici")
    print("Quotas du jour : " + (json.dumps(state.load("quota", {}).get(now().strftime("%Y-%m-%d"), {}), ensure_ascii=False) or "{}"))
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("tick"); t.add_argument("--force", action="store_true", help="produit une vidéo maintenant, même hors créneau")
    m = sub.add_parser("make"); m.add_argument("--story"); m.add_argument("--no-publish", action="store_true")
    sub.add_parser("demo"); sub.add_parser("stats"); sub.add_parser("plan")
    d = sub.add_parser("doctor"); d.add_argument("--live", action="store_true", help="teste réellement les clés (consomme 1 appel chacune)")
    args = ap.parse_args()
    cfg = config.load()
    state = State(ROOT)
    return {"tick": cmd_tick, "make": cmd_make, "demo": cmd_demo, "stats": cmd_stats, "plan": cmd_plan,
            "doctor": cmd_doctor}[args.cmd](args, cfg, state)


if __name__ == "__main__":
    sys.exit(main())
