"""Tests sans réseau : texte, forme du storyboard, garde-fous de fond, phrase de fin, stratège, porte de publication.

    python -m unittest discover -s tests -v
"""
import copy
import datetime as dt
import json
import random
import sys
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from studio import align, config, fiche, garde, porte, preuves, schema, scout, strategist, writer  # noqa: E402
from studio.state import State, now  # noqa: E402

CTA = "Commente MOT si tu veux la suite. La formation complète est en promo, lien en bio."
JOUR = "2026-11-11"          # jour de la première vérification des faits (data/faits.yaml)


def reserve(name: str) -> dict:
    return json.loads((ROOT / "examples" / "reserve" / f"{name}.json").read_text(encoding="utf-8"))


def faits_du_jour() -> dict:
    return scout.faits_confirmes(ROOT, State(Path(tempfile.mkdtemp())), today=JOUR)


def pret(name: str, cfg: dict | None = None) -> tuple[dict, dict]:
    st = reserve(name)
    pack = preuves.charger(ROOT, st["preuve"])
    out, _ = writer.controler(st, cfg or config.load(), pack, faits_du_jour(), None)
    return out, pack


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


class Forme(unittest.TestCase):
    """Le fil d'une vidéo : résultat -> 3 étapes prouvées -> vérification et limite -> phrase de fin."""

    def test_reserves_valides(self):
        files = sorted((ROOT / "examples" / "reserve").glob("*.json"))
        self.assertGreaterEqual(len(files), 6)
        segs = set()
        for f in files:
            st, notes = schema.check(json.loads(f.read_text(encoding="utf-8")), (35, 45))
            self.assertEqual(notes, [], f.name)
            self.assertEqual([s["type"] for s in st["scenes"]], ["resultat", "etape", "etape", "etape", "verif", "cta"], f.name)
            self.assertTrue(st["scenes"][0]["visuel"], "la première image montre le résultat")
            self.assertEqual(len(st["hooks"]), 3, "trois accroches proposées, une retenue")
            segs.add(st["segment"])
        self.assertEqual(segs, {"commercant", "createur_freelance"})

    def test_reparations(self):
        st = reserve("c1_defaut_corrige")
        st["scenes"][0]["title"] = "Un titre beaucoup trop long pour tenir sur les deux lignes prévues à l'écran"
        st["scenes"][1]["say"] = "[z]" + st["scenes"][1]["say"]
        st["scenes"][2]["blocks"].append({"id": "c", "kind": "inconnu"})
        st["scenes"].append({"type": "cta", "say": "Abonne-toi et je t'envoie le guide !"})
        out, notes = schema.check(st)
        self.assertLessEqual(len(schema.plain(out["scenes"][0]["title"])), schema.LIMITS["title"])
        self.assertNotIn("[z]", out["scenes"][1]["say"])
        self.assertEqual(len(out["scenes"][2]["blocks"]), 2)
        self.assertEqual(len(out["scenes"]), 6)
        self.assertTrue(any("raccourci" in n for n in notes) and any("repères" in n for n in notes))

    def test_rejets(self):
        base = reserve("m1_photo_en_pub")
        cas = {
            "un seul public": lambda s: s.pop("segment"),
            "pas de preuve, pas de vidéo": lambda s: s.pop("preuve"),
            "trois étapes": lambda s: s["scenes"].pop(2),
            "le public est nommé": lambda s: s["scenes"][0].pop("public"),
            "le résultat à la première image": lambda s: s["scenes"][0].pop("visuel"),
            "une limite utile": lambda s: s["scenes"][4].pop("limite"),
            "la demande écrite apparaît": lambda s: s["scenes"][2].update(blocks=[{"id": "a", "kind": "note", "text": "Écris ton offre"}]),
        }
        for nom, casse in cas.items():
            st = copy.deepcopy(base)
            casse(st)
            with self.assertRaises(schema.StoryError, msg=nom):
                schema.check(st)

    def test_place_a_l_ecran(self):
        st = reserve("c2_charte_avant_la_demande")
        st["scenes"][2]["blocks"] += [{"id": "b", "kind": "media", "ref": "rendu"}, {"id": "c", "kind": "note", "text": "Une note en trop"}]
        out, notes = schema.check(st)
        self.assertLessEqual(len(out["scenes"][2]["blocks"]), 2, "deux blocs au plus par étape")
        self.assertTrue(any("plus de place" in n for n in notes))

    def test_nombres(self):
        self.assertEqual(schema.find_numbers("3 500 FCFA, 200 g, 3,5 % et 1080 px"), {"3500", "200", "3.5", "1080"})


class Garde(unittest.TestCase):
    """Ce qu'une vidéo n'a pas le droit de montrer ou de dire, d'où qu'elle vienne."""

    def setUp(self):
        self.cfg = config.load()
        self.faits = faits_du_jour()

    def refus(self, name: str, modif, attendu: str):
        st = reserve(name)
        modif(st)
        pack = preuves.charger(ROOT, st["preuve"])
        with self.assertRaises(schema.StoryError) as e:
            writer.controler(st, self.cfg, pack, self.faits, None)
        self.assertIn(attendu, str(e.exception))

    def test_toutes_les_reserves_passent(self):
        for f in sorted((ROOT / "examples" / "reserve").glob("*.json")):
            st, pack = pret(f.stem, self.cfg)
            self.assertEqual(garde.controle(st, pack, self.faits), [], f.name)

    def test_demande_citee_mot_pour_mot(self):
        def reformule(s):
            s["scenes"][2]["blocks"][0]["text"] = "Réduis un peu le titre pour qu'il rentre dans l'image."
            s["scenes"][2]["blocks"][0]["hl"] = []
        self.refus("c1_defaut_corrige", reformule, "introuvable mot pour mot")

    def test_code_cite_tel_quel(self):
        self.refus("c1_defaut_corrige", lambda s: s["scenes"][2]["blocks"][1]["lines"].__setitem__(1, "defaultProps={{ c: charte, taille: 150 }}"),
                   "code affiché introuvable")

    def test_media_inexistant(self):
        self.refus("c3_qui_fait_quoi", lambda s: s["scenes"][0].update(visuel={"ref": "capture_inventee"}), "absent du dossier de preuve")

    def test_chiffre_invente(self):
        self.refus("m1_photo_en_pub", lambda s: s["scenes"][4]["rows"].__setitem__(0, "Prix affiché : 2 900 FCFA"), "2900")
        self.refus("m1_photo_en_pub", lambda s: s["scenes"][3].update(say=s["scenes"][3]["say"] + " Prête en 2 minutes."), "refusée")
        self.refus("c3_qui_fait_quoi", lambda s: s["scenes"][3].update(say="[a]Remotion calcule 240 images et sort le MP4 en entier."), "240")

    def test_gratuit_seulement_avec_sa_precision(self):
        def sans_precision(s):
            s["scenes"][4]["limite"] = "Remotion est gratuit."
        self.refus("c3_qui_fait_quoi", sans_precision, "sans la précision")
        def sans_fait(s):
            s["faits"] = []
        self.refus("c3_qui_fait_quoi", sans_fait, "« gratuit »")

    def test_fait_non_confirme_par_la_veille(self):
        st = reserve("c3_qui_fait_quoi")
        pack = preuves.charger(ROOT, st["preuve"])
        with self.assertRaises(schema.StoryError) as e:
            writer.controler(st, self.cfg, pack, {}, None)                 # la veille n'a rien confirmé aujourd'hui
        self.assertIn("pas confirmé par la veille", str(e.exception))

    def test_promesses_refusees(self):
        for phrase, attendu in [("Tes ventes vont exploser.", "explose"), ("C'est garanti.", "garanti"), ("Plus besoin de monteur.", "monteur"),
                                ("Tu fais tout sans coder.", "sans coder"), ("Tu gagnes de l'argent avec ça.", "revenu"),
                                ("Commente et je t'envoie le fichier.", "envoi"), ("Clique sur le lien en bio.", "appel à l'action")]:
            self.refus("c2_charte_avant_la_demande", lambda s, p=phrase: s["scenes"][3].update(say=s["scenes"][3]["say"] + " " + p), attendu)

    def test_qui_fait_quoi(self):
        self.refus("c3_qui_fait_quoi", lambda s: s["scenes"][3].update(say="[a]Claude Code génère directement la vidéo et sort le MP4."), "confusion technique")

    def test_un_seul_public(self):
        def code_chez_le_commercant(s):
            s["scenes"][2]["blocks"].append({"id": "b", "kind": "code", "file": "src/Promo.tsx", "lines": ['const JAUNE = "#FFC83D";']})
        self.refus("m1_photo_en_pub", code_chez_le_commercant, "ni code ni terminal")
        self.refus("m1_photo_en_pub", lambda s: s["scenes"][0].update(say="Avec Remotion, cette photo devient une pub. [public]Si tu vends tes produits, regarde."),
                   "ne cite pas d'outil")
        self.refus("m1_photo_en_pub", lambda s: s.update(preuve="createur-intro-serie"), "public")

    def test_exemple_fictif_jamais_presente_comme_reel(self):
        self.refus("m3_trois_details", lambda s: s["scenes"][4].update(limite="C'est un vrai commerce de Cotonou."), "fictif")
        st, pack = pret("m3_trois_details", self.cfg)
        self.assertTrue(pack["fictif"])


class PhraseDeFin(unittest.TestCase):
    """La phrase imposée : dite et écrite mot pour mot, identique pour les deux publics, jamais laissée au modèle."""

    def setUp(self):
        self.cfg = config.load()

    def test_reglage_par_defaut(self):
        self.assertEqual(self.cfg["offer"]["cta"], CTA)
        self.assertEqual(writer.CTA, CTA)

    def test_meme_fin_pour_les_deux_publics(self):
        fins = set()
        for name in ("c1_defaut_corrige", "m1_photo_en_pub"):
            st, _ = pret(name, self.cfg)
            cta = st["scenes"][-1]
            dit = " ".join(align.parse_say(cta["say"])[1]).replace("\u00a0", " ")
            self.assertEqual(dit, CTA.replace("MOT", st["keyword"]), "aucune amorce, aucun ajout, aucun mot en moins")
            self.assertEqual(f"{cta['verb']} {cta['keyword']} {cta['l2']} {cta['l3']}", CTA.replace("MOT", st["keyword"]), "l'écran affiche la phrase entière")
            self.assertTrue(st["caption"].endswith(CTA.replace("MOT", st["keyword"])))
            fins.add(dit.replace(st["keyword"], "MOT"))
        self.assertEqual(fins, {CTA})

    def test_le_modele_ne_peut_pas_la_changer(self):
        st = reserve("c1_defaut_corrige")
        st["scenes"].append({"type": "cta", "say": "Commente RENDU et je t'envoie mon guide en message privé !", "sub": "guide offert"})
        st["caption"] = "Un rendu corrigé. Commente RENDU pour recevoir le guide. Lien en bio !"
        pack = preuves.charger(ROOT, st["preuve"])
        out, _ = writer.controler(st, self.cfg, pack, faits_du_jour(), None)
        self.assertNotIn("guide", json.dumps(out["scenes"][-1], ensure_ascii=False))
        self.assertEqual(out["caption"], "Un rendu corrigé. " + CTA.replace("MOT", "RENDU"))
        again, _ = writer.controler(out, self.cfg, pack, faits_du_jour(), None)
        self.assertEqual(again["caption"], out["caption"], "appliquer deux fois ne change rien")

    def test_mot_fixe(self):
        cfg = copy.deepcopy(self.cfg)
        cfg["offer"]["cta_mot_fixe"] = "suite"
        st, _ = pret("m1_photo_en_pub", cfg)
        self.assertEqual(st["keyword"], "SUITE")
        self.assertIn("Commente SUITE si tu veux la suite.", st["caption"])

    def test_phrase_sans_mot_refusee(self):
        cfg = copy.deepcopy(self.cfg)
        cfg["offer"]["cta"] = "Abonne-toi."
        with self.assertRaises(ValueError):
            writer.cta_template(cfg)


class Preuves(unittest.TestCase):
    def test_dossiers_utilisables(self):
        packs = preuves.tous(ROOT)
        self.assertEqual({p["segment"] for p in packs.values()}, {"commercant", "createur_freelance"})
        for pid, p in packs.items():
            self.assertEqual(preuves.problemes(p), [], pid)
        self.assertTrue(packs["commerce-karite-exemple"]["fictif"], "l'exemple de commerce est étiqueté fictif")
        self.assertEqual(preuves.note(packs["commerce-karite-exemple"]), 2)

    def test_mot_pour_mot(self):
        p = preuves.charger(ROOT, "createur-intro-serie")
        self.assertEqual(preuves.extrait_ok(p, "Mouvement : entrées en ressort, jamais linéaires."), "demande")
        self.assertEqual(preuves.extrait_ok(p, "Réduis le titre pour qu'il tienne dans le cadre"), "correction")
        self.assertEqual(preuves.extrait_ok(p, "Crée une intro … Termine par une barre de progression qui se remplit."), "demande")
        self.assertIsNone(preuves.extrait_ok(p, "Fais une vidéo virale"))
        self.assertEqual(preuves.code_faux(p, "src/charte.ts", ['police: "Inter Tight",']), [])
        self.assertTrue(preuves.code_faux(p, "src/charte.ts", ['police: "Comic Sans",']))
        self.assertTrue(preuves.code_faux(p, "src/absent.ts", ["x"]))

    def test_dossier_incomplet(self):
        p = preuves.charger(ROOT, "commerce-karite-exemple")
        p["offre"] = {"produit": "Beurre"}
        p["media"]["rendu"]["fichier"] = "media/absent.mp4"
        pb = " ".join(preuves.problemes(p))
        self.assertIn("offre.prix", pb)
        self.assertIn("introuvable", pb)
        self.assertEqual(preuves.note(p), 0)


class Veille(unittest.TestCase):
    """Chaque jour, la page officielle est rouverte : un fait qui a disparu de sa page n'est plus utilisable."""

    def test_changement_detecte(self):
        state = State(Path(tempfile.mkdtemp()))
        logs = []
        ok_page = lambda url: (200, "For individuals and companies of up to 3 people … $25/mo per seat … $0.01 per render, $100/mo minimum … "
                                    "give you a frame number and a blank canvas … Claude Code … Node.js … is 4 or more … not open-source software")
        scout.verifier_faits(ROOT, state, logs.append, force=True, fetch=ok_page)
        self.assertEqual(len(scout.faits_confirmes(ROOT, state)), 6)
        moved = lambda url: (200, "New pricing: free for teams of up to 5 people. " + ok_page(url)[1].replace("For individuals and companies of up to 3 people", ""))
        scout.verifier_faits(ROOT, state, logs.append, force=True, fetch=moved)
        left = scout.faits_confirmes(ROOT, state)
        self.assertNotIn("remotion-licence-gratuite", left)
        self.assertIn("remotion-licence-createurs", left)
        self.assertTrue(any("CHANGEMENT" in x for x in logs))
        self.assertEqual(state.load("veille", {})["changements"][-1]["fait"], "remotion-licence-gratuite")

    def test_fait_trop_ancien(self):
        state = State(Path(tempfile.mkdtemp()))
        self.assertEqual(len(scout.faits_confirmes(ROOT, state, today=JOUR)), 6)
        self.assertEqual(scout.faits_confirmes(ROOT, state, today="2026-12-25"), {}, "sans nouvelle vérification, un fait n'est plus cité")

    def test_page_injoignable(self):
        state = State(Path(tempfile.mkdtemp()))
        def panne(url):
            raise OSError("réseau")
        scout.verifier_faits(ROOT, state, lambda *_: None, force=True, fetch=panne)
        self.assertEqual(state.load("veille", {})["faits"], {}, "une panne de réseau ne confirme ni ne suspend rien")


class Stratege(unittest.TestCase):
    def setUp(self):
        self.state = State(Path(tempfile.mkdtemp()))
        self.cfg = config.load()
        self.faits = faits_du_jour()

    def publie(self, seg, n, hook, score=None, net="tiktok", jours=1):
        at = (now() - dt.timedelta(days=jours)).isoformat(timespec="seconds")
        p = {"id": f"p{len(self.state.posts)}", "created": at, "title": f"v{n}", "duration": 40, "brief": {"segment": seg, "sujet": n, "hook_type": hook}}
        if score is not None:
            p["score"] = score
        self.state.add_post(p)
        return p

    def test_ponderation_de_la_fiche_sujet(self):
        bq = strategist.banque(ROOT)
        self.assertEqual(len(bq["sujets"]), 16)
        self.assertAlmostEqual(sum(bq["poids"].values()), 1.0)
        self.assertEqual({k: round(v * 100) for k, v in bq["poids"].items()}, {"probleme": 30, "preuve": 25, "demande": 20, "formation": 15, "fraicheur": 10})
        f = {x["n"]: x for x in strategist.fiches(ROOT, self.state, self.faits)}
        c = f[5]["criteres"]
        self.assertAlmostEqual(f[5]["note"], 0.30 * c["probleme"] + 0.25 * c["preuve"] + 0.20 * c["demande"] + 0.15 * c["formation"] + 0.10 * c["fraicheur"], places=2)
        self.assertEqual(c["demande"], 0, "sans signal vérifiable, la demande vaut 0 et la fiche le dit")
        self.assertTrue(any("inconnue" in x for x in f[5]["confiance"]))

    def test_pas_de_preuve_pas_de_video(self):
        f = {x["n"]: x for x in strategist.fiches(ROOT, self.state, self.faits)}
        self.assertIsNone(f[9]["preuve"])
        for seg in strategist.SEGMENTS:
            for seed in range(8):
                c = strategist.choisir(ROOT, self.state, self.cfg, seg, self.faits, random.Random(seed))
                self.assertIsNotNone(f[c["fiche"]["n"]]["preuve"])
                self.assertEqual(c["fiche"]["segment"], seg)
        self.assertEqual(len(strategist.manques(ROOT, self.state, self.faits)), 10)

    def test_les_deux_series_alternent(self):
        plan = strategist.plan_day(self.state, self.cfg, "2026-11-12", random.Random(1))
        self.assertEqual(sorted(plan["segments"].values()), ["commercant", "createur_freelance"], "chaque jour sert les deux publics")
        plan2 = strategist.plan_day(self.state, self.cfg, "2026-11-13", random.Random(1))
        self.assertNotEqual(plan["segments"][plan["slots"][0]], plan2["segments"][plan2["slots"][0]], "le public qui ouvre la journée change")

    def test_jours_sans_publication(self):
        cfg = copy.deepcopy(self.cfg)
        cfg["schedule"]["jours"] = [1, 2, 4, 5]
        self.assertEqual(strategist.plan_day(self.state, cfg, "2026-11-11", random.Random(1))["slots"], [], "mercredi : pas de vidéo")
        self.assertEqual(len(strategist.plan_day(self.state, cfg, "2026-11-12", random.Random(1))["slots"]), 2)

    def test_ordre_de_lancement_et_suite(self):
        c = strategist.choisir(ROOT, self.state, self.cfg, "commercant", self.faits, random.Random(0))
        self.assertEqual(c["fiche"]["n"], 5, "on commence par le motion design")
        self.assertEqual(c["themes"], ["motion"])
        self.assertEqual(c["suite"]["n"], 6, "la suite promise est la vidéo suivante de la série")

    def test_un_seul_facteur_change(self):
        vus = []
        for i in range(9):
            c = strategist.choisir(ROOT, self.state, self.cfg, "commercant", self.faits, random.Random(i))
            vus.append((c["fiche"]["n"], c["hook_type"], c["fiche"]["preuve"]))
            self.publie("commercant", c["fiche"]["n"], c["hook_type"])
        self.assertEqual([n for n, _h, _p in vus[:3]], [5, 6, 12], "d'abord chaque sujet une fois")
        self.assertEqual(len(set(vus)), 9, "jamais deux fois le même sujet avec la même accroche")
        self.assertEqual(len({p for _n, _h, p in vus}), 1, "la preuve reste la même : seule l'accroche change")
        self.assertIsNone(strategist.choisir(ROOT, self.state, self.cfg, "commercant", self.faits, random.Random(0)), "plus rien d'honnête à produire")

    def test_les_vues_seules_ne_designent_pas_une_gagnante(self):
        def snap(views, **kw):
            return [{"h": 30, "views": views, **kw}]
        rows = [("a", 100000, dict(shares=10, saves=10, comments=10, watch=8)), ("b", 1000, dict(shares=10, saves=10, comments=10, watch=30)),
                ("c", 1000, dict(shares=1, saves=1, comments=1, watch=15)), ("d", 1000, dict(shares=2, saves=2, comments=2, watch=16))]
        for pid, views, m in rows:
            p = self.publie("commercant", 5, "resultat")
            p["id"] = pid
            p["stats"] = {"tiktok": snap(views, **m)}
        seul = self.publie("createur_freelance", 1, "resultat")
        seul["stats"] = {"tiktok": snap(999999, shares=9999, saves=9999, comments=9999, watch=39)}
        strategist.score_posts(self.state, self.cfg)
        s = {p["id"]: p.get("score") for p in self.state.posts}
        self.assertGreater(s["b"], s["a"], "100 fois plus de vues, mais regardée 4 fois moins longtemps et moins partagée en proportion")
        self.assertIsNone(s[seul["id"]], "pas de note sans 3 vidéos du même public sur le même réseau")
        self.assertIn("Clics sur le lien et ventes : non renseignés", strategist.memo(self.state, ROOT))


class Porte(unittest.TestCase):
    """Ce qui doit être vrai avant qu'une vidéo parte : la machine prépare, une personne valide."""

    def setUp(self):
        self.cfg = config.load()
        self.reel = preuves.charger(ROOT, "createur-intro-serie")
        self.fictif = preuves.charger(ROOT, "commerce-karite-exemple")
        self.suite = {"n": 2, "sujet": "…"}
        self.ok_qa = {"ok": True, "problems": []}

    def pret(self):
        cfg = copy.deepcopy(self.cfg)
        cfg["offer"].update({"lien_bio": "https://exemple.com/choisir", "promo": {"confirmee": True, "jusquau": "2026-12-31"}})
        return cfg, {**self.reel, "valide_par": "Moi", "valide_le": JOUR}

    def test_reglages_de_depart(self):
        self.assertTrue(self.cfg["publish"]["dry_run"])
        self.assertTrue(porte.validation_requise(self.cfg))
        blocs = " | ".join(porte.bloquants(self.cfg, self.reel, self.ok_qa, self.suite, dt.date(2026, 11, 11)))
        for attendu in ("n'est pas signé", "promotion non confirmée", "page d'aiguillage"):
            self.assertIn(attendu, blocs)

    def test_tout_est_vrai(self):
        cfg, pack = self.pret()
        self.assertEqual(porte.bloquants(cfg, pack, self.ok_qa, self.suite, dt.date(2026, 11, 20)), [])

    def test_chaque_condition_bloque(self):
        cfg, pack = self.pret()
        today = dt.date(2026, 11, 20)
        self.assertIn("promotion terminée", " ".join(porte.bloquants(cfg, pack, self.ok_qa, self.suite, dt.date(2027, 1, 1))))
        self.assertIn("aucune suite", " ".join(porte.bloquants(cfg, pack, self.ok_qa, None, today)))
        self.assertIn("contrôle qualité", " ".join(porte.bloquants(cfg, pack, {"ok": False, "problems": ["x"]}, self.suite, today)))
        self.assertIn("exemple fictif", " ".join(porte.bloquants(cfg, {**self.fictif, "valide_par": "Moi"}, self.ok_qa, self.suite, today)))
        cfg["publish"]["exemples_fictifs"] = True
        self.assertEqual(porte.bloquants(cfg, {**self.fictif, "valide_par": "Moi"}, self.ok_qa, self.suite, today), [])
        cfg["offer"]["promo"]["jusquau"] = ""
        self.assertIn("date de fin", " ".join(porte.bloquants(cfg, pack, self.ok_qa, self.suite, today)))


class Fiche(unittest.TestCase):
    def test_les_neuf_elements_dans_l_ordre(self):
        cfg = config.load()
        st, pack = pret("m1_photo_en_pub", cfg)
        res = {"video": "/tmp/x.mp4", "duration": 38.2, "words": 109, "voice": ["edge"], "voice_rate": "+10%", "layout": {"warnings": []},
               "audio": {"lufs": -14.1, "clarte_db": 21.0}, "qa": {"ok": True, "problems": [], "warnings": []},
               "scenes": [{"type": s["type"], "t0": i * 6.0, "t1": i * 6.0 + 6, "mots": 17} for i, s in enumerate(st["scenes"])]}
        state = State(Path(tempfile.mkdtemp()))
        choix = strategist.choisir(ROOT, state, cfg, "commercant", faits_du_jour(), random.Random(0))
        out = fiche.ecrire(Path(tempfile.mkdtemp()) / "f.md", st, pack, cfg, res, choix, faits_du_jour(),
                           strategist.references(ROOT, "commercant", 5), choix["suite"], "réserve m1").read_text(encoding="utf-8")
        titres = ["## 1. Fiche stratégie", "## 2. Sources et veille", "## 3. Références publiques observées", "## 4. Trois accroches, une choisie",
                  "## 5. Script minuté", "## 6. Storyboard", "## 7. Phrase de fin", "## 8. Pack de publication par plateforme", "## 9. Contrôle avant publication"]
        pos = [out.index(t) for t in titres]
        self.assertEqual(pos, sorted(pos))
        self.assertIn("> " + CTA.replace("MOT", "PHOTO"), out)
        for plateforme in ("### TikTok", "### Instagram Reels", "### YouTube Shorts", "### Facebook Reels"):
            self.assertIn(plateforme, out)
        packs_ = out[out.index("## 8."):out.index("## 9.")]
        self.assertEqual(packs_.count(CTA.replace("MOT", "PHOTO")), 4, "la même phrase, mot pour mot, dans les 4 légendes")
        self.assertIn("Exemple fictif", out)
        self.assertIn("Publication : SUSPENDUE", out)
        self.assertIn("demande : inconnue", out)
        self.assertIn("Aucun chiffre de marché, de vues ou de ventes", out)


class Son(unittest.TestCase):
    """Ce que personne n'écoute avant publication doit être vérifié par le calcul."""

    def test_mot_cle_detache_a_l_oral(self):
        from studio import voice
        self.assertEqual(voice.stress('Commente "MOTION" maintenant', "MOTION"), "Commente « MOTION » maintenant")
        self.assertEqual(voice.stress("Commente RENDU si tu veux la suite.", "RENDU"), "Commente « RENDU » si tu veux la suite.")
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

    def _timeline(self, name):
        import numpy as np
        from studio import timeline
        cfg = config.load()
        st, pack = pret(name, cfg)
        voices = []
        for sc in st["scenes"]:
            n = len(align.parse_say(sc["say"])[1])
            voices.append({"audio": np.zeros(int(0.4 * n * 48000), dtype=np.float32), "dur": 0.4 * n, "words": [], "provider": "test"})
        media = {r: {"kind": "image", "srcs": ["x"], "w": 1080, "h": 1920, **({"zone": m["zone"]} if m.get("zone") else {})} for r, m in pack["media"].items()}
        return cfg, st, voices, timeline.build(st, voices, cfg, media, fictif=bool(pack.get("fictif")))

    def test_le_ding_attend_la_fin_du_mot_cle(self):
        from studio import voice
        cfg, st, voices, built = self._timeline("c1_defaut_corrige")
        gap = float(cfg.get("video", {}).get("scene_gap", 0.2))
        a0 = 0.05 + sum(v["dur"] + gap for v in voices[:-1])
        toks = align.parse_say(st["scenes"][-1]["say"])[1]
        idx = next(k for k, w in enumerate(toks) if align.norm(st["keyword"]) == align.norm(w))
        fin_mot = a0 + voice.word_times(toks, voices[-1])[idx][1]
        ding = [t for t, kind in built["sfx"] if kind == "ding"]
        self.assertEqual(len(ding), 1)
        self.assertGreaterEqual(ding[0], fin_mot)
        self.assertLess(ding[0], built["duration"] - 0.5)

    def test_timeline_dans_l_ordre(self):
        for name in ("c1_defaut_corrige", "m2_produit_visible"):
            _cfg, st, _v, built = self._timeline(name)
            tl = built["timeline"]
            self.assertEqual(tl["scenes"][0]["t0"], 0.0)
            self.assertEqual(tl["fictif"], "Exemple fictif" if st["segment"] == "commercant" else "", "l'étiquette vient du dossier, pas du storyboard")
            self.assertNotEqual(tl["theme"]["bg"], "", "chaque série a ses couleurs")
            for s in tl["scenes"]:
                self.assertLess(s["t0"], s["t1"])
                for b in s.get("blocks", []):
                    self.assertTrue(s["t0"] <= b["at"] <= s["t1"], "un bloc apparaît pendant sa scène")
                    if b["kind"] == "erreur":
                        self.assertTrue(b["zone"] and b["at"] < b["zoneAt"] <= s["t1"])
            cta = tl["scenes"][-1]
            self.assertTrue(cta["kwAt"] < cta["l2At"] < cta["subAt"] < cta["t1"])
            caps = tl["captions"]
            self.assertTrue(all(b["t0"] >= a["t1"] for a, b in zip(caps, caps[1:])), "les sous-titres ne se chevauchent pas")
        themes = {self._timeline(n)[3]["timeline"]["theme"]["bg"] for n in ("c1_defaut_corrige", "m2_produit_visible")}
        self.assertEqual(len(themes), 2, "les deux séries se distinguent à l'œil")


class Parcours(unittest.TestCase):
    """De bout en bout, sans rendu : essai, suspension, attente de validation, publication."""

    def setUp(self):
        import run
        self.run = run
        self.state = State(Path(tempfile.mkdtemp()))
        self.cfg = config.load()
        self.cfg["llm"] = {**self.cfg["llm"], "providers": [], "keyless_fallback": False}
        self.cfg["research"] = {**self.cfg["research"], "github": False}
        self.saved = {k: getattr(run, k) for k in ("candidates", "veille", "log", "_host", "publish_all", "OUT")}
        run.OUT = Path(tempfile.mkdtemp())          # les tests n'écrivent jamais dans le dossier out/ du dépôt
        self.saved_mod = (run.produce.make_video, run.fiche.ecrire, run.preuves.charger)
        self.rendus = []
        faits = faits_du_jour()
        run.candidates = lambda state, cfg: []
        run.veille = lambda state, cfg, force=False: faits
        run.log = lambda *_: None
        run._host = lambda post_id, res, cfg, state: f"https://exemple.com/v/{post_id}.mp4"
        run.fiche.ecrire = lambda path, *a, **k: Path(path)

        def faux_rendu(story, cfg, out, pid, log, pack=None, faits=None):
            self.rendus.append(pid)
            return {"story": story, "duration": 38.0, "words": 105, "video": "/tmp/x.mp4", "thumb": "/tmp/x.jpg", "thumb_ms": 0,
                    "qa": {"ok": True, "problems": [], "warnings": []}}
        run.produce.make_video = faux_rendu

    def tearDown(self):
        run = self.run
        for k, v in self.saved.items():
            setattr(run, k, v)
        run.produce.make_video, run.fiche.ecrire, run.preuves.charger = self.saved_mod

    def pret_a_publier(self, validation):
        self.cfg["publish"].update({"dry_run": False, "networks": ["tiktok"], "validation": validation, "exemples_fictifs": True})
        self.cfg["offer"].update({"lien_bio": "https://exemple.com/choisir", "promo": {"confirmee": True, "jusquau": "2099-12-31"}})
        vrai = self.saved_mod[2]
        self.run.preuves.charger = lambda root, pid: {**vrai(root, pid), "valide_par": "Moi", "valide_le": JOUR}
        self.run.publish_all = lambda *a, **k: {"tiktok": {"status": "sent", "id": "1", "via": "buffer"}}

    def test_l_essai_ne_consomme_rien_et_montre_les_deux_series(self):
        self.cfg["publish"]["dry_run"] = True
        posts = [self.run.make_one(self.state, self.cfg, "18:30") for _ in range(7)]
        segs = [p["brief"]["segment"] for p in posts]
        self.assertEqual(segs[:6], ["commercant", "createur_freelance"] * 3, "les deux séries alternent")
        self.assertEqual(len({p["title"] for p in posts[:6]}), 6, "les 6 vidéos de réserve passent tour à tour")
        self.assertEqual(posts[6]["title"], posts[0]["title"], "puis la boucle recommence")
        self.assertEqual((self.state.posts, self.state.load("attente", [])), ([], []))
        self.assertEqual(self.state.load("essais", {})["n"], 7)

    def test_publication_suspendue_tant_que_rien_n_est_confirme(self):
        self.cfg["publish"]["dry_run"] = False
        out = self.run.make_one(self.state, self.cfg, "18:30", segment="createur_freelance")
        self.assertIn("n'est pas signé", " ".join(out["suspendu"]))
        self.assertEqual(self.rendus, [], "aucune vidéo n'est fabriquée pour rien")
        self.assertEqual((self.state.posts, self.state.load("attente", [])), ([], []))

    def test_chaque_video_attend_la_validation(self):
        self.pret_a_publier("chaque_video")
        envoye = []
        self.run.publish_all = lambda *a, **k: envoye.append(1) or {"tiktok": {"status": "sent", "id": "1", "via": "buffer"}}
        post = self.run.make_one(self.state, self.cfg, "18:30", segment="createur_freelance")
        self.assertEqual(envoye, [], "rien ne part sans ton accord")
        wait = self.state.load("attente", [])
        self.assertEqual([w["id"] for w in wait], [post["id"]])
        self.assertTrue(wait[0]["url"].endswith(".mp4") and wait[0]["story"]["scenes"])
        autre = self.run.make_one(self.state, self.cfg, "18:30", segment="createur_freelance")
        self.assertNotEqual(autre["brief"]["sujet"], post["brief"]["sujet"], "un sujet en attente n'est pas refait")
        (self.run.OUT / f"{post['id']}.mp4").write_bytes(b"x")          # la vidéo est déjà sur place : rien à télécharger
        code = self.run.cmd_valider(types.SimpleNamespace(video=post["id"]), self.cfg, self.state)
        self.assertEqual(code, 0)
        self.assertEqual(envoye, [1])
        self.assertEqual([p["id"] for p in self.state.posts], [post["id"]])
        self.assertEqual(len(self.state.load("attente", [])), 1)
        self.assertEqual(self.run.cmd_valider(types.SimpleNamespace(video="inconnue"), self.cfg, self.state), 1)

    def test_validation_deleguee(self):
        self.pret_a_publier("preuve_signee")
        a = self.run.make_one(self.state, self.cfg, "18:30", segment="commercant")
        b = self.run.make_one(self.state, self.cfg, "18:30", segment="commercant")
        self.assertEqual(len(self.state.posts), 2)
        self.assertNotEqual(a["brief"]["sujet"], b["brief"]["sujet"], "une réserve ne sert qu'une fois")
        self.assertEqual(a["suite"]["n"], b["brief"]["sujet"], "la suite annoncée est bien la vidéo suivante")

    def test_publication_reelle_sans_destinataire(self):
        self.pret_a_publier("preuve_signee")
        self.run.publish_all = lambda *a, **k: {"tiktok": {"status": "skipped", "error": "aucun accès configuré pour ce réseau"}}
        with self.assertRaises(RuntimeError):
            self.run.make_one(self.state, self.cfg, "18:30", segment="createur_freelance")
        self.assertEqual(self.state.posts, [], "rien n'est compté : le sujet reste disponible")

    def test_reserve_epuisee(self):
        self.pret_a_publier("preuve_signee")
        faits = [self.run.make_one(self.state, self.cfg, "18:30", segment="commercant") for _ in range(4)]
        self.assertEqual([bool(p and p.get("id")) for p in faits], [True, True, True, False], "sans modèle, 3 réserves par série puis l'agent s'arrête")
        self.assertEqual(len(self.state.posts), 3)


if __name__ == "__main__":
    unittest.main()
