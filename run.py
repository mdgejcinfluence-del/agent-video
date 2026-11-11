#!/usr/bin/env python3
"""Agent vidéo autonome — point d'entrée.

  python3 run.py tick              ce que GitHub lance à chaque réveil : mesures -> bilan (tous les 3 jours) -> veille -> choix -> vidéo -> publication
  python3 run.py make              fabrique une vidéo tout de suite (--story fichier.json, --reserve nom, --no-publish)
  python3 run.py demo              rend toutes les vidéos de réserve (aucune clé nécessaire, rien n'est publié)
  python3 run.py bilan             fait le bilan maintenant (mesures, classement, nouveaux poids, state/BILAN.md)
  python3 run.py sujets            la banque d'idées, les poids des familles, les suites promises
  python3 run.py rushs "mots"      cherche une séquence filmée comme le ferait l'agent (essai des banques d'images)
  python3 run.py veille            rouvre les pages officielles et reconfirme les faits
  python3 run.py stats             relève les mesures et recalcule les notes
  python3 run.py plan              le plan du jour et la prochaine vidéo
  python3 run.py doctor            vérifie l'installation, les clés et les réserves (--live : teste réellement les clés)

L'agent travaille seul. Il n'a pas de validation humaine : il ne publie que ce que ses contrôles automatiques ont accepté
(forme, garde-fous, séquences filmées, contrôle qualité). Tant qu'aucune clé de publication n'existe, il est en MODE ESSAI :
les vidéos sont fabriquées et contrôlées, rien n'est publié, rien n'est compté.
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

# ffmpeg et ffprobe « autonomes » posés par setup.sh quand le système n'en fournit pas (voir setup.sh)
_OUTILS = Path.home() / ".cache" / "agent-video" / "bin"
if _OUTILS.is_dir():
    os.environ["PATH"] = f"{_OUTILS}{os.pathsep}{os.environ.get('PATH', '')}"
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out"                      # vidéos, couvertures et fiches de production
sys.path.insert(0, str(ROOT))

from studio import bilan, config, fiche, llm, mediahost, notify, porte, produce, rushs, scout, stats, strategist, writer  # noqa: E402
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


def veille(state: State, cfg: dict, force: bool = False, brain=None) -> dict[str, dict]:
    """Veille du jour sur les faits (pages officielles), puis liste des faits utilisables aujourd'hui."""
    if (cfg.get("research") or {}).get("faits", True):
        try:
            scout.verifier_faits(ROOT, state, log, force=force)
        except Exception as e:  # noqa: BLE001
            log(f"veille : vérification des faits impossible ({type(e).__name__}: {str(e)[:120]})")
    if brain is not None:
        try:
            scout.proposer_faits(brain, ROOT, state, cfg, log)       # avec Gemini : de nouveaux faits, gardés seulement s'ils se relisent sur la page officielle
        except Exception as e:  # noqa: BLE001
            log(f"veille : nouveaux faits — erreur ignorée ({type(e).__name__})")
    return scout.faits_confirmes(ROOT, state)


def is_rehearsal(cfg: dict, publish: bool = True) -> bool:
    """Vrai tant que rien ne part sur les réseaux : mode essai, ou vidéo demandée sans publication."""
    return (not publish) or config.essai(cfg)


def _host(post_id: str, res: dict, cfg: dict, state: State) -> str | None:
    """Met la vidéo en ligne à une adresse publique (Buffer vient la chercher)."""
    pcfg = cfg.get("publish") or {}
    keep = int(pcfg.get("keep_videos", 30))
    if pcfg.get("media_host", "github_pages") == "cloudinary":
        url = mediahost.cloudinary_upload(Path(res["video"]), f"studio/{post_id}", log)
        hosted = state.load("hosted", [])
        if url:
            hosted.append(f"studio/{post_id}")
            for old_id in hosted[:-keep]:
                mediahost.cloudinary_delete(old_id)
            state.save("hosted", hosted[-keep:])
        return url
    base = mediahost.publish({f"v/{post_id}.mp4": Path(res["video"]), f"v/{post_id}.jpg": Path(res["thumb"])}, cfg, ROOT, keep, log)
    if base:
        url = f"{base}/v/{post_id}.mp4"
        if mediahost.wait_public(url, Path(res["video"]).stat().st_size, log=log):
            return url
    return None


def ecrire(state: State, cfg: dict, choix: dict, faits: dict, brain, essai: bool) -> tuple[dict | None, str]:
    """Le storyboard : écrit par Gemini si une clé existe, sinon pris en réserve. Renvoie (storyboard, origine)."""
    idee = choix["idee"]
    if choix.get("reserve") and (essai or not brain.available()):
        st = writer.reserve(cfg, choix["reserve"])
        if st is not None:
            log(f"scénariste : storyboard de réserve « {choix['reserve']} »" + (" — essai : rien n'est consommé" if essai else ""))
            return st, f"réserve {choix['reserve']}"
    if brain.available():
        try:
            recents = [p.get("title", "") for p in state.posts[-12:]]
            st = writer.write(brain, {**idee, "famille": choix["famille"], "hook_type": choix.get("hook_type") or "resultat"}, faits, cfg,
                              strategist.memo(state), log, recents)
            return st, f"modèle {brain.used[-1] if brain.used else '?'}"
        except Exception as e:  # noqa: BLE001 — pas de modèle disponible, ou réponses toutes refusées : réserve
            log(f"scénariste : écriture par le modèle impossible ({type(e).__name__}: {str(e)[:220]})")
    res = idee.get("reserve")
    st = writer.reserve(cfg, res) if res else None
    if st is not None:
        log(f"scénariste : storyboard de réserve « {res} »")
        return st, f"réserve {res}"
    return None, "aucune réserve pour cette idée"


def make_one(state: State, cfg: dict, slot: str, story: dict | None = None, publish: bool = True, post_id: str | None = None) -> dict | None:
    """Fabrique une vidéo et, hors mode essai, la publie. Renvoie la fiche du post, ou None s'il n'y avait rien à produire."""
    t0 = time.time()
    when = local_now(cfg)
    rng = random.Random(int(time.time()))
    essai = is_rehearsal(cfg, publish)
    brain = llm.Brain(cfg, state, log)
    faits = veille(state, cfg)
    reserves = [r["_reserve"] for r in writer.reserves(cfg)]
    choix, origine = None, "storyboard fourni à la main"
    res = None
    if story is None:
        essais = 0
        ecartes: set[str] = set()
        while res is None and essais < 3:
            essais += 1
            choix = strategist.choisir(ROOT, state, cfg, faits, rng, essai, brain.available(), [r for r in reserves if r not in ecartes])
            if choix is None:
                log("stratège : rien à produire — toutes les idées disponibles ont été traitées récemment"
                    + ("" if brain.available() else " et aucune clé GEMINI_API_KEY ne permet d'en écrire de nouvelles (il ne reste que les 6 réserves)"))
                state.log("rien")
                return None
            i = choix["idee"]
            log(f"stratège : « {i.get('sujet')} » — {choix['pourquoi']}" + (f", accroche « {choix['hook_type']} »" if choix.get("hook_type") else ""))
            story, origine = ecrire(state, cfg, choix, faits, brain, essai)
            if story is None:
                log(f"scénariste : {origine}")
                return None
            try:
                stamp = when.strftime("%Y%m%d-%H%M")
                story, _ = writer.controler(story, cfg, faits, strict=True)
                pid = post_id or f"{stamp}-{story['keyword'].lower()}"
                res = produce.make_video(story, cfg, OUT, pid, log, faits=faits, state=state, brain=brain)
                post_id = pid
            except produce.RushIntrouvable as e:
                log(f"rushs : {e} — la vidéo n'est pas fabriquée, autre sujet")
                if story.get("_reserve"):
                    ecartes.add(story["_reserve"])
                state.log("rush_introuvable", sujet=i.get("sujet"), detail=str(e)[:300])
                if essai:                                   # en essai, on avance d'un cran pour ne pas retomber sur la même réserve
                    n = state.load("essais", {"n": 0}); n["n"] = int(n.get("n", 0)) + 1; state.save("essais", n)
                story = None
        if res is None:
            log("aucune vidéo fabriquée : pas de séquence filmée acceptable pour les sujets essayés")
            return None
    else:
        stamp = when.strftime("%Y%m%d-%H%M")
        story, _ = writer.controler(story, cfg, faits, strict=True)
        post_id = post_id or f"{stamp}-{story['keyword'].lower()}"
        res = produce.make_video(story, cfg, OUT, post_id, log, faits=faits, state=state, brain=brain)
    story = res["story"]
    reserve = story.get("_reserve")
    credit = rushs.ligne_credit(res["rushs"])
    blocs = porte.bloquants(cfg, story, res["qa"], faits)
    brief = {"idee": ((choix or {}).get("idee") or {}).get("id") or story.get("idee"), "famille": story.get("famille"), "hook_type": story.get("hook_type"),
             "slot": strategist.slot_bucket(slot), "slot_exact": slot, "origine": origine.split(" ")[0], **({"reserve": reserve} if reserve else {}),
             **({"suite_de": choix["suite_de"]} if (choix or {}).get("suite_de") else {})}
    fp = fiche.ecrire(OUT / f"{post_id}.md", story, cfg, res, choix, faits, origine, blocs)
    log(f"fiche de production : {fp.name}")
    post = {"id": post_id, "created": now().isoformat(timespec="seconds"), "slot": slot, "brief": brief, "title": story["title"],
            "keyword": story["keyword"], "duration": round(res["duration"], 1), "words": res["words"], "thumb_ms": res["thumb_ms"],
            "llm": brain.used[-1:] or ["aucun"], "why": (choix or {}).get("pourquoi", ""), "faits": story.get("faits") or [],
            "rushs": [c["id"] for c in res["rushs"].values()],
            "qa": {"ok": res["qa"]["ok"], "problems": res["qa"]["problems"], "warnings": res["qa"]["warnings"]}, "published": {}, "stats": {}}
    if essai:
        log("porte de publication : " + ("rien ne bloque" if not blocs else "la vidéo serait RETENUE — " + " ; ".join(blocs)))
        log("légende prévue (Facebook) :\n" + caption_for(story, cfg, "facebook", credit))
        n = state.load("essais", {"n": 0}); n["n"] = int(n.get("n", 0)) + 1; state.save("essais", n)
        state.log("essai", id=post_id, title=story["title"], famille=story.get("famille"), seconds=round(time.time() - t0), qa=res["qa"]["ok"], reserve=reserve,
                  rushs=post["rushs"])
        log(f"MODE ESSAI — terminé en {time.time() - t0:.0f} s : « {story['title']} » ({post['duration']} s). Rien n'a été publié ni compté.")
        return post
    if blocs:
        log("PUBLICATION RETENUE — " + " ; ".join(blocs))
        state.log("retenue", id=post_id, raisons=blocs)
        return post
    public_url = _host(post_id, res, cfg, state)
    if public_url:
        log(f"hébergement : {public_url}")
    post["published"] = publish_all(res["video"], story, int(post["thumb_ms"]), public_url, cfg, state, log, credit)
    if not any(v.get("status") not in ("skipped", "error") for v in post["published"].values()):
        detail = " ; ".join(f"{n} : {v.get('error') or v.get('status')}" for n, v in post["published"].items()) or "aucun réseau dans publish.networks"
        raise RuntimeError(f"aucun réseau n'a reçu la vidéo ({detail[:220]})")
    state.add_post(post)
    rushs.noter_usage(state, post["rushs"])
    strategist.noter_suite(state, post, story)
    if (choix or {}).get("suite_de"):
        strategist.marquer_suite(state, choix["suite_de"], post_id)
    state.log("video", id=post_id, title=post["title"], published={k: v.get("status") for k, v in post["published"].items()})
    log(f"terminé en {time.time() - t0:.0f} s : « {story['title']} » ({post['duration']} s) — publiée")
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
        if t - dt.timedelta(minutes=25) <= when <= t + dt.timedelta(hours=grace):
            return s
    return None


def mesures(state: State, cfg: dict, brain=None, force_bilan: bool = False) -> None:
    """Relevé des statistiques par l'API des réseaux, notes, puis bilan tous les 3 jours."""
    try:
        n = stats.collect(state, cfg, log)
        strategist.score_posts(state, cfg)
        if n:
            log(f"mesures : {n} relevé(s), notes recalculées")
    except Exception as e:  # noqa: BLE001 — les mesures ne doivent jamais empêcher de produire
        log(f"mesures : erreur ignorée ({type(e).__name__}: {str(e)[:160]})")
    try:
        if force_bilan or (bilan.du(state, cfg) and (state.posts or not (state.load("bilan", {}) or {}).get("fait_le"))):
            bilan.faire(state, cfg, ROOT, brain, log, scout.faits_confirmes(ROOT, state))
    except Exception as e:  # noqa: BLE001
        log(f"bilan : erreur ignorée ({type(e).__name__}: {str(e)[:160]})")


def cmd_tick(args, cfg, state) -> int:
    brain = llm.Brain(cfg, state, log)
    mesures(state, cfg, brain)
    when = local_now(cfg)
    date = when.strftime("%Y-%m-%d")
    plan = strategist.plan_day(state, cfg, date, random.Random(when.strftime("%Y%m%d")))     # le plan du jour existe toujours
    slot = when.strftime("%H:%M") if args.force else due_slot(state, cfg, when)
    if not slot:
        veille(state, cfg, brain=brain)          # la veille du jour a lieu même sans vidéo à produire
        log(f"aucun créneau à traiter maintenant ({when.strftime('%H:%M')} ; plan du jour : " + (", ".join(plan["slots"]) or "pas de publication aujourd'hui") + ")")
        summary(cfg, notify_user=False)
        return 0
    days = state.load("day", {})
    entry = days[date]["done"].setdefault(("manuel-" + slot) if args.force else slot, {"tries": 0, "ok": False})
    entry["tries"] += 1
    state.save("day", days)
    code = 0
    try:
        post = make_one(state, cfg, slot)
        entry["ok"] = post is None or bool(post["qa"]["ok"])          # « rien à produire » n'est pas une panne
        entry["post"] = post and post.get("id")
    except Exception as e:  # noqa: BLE001
        log(f"ÉCHEC de la production : {type(e).__name__}: {str(e)[:400]}")
        traceback.print_exc()
        state.log("error", slot=slot, error=f"{type(e).__name__}: {str(e)[:300]}")
        code = 1
    state.save("day", days)
    summary(cfg)
    return code


def summary(cfg: dict, notify_user: bool = True) -> None:
    text = "\n".join(LINES[-60:])
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write("### Agent vidéo\n```\n" + text + "\n```\n")
    if notify_user:
        notify.telegram("🎬 Agent vidéo\n" + "\n".join(LINES[-14:]), cfg, log)


def cmd_make(args, cfg, state) -> int:
    story = None
    if args.story:
        story = json.loads(Path(args.story).read_text(encoding="utf-8"))
        story.setdefault("_reserve", Path(args.story).stem)
    elif args.reserve:
        story = writer.reserve(cfg, args.reserve)
        if story is None:
            print(f"réserve inconnue : {args.reserve} (réserves : {', '.join(r['_reserve'] for r in writer.reserves(cfg))})")
            return 1
    post = make_one(state, cfg, local_now(cfg).strftime("%H:%M"), story=story, publish=not args.no_publish)
    summary(cfg, notify_user=False)
    return 0 if post is None or post["qa"]["ok"] else 1


def cmd_demo(args, cfg, state) -> int:
    """Toutes les réserves, l'une après l'autre : pour voir chaque format sans rien publier."""
    code = 0
    for r in writer.reserves(cfg):
        try:
            post = make_one(state, cfg, local_now(cfg).strftime("%H:%M"), story=r, publish=False, post_id=f"demo-{r['_reserve']}")
            code = code or (0 if post and post["qa"]["ok"] else 1)
        except Exception as e:  # noqa: BLE001
            log(f"démo {r['_reserve']} : ÉCHEC — {type(e).__name__}: {str(e)[:300]}")
            code = 1
    summary(cfg, notify_user=False)
    return code


def cmd_bilan(args, cfg, state) -> int:
    mesures(state, cfg, llm.Brain(cfg, state, log), force_bilan=True)
    print((Path(state.dir) / "BILAN.md").read_text(encoding="utf-8"))
    return 0


def cmd_sujets(args, cfg, state) -> int:
    faits = scout.faits_confirmes(ROOT, state)
    bq = strategist.banque(ROOT)
    w = strategist.poids(ROOT, state)
    used = {(p.get("brief") or {}).get("idee") for p in strategist._used(state, int((cfg.get("strategy") or {}).get("repeat_days", 21)))}
    print("Familles (poids actuels) :")
    for k, f in sorted(bq["familles"].items(), key=lambda x: -w.get(x[0], 0)):
        print(f"  {w.get(k, 0):5.0%}  {f.get('nom')}")
    print("\nIdées :")
    for i in strategist.idees(ROOT, state):
        manque = [f for f in (i.get("faits") or []) if f not in faits]
        etat = "déjà traitée" if i["id"] in used else ("fait non confirmé : " + ", ".join(manque)) if manque else "disponible"
        print(f"  [{i['famille']:11s}] {i['sujet'][:86]} — {etat}" + (f" (réserve {i['reserve']})" if i.get("reserve") else ""))
    q = [s for s in state.load("suites", []) if not s.get("faite")]
    print(f"\nSuites promises à produire : {len(q)}")
    for s in q:
        print(f"  « {s.get('promesse')} » (mot {s.get('keyword')}, annoncée par {s.get('de')})")
    return 0


def cmd_rushs(args, cfg, state) -> int:
    """Essaie la recherche d'une séquence comme le fait l'agent : sources, contrôles, choix."""
    brain = llm.Brain(cfg, state, log)
    print("banques actives :", ", ".join(rushs.sources_actives()) or "aucune clé (bibliothèque de départ seulement)", "| contrôle par l'image :", "oui" if brain.vision() else "non")
    besoin = {"ref": "essai", "q": args.mots, "voir": args.voir or args.mots, "cadre": args.cadre, "phrase": args.voir or args.mots, "sensible": False}
    got = rushs.choisir([besoin], cfg, state, brain, ROOT, log)
    if not got:
        print("aucune séquence acceptable")
        return 1
    c = got["essai"]
    print(json.dumps({k: c.get(k) for k in ("id", "source", "auteur", "page", "licence", "controle", "mesures", "fichier")}, ensure_ascii=False, indent=1))
    return 0


def cmd_veille(args, cfg, state) -> int:
    faits = veille(state, cfg, force=True)
    allf = scout.charger_faits(ROOT, state)["faits"]
    for fid, f in allf.items():
        ok = fid in faits
        print(f"  {'✅' if ok else '❌'} {fid} — {f.get('affirmation')[:90]}" + ("" if ok else "  [NON CONFIRMÉ]"))
    return 0


def cmd_stats(args, cfg, state) -> int:
    mesures(state, cfg)
    for p in state.posts[-15:]:
        print(f"  {p['id']} | note {p.get('score', '—')} | {strategist.vues(p)} vues | {p['title'][:60]}")
    return 0


def cmd_plan(args, cfg, state) -> int:
    when = local_now(cfg)
    plan = strategist.plan_day(state, cfg, when.strftime("%Y-%m-%d"), random.Random(when.strftime("%Y%m%d")))
    essai = config.essai(cfg)
    print(f"Aujourd'hui ({when.strftime('%Y-%m-%d %H:%M')}) : créneaux {', '.join(plan['slots']) or '—'} · mode {'ESSAI' if essai else 'PUBLICATION RÉELLE'}")
    brain = llm.Brain(cfg, state, lambda *_: None)
    faits = scout.faits_confirmes(ROOT, state)
    reserves = [r["_reserve"] for r in writer.reserves(cfg)]
    c = strategist.choisir(ROOT, state, cfg, faits, random.Random(1), essai, brain.available(), reserves)
    print("Prochaine vidéo :", f"« {c['idee'].get('sujet')} » — {c['pourquoi']}" if c else "rien à produire")
    print(f"Idées encore disponibles : {strategist.reste(ROOT, state, cfg, faits, brain.available(), reserves)} "
          f"({'avec' if brain.available() else 'sans'} modèle d'écriture)")
    b = state.load("bilan", {}) or {}
    print("Dernier bilan :", b.get("fait_le", "jamais"), "· prochain :", b.get("prochain", "au prochain réveil"))
    return 0


def cmd_doctor(args, cfg, state) -> int:
    ok = True

    def line(good, label, detail=""):
        nonlocal ok
        ok = ok and (good is not False)
        print(f"  {'✅' if good else ('⚠️ ' if good is None else '❌')} {label}{(' — ' + detail) if detail else ''}")
    print("Outils")
    line(bool(shutil.which("ffmpeg")) and bool(shutil.which("ffprobe")), f"ffmpeg et ffprobe — {shutil.which('ffmpeg') or 'introuvable'}")
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
    poses = json.loads((ROOT / "engine" / "avatar" / "poses.json").read_text()) if (ROOT / "engine" / "avatar" / "poses.json").exists() else {}
    line(len(poses) >= 8, "personnage", f"{len(poses)} poses")
    print("Faits et réserves")
    faits = veille(state, cfg, force=args.live)
    allf = scout.charger_faits(ROOT, state)["faits"]
    line(len(faits) == len(allf), "faits vérifiés", f"{len(faits)}/{len(allf)} utilisables" + ("" if args.live else " (ajoute --live pour rouvrir les pages officielles)"))
    n_ok = 0
    for st_ in writer.reserves(cfg):
        try:
            writer.controler(dict(st_), cfg, faits, strict=True)
            n_ok += 1
        except Exception as e:  # noqa: BLE001
            line(False, f"réserve {st_['_reserve']}", str(e)[:200])
    line(n_ok > 0, "storyboards de réserve", f"{n_ok} acceptés par les contrôles")
    print("Cerveau (Gemini)")
    brain = llm.Brain(cfg, state, lambda *_: None)
    if not brain.key():
        line(None, "GEMINI_API_KEY", "absente : l'agent n'a que ses 6 réserves, il n'écrit rien de nouveau et ne regarde pas les images")
    else:
        line(True, "GEMINI_API_KEY", f"{state.quota_used('llm:gemini')} appel(s) aujourd'hui")
        if args.live:
            try:
                m1, m2 = brain.modeles("ecriture")[:2], brain.modeles("controle")[:2]
                line(bool(m1), "modèles", f"écriture : {', '.join(m1) or '—'} · contrôle : {', '.join(m2) or '—'}")
                obj = brain.ask_json("Réponds par un objet JSON.", 'Renvoie {"etat": "pret"}', niveau="controle", max_tokens=200, retries=0)
                line(True, "appel d'essai", f"{brain.used[-1]} a répondu {json.dumps(obj, ensure_ascii=False)[:40]}")
            except Exception as e:  # noqa: BLE001
                line(False, "appel d'essai", str(e)[:200])
    line(True if secret("GROQ_API_KEY") else None, "GROQ_API_KEY (secours, facultatif)", "présente" if secret("GROQ_API_KEY") else "absente")
    print("Séquences filmées")
    lib = rushs.bibliotheque(ROOT)
    for name, key in (("Pexels", "PEXELS_API_KEY"), ("Pixabay", "PIXABAY_API_KEY")):
        line(True if secret(key) else None, f"{name} ({key})", "présente" if secret(key) else "absente")
    line(True if rushs.sources_actives() else None, "recherche de rushs", "banques interrogées en direct" if rushs.sources_actives() else f"aucune clé : seulement les {len(lib)} séquences de la bibliothèque de départ")
    if args.live and rushs.sources_actives():
        try:
            got = rushs.chercher("hands typing laptop", "portrait", None, lambda *_: None)
            line(bool(got), "recherche d'essai", f"{len(got)} séquence(s) pour « hands typing laptop »")
        except Exception as e:  # noqa: BLE001
            line(False, "recherche d'essai", str(e)[:160])
    print("Publication")
    essai = config.essai(cfg)
    line(None if essai else True, "mode", "ESSAI : rien n'est publié (aucune clé de publication, ou dry_run: true)" if essai else "PUBLICATION RÉELLE, sans validation humaine")
    line(True if writer.promo_active(cfg) else None, "formation annoncée à la fin", "oui" if writer.promo_active(cfg) else "non (offer.promo.confirmee + offer.lien_bio) : l'écran de fin annonce seulement la suite")
    pcfg = cfg.get("publish") or {}
    if secret("BUFFER_API_KEY"):
        try:
            from studio.publish.buffer import Buffer
            chans = Buffer(secret("BUFFER_API_KEY"), state).channels() if args.live else None
            line(True, "Buffer (BUFFER_API_KEY)", ("canaux : " + ", ".join(sorted({c.get("service", "?") for c in chans}))) if chans is not None else "clé présente")
        except Exception as e:  # noqa: BLE001
            line(False, "Buffer", str(e)[:160])
    else:
        line(None, "Buffer (BUFFER_API_KEY)", "clé absente")
    for name, keys in (("Facebook (API Meta)", ("FB_PAGE_ID", "FB_PAGE_TOKEN")), ("Instagram (API Meta)", ("IG_USER_ID",)),
                       ("TikTok (API)", ("TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET", "TIKTOK_REFRESH_TOKEN"))):
        have = all(secret(k) for k in keys)
        line(True if have else None, name, "clés présentes" if have else "clés absentes")
    if pcfg.get("media_host", "github_pages") == "github_pages":
        base = mediahost.base_url(cfg, ROOT)
        line(True if base else None, "hébergement des vidéos (GitHub Pages)", base or "adresse inconnue hors de GitHub")
    b = state.load("bilan", {}) or {}
    line(True, "bilan automatique", f"dernier : {b.get('fait_le', 'jamais')} · tous les {int((cfg.get('bilan') or {}).get('tous_les_jours', 3))} jours")
    print("\n" + ("Tout est en ordre." if ok else "Des points sont à corriger (❌)."))
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Agent vidéo autonome")
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("tick"); t.add_argument("--force", action="store_true", help="produit une vidéo maintenant, même hors créneau")
    m = sub.add_parser("make"); m.add_argument("--story"); m.add_argument("--reserve"); m.add_argument("--no-publish", action="store_true")
    r = sub.add_parser("rushs"); r.add_argument("mots"); r.add_argument("--voir", default=""); r.add_argument("--cadre", default="portrait", choices=["portrait", "paysage", "carre"])
    for name in ("demo", "bilan", "sujets", "veille", "stats", "plan"):
        sub.add_parser(name)
    d = sub.add_parser("doctor"); d.add_argument("--live", action="store_true", help="teste réellement les clés et rouvre les pages officielles")
    args = ap.parse_args()
    cfg = config.load()
    state = State(ROOT)
    return {"tick": cmd_tick, "make": cmd_make, "demo": cmd_demo, "bilan": cmd_bilan, "sujets": cmd_sujets, "rushs": cmd_rushs, "veille": cmd_veille,
            "stats": cmd_stats, "plan": cmd_plan, "doctor": cmd_doctor}[args.cmd](args, cfg, state)


if __name__ == "__main__":
    sys.exit(main())
