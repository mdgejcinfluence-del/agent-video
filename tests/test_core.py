"""Tests sans réseau : découpage du texte, réparation du storyboard, apprentissage du stratège.

    python -m unittest discover -s tests -v
"""
import json
import random
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from studio import align, schema, strategist  # noqa: E402
from studio.state import State, now  # noqa: E402


class Align(unittest.TestCase):
    def test_reperes(self):
        clean, toks, cues = align.parse_say("Tu crées [a1]un compte gratuit, [a2]sans carte.")
        self.assertEqual(clean, "Tu crées un compte gratuit, sans carte.")
        self.assertEqual(toks[cues["a1"]], "un")
        self.assertEqual(toks[cues["a2"]], "sans")

    def test_ponctuation_et_milliers(self):
        toks = align.tokens("à 68 000 étoiles : oui ? 0 €")
        self.assertEqual(toks, ["à", "68\u00a0000", "étoiles\u00a0:", "oui\u00a0?", "0\u00a0€"])

    def test_horodatage_avec_mots_fusionnes_et_prononciation(self):
        toks = align.tokens("tu as 40 requêtes sur GitHub.")
        spoken = [{"w": "tu", "t0": 0.0, "t1": 0.1}, {"w": "as", "t0": 0.1, "t1": 0.2}, {"w": "40 requêtes", "t0": 0.2, "t1": 0.9},
                  {"w": "sur", "t0": 0.9, "t1": 1.0}, {"w": "guite-heub", "t0": 1.0, "t1": 1.5}]
        times = align.map_times(toks, spoken, 1.6)
        self.assertEqual(len(times), len(toks))
        self.assertTrue(all(b[0] >= a[0] for a, b in zip(times, times[1:])), "les mots doivent rester dans l'ordre")
        self.assertAlmostEqual(times[2][0], 0.2, places=2)          # « 40 »
        self.assertTrue(1.0 <= times[5][0] <= 1.5)                  # « GitHub. » interpolé sur « guite-heub »

    def test_sous_titres_courts_sans_chevauchement(self):
        say = "Chez NVIDIA, tu crées un compte gratuit, sans carte bancaire, et tu as jusqu'à 40 requêtes par minute."
        _, toks, _ = align.parse_say(say)
        times = align.estimate_times(toks, 6.0)
        groups = align.group_captions(toks, times, {4}, 10.0)
        self.assertTrue(all(len(g["words"]) <= 4 for g in groups))
        self.assertEqual(sum(len(g["words"]) for g in groups), len(toks))
        self.assertTrue(any(w.get("hl") for g in groups for w in g["words"]))
        for g in groups:
            self.assertGreater(g["t1"], g["t0"])


class Schema(unittest.TestCase):
    def setUp(self):
        self.demo = json.loads((ROOT / "examples" / "demo_storyboard.json").read_text(encoding="utf-8"))

    def test_exemple_valide(self):
        st, notes = schema.check(self.demo, (28, 48))
        self.assertEqual(notes, [])
        self.assertEqual([s["type"] for s in st["scenes"]], ["hook", "section", "section", "section", "cta"])
        self.assertEqual(schema.numbers_in(st), {"1", "2", "3", "72000"})

    def test_reparations(self):
        d = json.loads(json.dumps(self.demo))
        d["scenes"][1]["title"] = "Un titre de section beaucoup trop long pour tenir à l'écran"
        d["scenes"][1]["blocks"][1]["rows"] += ["ligne 4", "ligne 5 en trop", "ligne 6 en trop"]
        d["scenes"][1]["blocks"].append({"id": "z", "kind": "hologramme", "text": "?"})
        d["scenes"][1]["say"] += " [zz9]mot"
        st, notes = schema.check(d, (28, 48))
        self.assertLessEqual(len(schema.plain(st["scenes"][1]["title"])), 28)
        self.assertEqual(len(st["scenes"][1]["blocks"][1]["rows"]), 4)
        self.assertTrue(all(b["kind"] != "hologramme" for b in st["scenes"][1]["blocks"]))
        self.assertNotIn("[zz9]", st["scenes"][1]["say"])
        self.assertTrue(notes)

    def test_rejets(self):
        d = json.loads(json.dumps(self.demo)); d["scenes"] = d["scenes"][:-1]
        with self.assertRaises(schema.StoryError):
            schema.check(d, None)
        d = json.loads(json.dumps(self.demo)); d["scenes"][0]["say"] = "Trop court."
        with self.assertRaises(schema.StoryError):
            schema.check(d, None)

    def test_nombres(self):
        txt = "- 40 requêtes par minute\n- 550 milliards\n- Étoiles GitHub : 147 942\n3. 68 000 étoiles, v26.0, 3,5 % et 1 250 000"
        self.assertEqual(schema.find_numbers(txt), {"40", "550", "147942", "3", "68000", "26", "3.5", "1250000"})

    def test_hauteur_limitee(self):
        d = json.loads(json.dumps(self.demo))
        d["scenes"][1]["blocks"] = [{"id": c, "kind": "checklist", "label": "X", "rows": ["a b", "c d", "e f", "g h"]} for c in "abc"]
        d["scenes"][1]["say"] = "Voici [a]une, [b]deux, [c]trois listes bien trop hautes pour un seul écran de téléphone."
        st, notes = schema.check(d, None)
        self.assertLess(sum(schema.block_height(b) + 26 for b in st["scenes"][1]["blocks"]), 801)
        self.assertTrue(any("plus de place" in n for n in notes))


class Stratege(unittest.TestCase):
    def _state(self):
        return State(Path(tempfile.mkdtemp()))

    def test_le_bandit_apprend(self):
        """Monde simulé : le format « tuto » fait 3x plus de vues et « soir » 2x. Le stratège doit le découvrir."""
        cfg = {"strategy": {"explore": 0.2, "formats": ["liste", "transforme", "tuto", "mythe", "comparatif"], "remake_every": 0},
               "offer": {"pitch_every": 0}, "stats": {"weights": {"views": 0.5, "comments": 0.2, "shares": 0.15, "saves": 0.15}},
               "schedule": {"slots": ["07:30", "12:30", "18:30", "20:30"], "videos_per_day": 2}}
        st = self._state(); rng = random.Random(7); world = random.Random(11)
        picks = []
        for i in range(120):
            slot = strategist.plan_day(st, cfg, f"2027-01-{i // 2:03d}", rng)["slots"][i % 2]
            b = strategist.sample_brief(st, cfg, rng, slot)
            views = 1000 * (3.0 if b["format"] == "tuto" else 1.0) * (2.0 if b["slot"] == "soir" else 1.0) * world.lognormvariate(0, 0.5)
            st.add_post({"id": f"p{i}", "created": now().isoformat(), "brief": b, "title": f"t{i}", "duration": 30,
                         "stats": {"tiktok": [{"h": 72, "views": int(views), "comments": int(views * 0.01), "shares": int(views * 0.01), "saves": int(views * 0.02)}]}})
            strategist.score_posts(st, cfg)
            picks.append(b)
        last = picks[-40:]
        share_tuto = sum(p["format"] == "tuto" for p in last) / len(last)
        share_soir = sum(p["slot"] == "soir" for p in last) / len(last)
        self.assertGreater(share_tuto, 0.5, f"« tuto » choisi seulement {share_tuto:.0%} du temps")
        self.assertGreater(share_soir, 0.4, f"« soir » choisi seulement {share_soir:.0%} du temps")
        first = picks[:20]
        self.assertGreater(len({p["format"] for p in first}), 2, "au début, le stratège doit explorer plusieurs formats")
        self.assertIn("tuto", strategist.memo(st))

    def test_score_centre_sur_la_mediane(self):
        cfg = {"stats": {}}
        st = self._state()
        for i, v in enumerate([100, 1000, 10000]):
            st.add_post({"id": f"p{i}", "created": now().isoformat(), "brief": {}, "stats": {"tiktok": [{"h": 30, "views": v, "comments": 10, "shares": 5, "saves": 5}]}})
        strategist.score_posts(st, cfg)
        s = [p["score"] for p in st.posts]
        self.assertLess(s[0], 0); self.assertGreater(s[2], 0)

    def test_nouveaute(self):
        st = self._state()
        cands = [{"id": "gh:a/b", "title": "Super outil motion", "facts": [], "source": "github", "stars": 5000, "kw": "x"},
                 {"id": "gh:c/d", "title": "Autre chose", "facts": [], "source": "github", "stars": 900, "kw": "x"}]
        strategist.mark_seen(st, [cands[0]], "Super outil motion")
        self.assertEqual([c["id"] for c in strategist.novelty_filter(cands, st)], ["gh:c/d"])

    def test_longueur_reelle(self):
        self.assertEqual([strategist.length_bucket(x) for x in (27.0, 35.9, 36.0, 47.0, 55.0)], ["court", "court", "moyen", "moyen", "moyen"])

    def test_video_d_offre_programmee(self):
        cfg = {"strategy": {"formats": ["liste"], "remake_every": 0}, "offer": {"pitch_every": 3, "name": "F", "points": ["a"]}}
        st = self._state(); rng = random.Random(1)
        fmts = []
        for i in range(9):
            b = strategist.sample_brief(st, cfg, rng, "18:30"); fmts.append(b["format"])
            st.add_post({"id": f"p{i}", "created": now().isoformat(), "brief": b})
        self.assertEqual([i for i, f in enumerate(fmts) if f == "offre"], [2, 5, 8])


class Son(unittest.TestCase):
    """Ce que personne n'écoute avant publication doit être vérifié par le calcul."""

    def test_mot_cle_detache_a_l_oral(self):
        from studio import voice
        self.assertEqual(voice.stress("Commente GRATUIT, et récupère-le.", "GRATUIT"), "Commente « GRATUIT », et récupère-le.")
        self.assertEqual(voice.stress('Commente "MOTION" maintenant', "MOTION"), "Commente « MOTION » maintenant")
        self.assertEqual(voice.stress("Commente « GRATUIT » ici", "GRATUIT"), "Commente « GRATUIT » ici")            # pas de double guillemet
        self.assertEqual(voice.stress("C'est gratuit. Commente gratuit.", "GRATUIT"), "C'est gratuit. Commente « GRATUIT ».")
        self.assertEqual(voice.stress("Commente SKILLS-PRO.", "SKILLS"), "Commente SKILLS-PRO.")                    # pas un mot entier
        self.assertEqual(voice.stress("Rien à détacher.", None), "Rien à détacher.")

    def test_marge_voix_sur_fond(self):
        import numpy as np
        from studio import mix
        sr = mix.SR
        t = np.arange(4 * sr) / sr
        parole = (np.sin(2 * np.pi * 2000 * t) * 0.2 * (np.sin(2 * np.pi * 2 * t) > 0)).astype(np.float32)     # « syllabes » à 2 kHz
        fond = (np.sin(2 * np.pi * 2500 * t) * 0.02).astype(np.float32)                                         # fond 20 dB plus bas
        calme = mix.clarity(parole, np.stack([fond, fond], axis=1))
        fort = mix.clarity(parole, np.stack([fond * 10, fond * 10], axis=1))                                    # fond au niveau de la voix
        self.assertAlmostEqual(calme["clarte_db"], 20.0, delta=1.5)
        self.assertAlmostEqual(fort["clarte_db"], 0.0, delta=1.5)
        self.assertGreater(fort["couvert"], 0.9)
        self.assertEqual(calme["couvert"], 0.0)
        grave = (np.sin(2 * np.pi * 80 * t) * 0.5).astype(np.float32)                                           # une basse forte ne gêne pas la parole
        self.assertGreater(mix.clarity(parole, np.stack([grave, grave], axis=1))["clarte_db"], 30)

    def test_le_ding_attend_la_fin_du_mot_cle(self):
        import numpy as np
        from studio import config, timeline, voice
        cfg = config.load()
        st, _ = schema.check(json.loads((ROOT / "examples" / "demo_storyboard.json").read_text(encoding="utf-8")), (20, 60))
        voices = []
        for sc in st["scenes"]:
            n = len(align.parse_say(sc["say"])[1])
            voices.append({"audio": np.zeros(int(0.4 * n * 48000), dtype=np.float32), "dur": 0.4 * n, "words": [], "provider": "test"})
        built = timeline.build(st, voices, cfg)
        gap = float(cfg.get("video", {}).get("scene_gap", 0.2))
        a0 = 0.05 + sum(v["dur"] + gap for v in voices[:-1])
        toks = align.parse_say(st["scenes"][-1]["say"])[1]
        idx = next(k for k, w in enumerate(toks) if align.norm(st["keyword"]) in align.norm(w))
        fin_mot = a0 + voice.word_times(toks, voices[-1])[idx][1]
        ding = [t for t, kind in built["sfx"] if kind == "ding"]
        self.assertEqual(len(ding), 1)
        self.assertGreaterEqual(ding[0], fin_mot)
        self.assertLess(ding[0], built["duration"] - 0.5)


class Ligne(unittest.TestCase):
    """Le métier : chaque vidéo parle de créer avec Claude et renvoie vers la formation en promo (lien en bio).
    Commenter ne fait rien recevoir : aucune vidéo ne doit promettre un envoi."""

    INTERDIT = ("guide", "en dm", "envoie", "reçois", "recevoir", "récupère", "gratuitement", "cadeau")

    def _story(self, kw="ROBOT", say="Tu veux le guide ? [kw]Commente ROBOT, et je te l'envoie en DM.", caption="Une vidéo utile. Commente ROBOT, le guide est sur le lien en bio."):
        return {"title": "T", "keyword": kw, "caption": caption, "scenes": [
            {"type": "hook", "title": "T", "say": "Une accroche courte ici."},
            {"type": "section", "title": "S", "blocks": [{"id": "a", "kind": "pill", "text": "x"}], "say": "Une [a]section courte ici."},
            {"type": "cta", "keyword": kw, "say": say}]}

    def test_fin_imposee_a_toutes_les_videos(self):
        from studio import writer
        st = writer.apply_cta(self._story(), {})
        cta = st["scenes"][-1]
        self.assertEqual(cta["say"], "Tu veux apprendre à le faire toi-même ? [kw]Commente ROBOT si tu veux la suite. "
                                     "[sub]La formation complète est en promo, lien en bio.")
        self.assertEqual(cta["sub"], "la formation est en promo, lien en bio")
        self.assertEqual(st["caption"], "Une vidéo utile. Commente ROBOT si tu veux la suite. La formation complète est en promo : lien en bio.")
        for mot in self.INTERDIT:
            self.assertNotIn(mot, (cta["say"] + " " + st["caption"]).lower())
        again = writer.apply_cta(json.loads(json.dumps(st)), {})
        self.assertEqual((again["scenes"][-1]["say"], again["caption"]), (cta["say"], st["caption"]), "appliquer deux fois ne change rien")

    def test_amorce_du_modele(self):
        from studio import writer
        keep = writer.apply_cta(self._story(say="Tu veux une vidéo comme celle-ci ?"), {})["scenes"][-1]["say"]
        self.assertTrue(keep.startswith("Tu veux une vidéo comme celle-ci ? [kw]Commente ROBOT si tu veux la suite."))
        # une amorce qui contient le mot-clé ferait apparaître le mot à l'écran trop tôt : elle est remplacée
        swap = writer.apply_cta(self._story(kw="CODE", say="Tu veux que Claude code pour toi ?"), {})["scenes"][-1]["say"]
        self.assertTrue(swap.startswith("Tu veux apprendre à le faire toi-même ? [kw]Commente CODE "))
        # réglages du fichier config.yaml
        cfg = {"offer": {"cta_comment": "pour la partie 2.", "cta_say": "Le lien est dans la bio", "cta_sub": "lien en bio", "caption_end": "Lien en bio"}}
        st = writer.apply_cta(self._story(), cfg)
        self.assertTrue(st["scenes"][-1]["say"].endswith("[kw]Commente ROBOT pour la partie 2. [sub]Le lien est dans la bio."))
        self.assertTrue(st["caption"].endswith("Commente ROBOT pour la partie 2. Lien en bio."))

    def test_reserve_dans_la_ligne(self):
        from studio import config, writer
        cfg = config.load()
        files = sorted((ROOT / "examples" / "evergreen").glob("*.json"))
        self.assertGreaterEqual(len(files), 3)
        mots = set()
        for f in files + [ROOT / "examples" / "demo_storyboard.json"]:
            raw = json.loads(f.read_text(encoding="utf-8"))
            st, notes = schema.check(raw, (20, 60))
            self.assertEqual(notes, [], f.name)
            ecrit = (st["scenes"][-1]["say"], st["scenes"][-1]["sub"], st["caption"])
            st = writer.apply_cta(st, cfg)
            self.assertEqual(ecrit, (st["scenes"][-1]["say"], st["scenes"][-1]["sub"], st["caption"]), f"{f.name} : la fin écrite n'est pas la fin imposée")
            texte = " ".join(s["say"] for s in st["scenes"]).lower() + " " + st["caption"].lower()
            self.assertIn("claude", texte, f.name)
            self.assertIn("lien en bio", st["scenes"][-1]["say"].lower(), f.name)
            for mot in self.INTERDIT:
                self.assertNotIn(mot, st["scenes"][-1]["say"].lower() + " " + st["caption"].lower(), f.name)
            if f.parent.name == "evergreen":
                self.assertNotIn(st["keyword"], mots, "deux vidéos de réserve ont le même mot-clé"); mots.add(st["keyword"])

    def test_filtre_de_veille(self):
        from studio import scout
        req = ["claude", "remotion", "coding agent", "agent skill"]
        self.assertFalse(scout.relevant("rustdesk/rustdesk", "An open-source remote desktop application", ["remote"], req))
        self.assertTrue(scout.relevant("remotion-dev/remotion", "Make videos programmatically with React", ["video"], req))
        self.assertTrue(scout.relevant("a/b", "Local video editor", ["claude-code", "ffmpeg"], req))
        self.assertTrue(scout.relevant("a/b", "Tools for any coding-agent", [], req))
        self.assertFalse(scout.relevant("a/b", "把书、长视频、播客等高价值内容蒸馏成可执行的 Agent Skills", ["claude-code"], req), "description illisible pour le scénariste")
        self.assertTrue(scout.relevant("a/b", "Anything", [], []), "sans mot exigé, tout passe")
        self.assertFalse(scout.relevant("a/b", "用 Claude Code Skills 做的视频剪辑 Agent", [], req), "description à moitié illisible")
        self.assertFalse(scout.relevant("a/claude-red", "Offensive security skills for Claude", [], req, ["security"]), "mot refusé")
        self.assertFalse(scout.relevant("a/b", "Remove AI watermarks from video, for Claude Code", [], req, ["watermark"]))


class Essai(unittest.TestCase):
    """Le mode essai fabrique la vidéo mais ne consomme rien ; la publication réelle sans destinataire échoue sans rien compter."""

    def setUp(self):
        import run
        from studio import config
        self.run = run
        self.state = State(Path(tempfile.mkdtemp()))
        self.cfg = config.load()
        self.cfg["llm"] = {**self.cfg["llm"], "providers": [], "keyless_fallback": False}
        self.saved = (run.candidates, run.produce.make_video, run.mediahost.publish, run.publish_all, run.log)
        run.candidates = lambda state, cfg: []
        run.log = lambda *_: None
        run.mediahost.publish = lambda *a, **k: None
        run.produce.make_video = lambda story, cfg, out, pid, log: {
            "story": story, "duration": 31.0, "words": 100, "video": "/tmp/x.mp4", "thumb": "/tmp/x.jpg", "thumb_ms": 0,
            "qa": {"ok": True, "problems": [], "warnings": []}}

    def tearDown(self):
        run = self.run
        run.candidates, run.produce.make_video, run.mediahost.publish, run.publish_all, run.log = self.saved

    def _seen(self):
        return self.state.load("seen", {"ids": [], "titles": []})["ids"]

    def test_l_essai_ne_consomme_rien_et_fait_tourner_la_reserve(self):
        self.cfg["publish"]["dry_run"] = True
        titres = [self.run.make_one(self.state, self.cfg, "18:30")["title"] for _ in range(4)]
        self.assertEqual(len(set(titres[:3])), 3, "les 3 vidéos de réserve passent tour à tour")
        self.assertEqual(titres[3], titres[0], "puis la boucle recommence, sans jamais tomber en panne")
        self.assertEqual(self.state.posts, [])
        self.assertEqual(self._seen(), [])
        self.assertEqual(self.state.load("essais", {})["n"], 4)

    def test_publication_reelle_sans_destinataire(self):
        self.cfg["publish"].update({"dry_run": False, "networks": ["tiktok"]})
        self.run.publish_all = lambda *a, **k: {"tiktok": {"status": "skipped", "error": "aucun accès configuré pour ce réseau"}}
        with self.assertRaises(RuntimeError):
            self.run.make_one(self.state, self.cfg, "18:30")
        self.assertEqual((self.state.posts, self._seen()), ([], []), "rien n'est compté : la vidéo de réserve reste disponible")

    def test_publication_reelle_reussie(self):
        self.cfg["publish"].update({"dry_run": False, "networks": ["tiktok"]})
        self.run.publish_all = lambda *a, **k: {"tiktok": {"status": "sent", "id": "1", "via": "buffer"}}
        a = self.run.make_one(self.state, self.cfg, "18:30")
        b = self.run.make_one(self.state, self.cfg, "18:30")
        self.assertNotEqual(a["title"], b["title"], "une vidéo de réserve ne sert qu'une fois")
        self.assertEqual(len(self.state.posts), 2)
        self.assertEqual(len(self._seen()), 2)


if __name__ == "__main__":
    unittest.main()
