#!/usr/bin/env python3
"""Agent autonome de vidéos « preuve à l'appui » — point d'entrée.

  python3 run.py tick              ce que le serveur lance à chaque réveil (mesures -> veille -> choix -> vidéo -> porte de publication)
  python3 run.py make              fabrique une vidéo tout de suite (--segment commercant|createur_freelance, --story fichier.json, --no-publish)
  python3 run.py demo              rend une vidéo d'exemple par public (aucune clé nécessaire, rien n'est publié)
  python3 run.py attente           liste les vidéos qui attendent ta validation
  python3 run.py valider ID|tout   publie une vidéo que tu as regardée et approuvée
  python3 run.py preuves           vérifie les dossiers de preuve (preuves/<id>/)
  python3 run.py sujets            la banque de 16 sujets, notée, avec ce qui manque pour les produire
  python3 run.py veille            rouvre les pages officielles et reconfirme les faits (prix, licences)
  python3 run.py stats             relève les mesures et recalcule les notes de qualité
  python3 run.py plan              le plan du jour, la prochaine vidéo de chaque série, ce que disent les mesures
  python3 run.py doctor            vérifie l'installation, les clés, les preuves et la porte de publication

Règle de l'agent : pas de preuve, pas de vidéo. Une vidéo ne montre que ce qui existe dans un dossier preuves/<id>/.

Mode essai (publish.dry_run: true, ou --no-publish) : la vidéo est fabriquée et contrôlée, rien n'est publié
et rien n'est « consommé » : tous les sujets restent disponibles pour le vrai lancement.
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
OUT = ROOT / "out"                      # vidéos, couvertures et fiches de production
sys.path.insert(0, str(ROOT))

from studio import config, fiche, llm, mediahost, notify, porte, preuves, produce, scout, stats, strategist, writer  # noqa: E402
from studio.config import secret  # noqa: E402
from studio.publish import caption_for, publish_all  # noqa: E402
from studio.state import State, now  # noqa: E402

LINES: list[str] = []
SEG_NAMES = {"commercant": "Commerçant", "createur_freelance": "Créateur"}


def log(msg: str) -> None:
    line = f"[{dt.datetime.now().strftime('%H:%M:%S')}] {msg}"
    LINES.append(line)
    print(line, flush=True)


def local_now(cfg: dict) -> dt.datetime:
    return dt.datetime.now(ZoneInfo((cfg.get("schedule") or {}).get("timezone", "UTC")))


def candidates(state: State, cfg: dict) -> list[dict]:
    """Actualité des outils (une seule série d'appels par jour). Ne sert qu'à noter la fraîcheur d'un sujet."""
    cache = state.load("candidates", {})
    today = now().strftime("%Y-%m-%d")
    if cache.get("date") == today and cache.get("items"):
        return cache["items"]
    try:
        items = scout.gather(cfg, log)
    except Exception as e:  # noqa: BLE001 — la veille des outils ne doit jamais empêcher de produire
        log(f"veille : actualité des outils indisponible ({type(e).__name__})")
        items = []
    if items:
        state.save("candidates", {"date": today, "items": items})
    return items or cache.get("items", [])


def veille(state: State, cfg: dict, force: bool = False) -> dict[str, dict]:
    """Veille du jour sur les faits (pages officielles), puis liste des faits utilisables aujourd'hui."""
    if (cfg.get("research") or {}).get("faits", True):
        try:
            scout.verifier_faits(ROOT, state, log, force=force)
        except Exception as e:  # noqa: BLE001
            log(f"veille : vérification des faits impossible ({type(e).__name__}: {str(e)[:120]})")
    return scout.faits_confirmes(ROOT, state)


def is_rehearsal(cfg: dict, publish: bool = True) -> bool:
    """Vrai tant que rien ne part sur les réseaux : réglage dry_run, ou vidéo demandée sans publication."""
    return (not publish) or bool((cfg.get("publish") or {}).get("dry_run", True))


def write_story(state: State, cfg: dict, choix: dict, pack: dict, faits: dict, brain, essai: bool) -> tuple[dict, str] | tuple[None, str]:
    """Écrit le storyboard ; bascule sur la réserve si aucun modèle ne répond. Renvoie (storyboard, origine)."""
    f = choix["fiche"]
    taken = {p.get("keyword") for p in state.posts + state.load("attente", [])}
    try:
        if not brain.available():
            raise RuntimeError("aucune clé de modèle configurée")
        refs = strategist.references(ROOT, f["segment"], f["n"])
        story = writer.write(brain, f, pack, faits, cfg, strategist.memo(state, ROOT, f["segment"]), log, taken=taken, refs=refs)
        return story, f"modèle {brain.used[-1] if brain.used else '?'}"
    except Exception as e:  # noqa: BLE001 — pas de cerveau disponible : storyboard de réserve
        log(f"scénariste : écriture par le modèle impossible ({type(e).__name__}: {str(e)[:200]})")
    days = int((cfg.get("strategy") or {}).get("repeat_days", 21))
    recent = set() if essai else {(b.get("sujet"), b.get("hook_type")) for b in strategist._used(state, days)}
    skip = {s["_reserve"] for s in writer.reserves(cfg) if (s.get("sujet"), s.get("hook_type")) in recent}
    st = writer.reserve_for(cfg, f["segment"], f["n"], pack["id"], f["hook_type"], skip=skip)
    if st is None:
        return None, "réserve épuisée"
    log(f"scénariste : storyboard de réserve « {st['_reserve']} »" + (" (essai : rien n'est consommé)" if essai else ""))
    return st, f"réserve {st['_reserve']}"


def _segment_auto(state: State, cfg: dict, when: dt.datetime, slot: str, essai: bool) -> str:
    plan = state.load("day", {}).get(when.strftime("%Y-%m-%d")) or {}
    if slot in (plan.get("segments") or {}):
        return plan["segments"][slot]
    if essai:
        return strategist.SEGMENTS[int(state.load("essais", {"n": 0}).get("n", 0)) % 2]
    return strategist.SEGMENTS[(len(state.posts) + len(state.load("attente", []))) % 2]


def _host(post_id: str, res: dict, cfg: dict, state: State) -> str | None:
    """Met la vidéo en ligne à une adresse publique (Buffer vient la chercher ; toi, tu peux la regarder)."""
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


def _send(post: dict, story: dict, video: str | None, public_url: str | None, cfg: dict, state: State) -> dict:
    post["published"] = publish_all(video, story, int(post.get("thumb_ms", 1500)), public_url, cfg, state, log)
    if not any(v.get("status") not in ("skipped", "error") for v in post["published"].values()):
        detail = " ; ".join(f"{n} : {v.get('error') or v.get('status')}" for n, v in post["published"].items()) or "aucun réseau dans publish.networks"
        raise RuntimeError(f"aucun réseau n'a reçu la vidéo ({detail[:220]})")
    state.add_post(post)
    state.log("video", id=post["id"], title=post["title"], published={k: v.get("status") for k, v in post["published"].items()})
    return post


def make_one(state: State, cfg: dict, slot: str, story: dict | None = None, publish: bool = True, segment: str | None = None,
             post_id: str | None = None) -> dict | None:
    """Fabrique une vidéo. Renvoie la fiche du post, ou None s'il n'y avait rien d'honnête à produire."""
    t0 = time.time()
    when = local_now(cfg)
    rng = random.Random(int(time.time()))
    essai = is_rehearsal(cfg, publish)
    brain = llm.Brain(cfg, state, log)
    faits = veille(state, cfg)
    items = candidates(state, cfg) if (cfg.get("research") or {}).get("github", True) else []
    choix, origine = None, "storyboard fourni à la main"
    if story is None:
        segment = segment or _segment_auto(state, cfg, when, slot, essai)
        choix = strategist.choisir(ROOT, state, cfg, segment, faits, rng, items, essai)
        if choix is None:
            log(f"stratège : rien à produire pour la série « {SEG_NAMES.get(segment, segment)} » — tous les sujets couverts par une preuve ont été traités "
                "récemment. Ajoute un dossier de preuve (preuves/LISEZMOI.md) : " + (strategist.manques(ROOT, state, faits) or ["—"])[0])
            state.log("rien", segment=segment)
            return None
        f = choix["fiche"]
        pack = preuves.charger(ROOT, f["preuve"])
        log(f"stratège : série « {SEG_NAMES.get(segment, segment)} », sujet n° {f['n']} « {f['sujet']} » (note {f['note']}/5), accroche « {choix['hook_type']} », "
            f"preuve « {pack['id']} » — {choix['pourquoi']}")
        suite = choix.get("suite")
        if not essai:
            pre = porte.bloquants(cfg, pack, None, suite)
            if pre:
                log("PUBLICATION SUSPENDUE — aucune vidéo fabriquée. Ce qui manque :")
                for k, b in enumerate(pre, 1):
                    log(f"  {k}. {b}")
                state.log("suspendu", segment=segment, sujet=f["n"], raisons=pre)
                return {"id": None, "qa": {"ok": True}, "suspendu": pre}
        story, origine = write_story(state, cfg, choix, pack, faits, brain, essai)
        if story is None:
            log(f"scénariste : aucun modèle disponible et plus de storyboard de réserve inédit pour la série « {SEG_NAMES.get(segment, segment)} » — "
                "ajoute une clé de modèle (NVIDIA_API_KEY ou GROQ_API_KEY) ou un dossier de preuve")
            return None
    else:
        pack = preuves.charger(ROOT, story.get("preuve"))
        segment = story.get("segment")
        other = strategist.choisir(ROOT, state, cfg, segment, faits, rng, items, essai) if segment in strategist.SEGMENTS else None
        suite = None
        if other:
            suite = other["suite"] if other["fiche"]["n"] == story.get("sujet") else {"n": other["fiche"]["n"], "sujet": other["fiche"]["sujet"]}
    reserve = story.pop("_reserve", None)
    stamp = when.strftime("%Y%m%d-%H%M")
    story, _notes = writer.controler(story, cfg, pack, faits, None)
    post_id = post_id or f"{stamp}-{story['keyword'].lower()}"
    out_dir = OUT
    res = produce.make_video(story, cfg, out_dir, post_id, log, pack=pack, faits=faits)
    story = res["story"]
    brief = {"segment": story["segment"], "sujet": story["sujet"], "hook_type": story["hook_type"], "preuve": pack["id"],
             "slot": strategist.slot_bucket(slot), "slot_exact": slot, "origine": origine.split(" ")[0], **({"reserve": reserve} if reserve else {})}
    refs = strategist.references(ROOT, story["segment"], story["sujet"])
    fp = fiche.ecrire(out_dir / f"{post_id}.md", story, pack, cfg, res, choix, faits, refs, suite, origine)
    log(f"fiche de production : {fp.name} (stratégie, sources, accroches, script minuté, storyboard, phrase de fin, packs par plateforme, contrôle)")
    post = {"id": post_id, "created": now().isoformat(timespec="seconds"), "slot": slot, "brief": brief, "title": story["title"],
            "keyword": story["keyword"], "duration": round(res["duration"], 1), "words": res["words"], "thumb_ms": res["thumb_ms"],
            "llm": brain.used[-1:] or ["aucun"], "why": (choix or {}).get("pourquoi", ""), "note": ((choix or {}).get("fiche") or {}).get("note"),
            "faits": story.get("faits") or [], "suite": suite,
            "qa": {"ok": res["qa"]["ok"], "problems": res["qa"]["problems"], "warnings": res["qa"]["warnings"]}, "published": {}, "stats": {}}
    blocs = porte.bloquants(cfg, pack, res["qa"], suite)
    if essai:
        # répétition générale : on montre ce qui se passerait, mais on ne retient rien (ni sujet, ni réserve, ni vidéo comptée)
        if blocs:
            log("porte de publication : en publication réelle, cette vidéo serait SUSPENDUE —")
            for k, b in enumerate(blocs, 1):
                log(f"  {k}. {b}")
        else:
            log("porte de publication : rien ne bloque" + (" ; il resterait ta validation" if porte.validation_requise(cfg) else ""))
        log("légende prévue (TikTok) :\n" + caption_for(story, cfg, "tiktok"))
        n = state.load("essais", {"n": 0}); n["n"] = int(n.get("n", 0)) + 1; state.save("essais", n)
        state.log("essai", id=post_id, title=story["title"], segment=story["segment"], sujet=story["sujet"], seconds=round(time.time() - t0),
                  qa=res["qa"]["ok"], reserve=reserve)
        log(f"MODE ESSAI — terminé en {time.time() - t0:.0f} s : « {story['title']} » ({post['duration']} s). Rien n'a été publié ni compté.")
        return post
    if blocs:
        log("PUBLICATION SUSPENDUE — la vidéo n'est pas publiée :")
        for k, b in enumerate(blocs, 1):
            log(f"  {k}. {b}")
        state.log("suspendu", id=post_id, raisons=blocs)
        return post
    public_url = _host(post_id, res, cfg, state)
    if public_url:
        log(f"hébergement : {public_url}")
    if porte.validation_requise(cfg):
        if not public_url:
            raise RuntimeError("la vidéo n'a pas pu être mise en ligne pour validation (hébergement indisponible)")
        wait = state.load("attente", [])
        wait.append({**post, "url": public_url, "story": story})
        state.save("attente", wait)
        state.log("attente", id=post_id, title=story["title"], url=public_url)
        log(f"EN ATTENTE DE TA VALIDATION — « {story['title']} » ({post['duration']} s)")
        log(f"  1. regarde : {public_url}")
        log(f"  2. relis la fiche de production (Artifacts de cette exécution : {post_id}.md)")
        log(f"  3. pour publier : onglet Actions > Agent vidéo > Run workflow > commande « valider », vidéo « {post_id} »")
        return post
    _send(post, story, res["video"], public_url, cfg, state)
    log(f"terminé en {time.time() - t0:.0f} s : « {story['title']} » ({post['duration']} s)")
    return post


def purge_attente(state: State, cfg: dict) -> list[dict]:
    """Abandonne les vidéos restées trop longtemps sans validation ; renvoie celles qui attendent encore."""
    days = int((cfg.get("publish") or {}).get("attente_jours", 7))
    wait = state.load("attente", [])
    keep = []
    for w in wait:
        try:
            old = (now() - dt.datetime.fromisoformat(w["created"])).days >= days
        except (KeyError, ValueError):
            old = True
        if old:
            log(f"validation : « {w.get('title', '')[:50]} » abandonnée (aucune validation en {days} jours)")
            state.log("abandon", id=w.get("id"))
        else:
            keep.append(w)
    if len(keep) != len(wait):
        state.save("attente", keep)
    return keep


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
            log(f"mesures : {n} relevé(s), notes de qualité recalculées")
    except Exception as e:  # noqa: BLE001 — les mesures ne doivent jamais empêcher de produire
        log(f"mesures : erreur ignorée ({type(e).__name__}: {str(e)[:160]})")
    wait = purge_attente(state, cfg)
    if wait:
        log(f"validation : {len(wait)} vidéo(s) attendent ton accord — " + ", ".join(w["id"] for w in wait))
    when = local_now(cfg)
    date = when.strftime("%Y-%m-%d")
    plan = strategist.plan_day(state, cfg, date, random.Random(when.strftime("%Y%m%d")))     # le plan du jour existe toujours
    slot = when.strftime("%H:%M") if args.force else due_slot(state, cfg, when)
    if not slot:
        veille(state, cfg)                       # la veille du jour a lieu même sans vidéo à produire
        log(f"aucun créneau à traiter maintenant ({when.strftime('%H:%M')} ; plan du jour : "
            + (", ".join(f"{s} {SEG_NAMES.get(plan['segments'].get(s), '')}" for s in plan["slots"]) or "pas de publication aujourd'hui") + ")")
        summary(cfg, notify_user=False)
        return 0
    days = state.load("day", {})
    # une vidéo forcée à la main s'ajoute au plan du jour sans le remplacer
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
    story = json.loads(Path(args.story).read_text(encoding="utf-8")) if args.story else None
    post = make_one(state, cfg, local_now(cfg).strftime("%H:%M"), story, publish=not args.no_publish, segment=args.segment)
    summary(cfg)
    return 0 if post is None or post["qa"]["ok"] else 1


def cmd_demo(args, cfg, state) -> int:
    """Une vidéo d'exemple par public (ou seulement --segment), à partir des storyboards de réserve. Rien n'est publié."""
    faits = scout.faits_confirmes(ROOT, state)
    ok = True
    for seg in ([args.segment] if args.segment else list(strategist.SEGMENTS)):
        st = writer.reserve_for(cfg, seg)
        if st is None:
            log(f"démo : aucun storyboard de réserve pour « {seg} »")
            ok = False
            continue
        name = st.pop("_reserve")
        pack = preuves.charger(ROOT, st["preuve"])
        res = produce.make_video(st, cfg, OUT, f"demo-{seg}", log, pack=pack, faits=faits)
        fiche.ecrire(OUT / f"demo-{seg}.md", res["story"], pack, cfg, res, None, faits,
                     strategist.references(ROOT, seg, res["story"]["sujet"]), None, f"réserve {name}")
        ok = ok and res["qa"]["ok"]
    return 0 if ok else 1


def cmd_attente(args, cfg, state) -> int:
    wait = purge_attente(state, cfg)
    if not wait:
        print("Aucune vidéo n'attend de validation.")
        return 0
    for w in wait:
        print(f"- {w['id']} — « {w.get('title')} » ({SEG_NAMES.get((w.get('brief') or {}).get('segment'), '?')}, {w.get('duration')} s)\n    regarder : {w.get('url')}")
    print("\nPour publier : python3 run.py valider <identifiant>   (ou : valider tout)")
    return 0


def cmd_valider(args, cfg, state) -> int:
    """Publie une vidéo en attente : c'est TA validation. Les autres conditions sont revérifiées au moment de publier."""
    wait = purge_attente(state, cfg)
    todo = wait if args.video.lower() in ("tout", "all") else [w for w in wait if w.get("id") == args.video]
    if not todo:
        log(f"validation : aucune vidéo en attente ne porte l'identifiant « {args.video} » (en attente : {', '.join(w['id'] for w in wait) or 'aucune'})")
        summary(cfg, notify_user=False)
        return 1
    if is_rehearsal(cfg):
        log("validation : publish.dry_run est à true — rien ne peut être publié en mode essai")
        summary(cfg, notify_user=False)
        return 1
    faits = veille(state, cfg)
    code = 0
    for w in todo:
        story = w["story"]
        try:
            pack = preuves.charger(ROOT, story["preuve"])
            writer.controler(story, cfg, pack, faits, None)                       # les faits cités sont-ils toujours confirmés aujourd'hui ?
            blocs = porte.bloquants(cfg, pack, w.get("qa"), w.get("suite"))
            if blocs:
                log(f"validation : « {w['title'][:50]} » reste SUSPENDUE — " + " ; ".join(blocs))
                code = 1
                continue
            video = OUT / f"{w['id']}.mp4"
            if not video.exists():
                import requests
                video.parent.mkdir(exist_ok=True)
                video.write_bytes(requests.get(w["url"], timeout=120).content)
            post = {k: v for k, v in w.items() if k not in ("story", "url")}
            post["validee_le"] = now().isoformat(timespec="seconds")
            _send(post, story, str(video), w["url"], cfg, state)
            state.save("attente", [x for x in state.load("attente", []) if x.get("id") != w["id"]])
            log(f"validation : « {w['title'][:50]} » publiée")
        except Exception as e:  # noqa: BLE001
            log(f"validation : « {w.get('title', '')[:50]} » non publiée ({type(e).__name__}: {str(e)[:240]})")
            code = 1
    summary(cfg)
    return code


def cmd_preuves(args, cfg, state) -> int:
    packs = preuves.tous(ROOT)
    if not packs:
        print("Aucun dossier de preuve. Lis preuves/LISEZMOI.md.")
        return 1
    bad = 0
    for pid, p in packs.items():
        pb = preuves.problemes(p)
        bad += bool(pb)
        if pb:
            print(f"❌ {pid}\n     " + "\n     ".join(pb))
            continue
        etat = "⚠️  exemple fictif (non publiable par défaut)" if p.get("fictif") else ("✅ réel, signé par " + str(p.get("valide_par")) if preuves.signee(p) else "⏳ réel, à signer (valide_par) avant publication")
        print(f"{etat} — {pid} [{SEG_NAMES.get(p.get('segment'))}] sujets {p.get('sujets')}\n     {p.get('titre')}\n     médias : {', '.join(p.get('media') or {})}")
    return 1 if bad else 0


def cmd_sujets(args, cfg, state) -> int:
    faits = scout.faits_confirmes(ROOT, state)
    rows = strategist.fiches(ROOT, state, faits, state.load("candidates", {}).get("items") or [])
    print("Note = problème 30 % + preuve 25 % + demande 20 % + adéquation 15 % + fraîcheur 10 % (outil de tri interne, pas une prévision).\n")
    print(f"{'n°':>2}  {'public':<10} {'thème':<9} {'note':>4}  pb pr de ad fr  preuve                     sujet")
    for f in rows:
        c = f["criteres"]
        print(f"{f['n']:>2}  {SEG_NAMES[f['segment']]:<10} {f['theme']:<9} {f['note']:>4.2f}  {c['probleme']:.0f}  {c['preuve']:.0f}  {c['demande']:.0f}  {c['formation']:.0f}  {c['fraicheur']:.0f}  "
              f"{(f['preuve'] or '— à fournir —'):<26} {f['sujet']}")
    miss = strategist.manques(ROOT, state, faits)
    print(f"\n{len(rows) - len(miss)} sujets sur {len(rows)} ont une preuve. Le signal de demande est inconnu partout tant que tu n'as rien mesuré ni saisi (data/sujets.yaml).")
    return 0


def cmd_veille(args, cfg, state) -> int:
    scout.verifier_faits(ROOT, state, log, force=True)
    ok = scout.faits_confirmes(ROOT, state)
    for fid, f in scout.charger_faits(ROOT)["faits"].items():
        print(f"  {'✅' if fid in ok else '⛔'} {fid} — {f['affirmation']}\n       {f['url']} (vérifié le {(ok.get(fid) or f).get('verifie_le')})")
    for ch in state.load("veille", {}).get("changements", [])[-5:]:
        print(f"  changement du {ch['le']} : {ch['detail']}")
    return 0


def cmd_stats(args, cfg, state) -> int:
    n = stats.collect(state, cfg, log)
    strategist.score_posts(state, cfg)
    log(f"{n} relevé(s)")
    print(strategist.memo(state, ROOT))
    return 0


def cmd_plan(args, cfg, state) -> int:
    when = local_now(cfg)
    plan = strategist.plan_day(state, cfg, when.strftime("%Y-%m-%d"), random.Random(when.strftime("%Y%m%d")))
    essai = is_rehearsal(cfg)
    print(f"Aujourd'hui ({when.strftime('%Y-%m-%d')}, {cfg['schedule']['timezone']}) — " + ("MODE ESSAI (rien n'est publié)" if essai else "publication réelle"))
    print("  créneaux : " + (", ".join(f"{s} → {SEG_NAMES.get(plan['segments'].get(s), '?')}" for s in plan["slots"]) or "aucun (jour sans publication)")
          + f" — faits : {plan['done'] or 'rien encore'}")
    faits = scout.faits_confirmes(ROOT, state)
    items = state.load("candidates", {}).get("items") or []
    print("\nProchaine vidéo de chaque série")
    for seg in strategist.SEGMENTS:
        c = strategist.choisir(ROOT, state, cfg, seg, faits, random.Random(0), items, essai)
        if not c:
            print(f"  {SEG_NAMES[seg]} : rien à produire (aucun sujet couvert par une preuve, ou tous traités récemment)")
            continue
        f = c["fiche"]
        pack = preuves.charger(ROOT, f["preuve"])
        blocs = porte.bloquants(cfg, pack, None, c.get("suite"))
        print(f"  {SEG_NAMES[seg]} : sujet n° {f['n']} « {f['sujet']} » — note {f['note']}/5, accroche « {c['hook_type']} », preuve « {f['preuve']} »")
        print(f"      pourquoi : {c['pourquoi']} ; thèmes ouverts : {', '.join(c['themes'])}")
        print(f"      la suite : " + (f"sujet n° {c['suite']['n']} « {c['suite']['sujet']} »" if c.get("suite") else "AUCUNE (la publication serait suspendue)"))
        print("      porte de publication : " + ("rien ne bloque" if not blocs else "SUSPENDUE — " + " | ".join(blocs)))
    wait = state.load("attente", [])
    print(f"\nEn attente de ta validation : {len(wait)}" + ("" if not wait else " — " + ", ".join(w["id"] for w in wait)))
    miss = strategist.manques(ROOT, state, faits)
    if miss:
        print(f"\nSujets sans preuve ({len(miss)}) — les 4 premiers :")
        for m in miss[:4]:
            print("  - " + m)
    print(f"\nVidéos publiées : {len(state.posts)} (dont notées : {sum(p.get('score') is not None for p in state.posts)})")
    print(strategist.memo(state, ROOT))
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
    print("Preuves et faits (pas de preuve, pas de vidéo)")
    packs = preuves.tous(ROOT)
    for pid, p in packs.items():
        pb = preuves.problemes(p)
        if pb:
            line(False, f"preuve {pid}", " ; ".join(pb))
        elif p.get("fictif"):
            line(None, f"preuve {pid}", "exemple fictif : sert aux essais, non publiable par défaut")
        else:
            line(True if preuves.signee(p) else None, f"preuve {pid}", f"signée par {p['valide_par']}" if preuves.signee(p) else "non signée (valide_par) : non publiable")
    faits = veille(state, cfg, force=args.live)
    allf = scout.charger_faits(ROOT)["faits"]
    line(len(faits) == len(allf), "faits vérifiés", f"{len(faits)}/{len(allf)} confirmés" + ("" if args.live else " (ajoute --live pour rouvrir les pages officielles)"))
    for st_ in writer.reserves(cfg):
        try:
            writer.controler(dict(st_), cfg, packs[st_["preuve"]], faits, None)
        except Exception as e:  # noqa: BLE001
            line(False, f"réserve {st_['_reserve']}", str(e)[:200])
    line(True, "storyboards de réserve", f"{len(writer.reserves(cfg))} contrôlés")
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
    print("Porte de publication")
    pcfg = cfg.get("publish") or {}
    line(None if pcfg.get("dry_run", True) else True, "mode", "ESSAI (dry_run: true) : rien n'est publié" if pcfg.get("dry_run", True) else "publication réelle")
    good, why = porte.promo_etat(cfg)
    line(True if good else None, "promotion de la phrase de fin", why)
    line(True if str((cfg.get("offer") or {}).get("lien_bio") or "").strip() else None, "page d'aiguillage (offer.lien_bio)",
         str((cfg.get("offer") or {}).get("lien_bio") or "non renseignée"))
    line(True, "validation", "chaque vidéo attend ton accord" if porte.validation_requise(cfg) else "déléguée : un dossier signé suffit")
    for seg in strategist.SEGMENTS:
        c = strategist.choisir(ROOT, state, cfg, seg, faits, random.Random(0), None, False)
        if c is None:
            line(None, f"série {SEG_NAMES[seg]}", "rien à produire")
        else:
            blocs = porte.bloquants(cfg, packs[c["fiche"]["preuve"]], None, c.get("suite"))
            line(True if not blocs else None, f"série {SEG_NAMES[seg]}", "publiable" if not blocs else f"{len(blocs)} condition(s) manquante(s) : " + " | ".join(blocs))
    print("Publication")
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
    if pcfg.get("media_host", "github_pages") == "cloudinary":
        has = bool(secret("CLOUDINARY_URL"))
        line(True if has else None, "hébergement des vidéos (Cloudinary)", "secret présent" if has else "secret CLOUDINARY_URL absent")
    elif not base:
        line(None, "hébergement des vidéos", "pas de dépôt GitHub détecté ici")
    elif not args.live:
        line(True, "hébergement des vidéos", base + " (ajoute --live pour le tester)")
    else:
        good, detail = mediahost.selftest(cfg, ROOT, int(pcfg.get("keep_videos", 30)))
        line(good, "hébergement des vidéos", detail)
    print("Quotas du jour : " + (json.dumps(state.load("quota", {}).get(now().strftime("%Y-%m-%d"), {}), ensure_ascii=False) or "{}"))
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("tick"); t.add_argument("--force", action="store_true", help="produit une vidéo maintenant, même hors créneau")
    m = sub.add_parser("make"); m.add_argument("--story"); m.add_argument("--no-publish", action="store_true")
    m.add_argument("--segment", choices=list(strategist.SEGMENTS))
    d0 = sub.add_parser("demo"); d0.add_argument("--segment", choices=list(strategist.SEGMENTS))
    v = sub.add_parser("valider"); v.add_argument("video", help="identifiant de la vidéo en attente, ou « tout »")
    for name in ("attente", "preuves", "sujets", "veille", "stats", "plan"):
        sub.add_parser(name)
    d = sub.add_parser("doctor"); d.add_argument("--live", action="store_true", help="teste réellement les clés et rouvre les pages officielles")
    args = ap.parse_args()
    cfg = config.load()
    state = State(ROOT)
    return {"tick": cmd_tick, "make": cmd_make, "demo": cmd_demo, "valider": cmd_valider, "attente": cmd_attente, "preuves": cmd_preuves,
            "sujets": cmd_sujets, "veille": cmd_veille, "stats": cmd_stats, "plan": cmd_plan, "doctor": cmd_doctor}[args.cmd](args, cfg, state)


if __name__ == "__main__":
    sys.exit(main())
