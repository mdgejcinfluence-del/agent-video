"""Tests sans réseau : forme du storyboard, garde-fous, écran de fin, timeline, rushs, stratège, bilan, porte, parcours complet.

    python3 -m unittest discover -s tests
"""
import copy
import datetime as dt
import json
import os
import random
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from studio import align, bilan, config, fiche, garde, porte, rushs, schema, scout, strategist, timeline, writer  # noqa: E402
from studio.publish import legende, packs  # noqa: E402
from studio.state import State, now  # noqa: E402

JOUR = "2026-11-11"          # jour de la première vérification des faits (data/faits.yaml)
CLES = ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GROQ_API_KEY", "PEXELS_API_KEY", "PIXABAY_API_KEY", "BUFFER_API_KEY", "FB_PAGE_TOKEN", "IG_TOKEN", "TIKTOK_REFRESH_TOKEN")


def sans_cles():
    for k in CLES:
        os.environ.pop(k, None)


def etat() -> State:
    return State(Path(tempfile.mkdtemp()))


def faits_du_jour() -> dict:
    return scout.faits_confirmes(ROOT, etat(), today=JOUR)


def reserve(name: str) -> dict:
    return json.loads((ROOT / "examples" / "reserve" / f"{name}.json").read_text(encoding="utf-8"))


def cfg0() -> dict:
    sans_cles()
    return config.load()


def voix(story: dict) -> list[dict]:
    """Fausses voix : 0,3 s par mot, sans horodatage (la timeline estime les mots)."""
    import numpy as np
    out = []
    for sc in story["scenes"]:
        n = len(align.parse_say(sc["say"])[1])
        out.append({"audio": np.zeros(int(48000 * 0.3 * n), dtype="float32"), "dur": 0.3 * n, "words": [], "provider": "test"})
    return out


class Forme(unittest.TestCase):
    def test_les_six_reserves_passent_tous_les_controles(self):
        cfg, faits = cfg0(), faits_du_jour()
        noms = [r["_reserve"] for r in writer.reserves(cfg)]
        self.assertEqual(len(noms), 6)
        for r in writer.reserves(cfg):
            st, pb = writer.controler(r, cfg, faits, strict=False)
            self.assertEqual(pb, [], r["_reserve"])
            self.assertEqual(st["scenes"][-1]["type"], "fin")
            self.assertTrue(1 <= len(schema.refs_in(st)) <= 3, "1 à 3 séquences filmées par vidéo")

    def test_chaque_reserve_annonce_une_suite_qui_existe(self):
        noms = {r["_reserve"] for r in writer.reserves(cfg0())}
        for r in writer.reserves(cfg0()):
            self.assertIn(r["suite"]["reserve"], noms, r["_reserve"])
            self.assertNotEqual(r["suite"]["reserve"], r["_reserve"])

    def test_refus_expliques_en_francais(self):
        st = reserve("r2_zapper")
        st["scenes"][1]["blocks"].append({"kind": "liste", "items": ["a", "b"]})
        st["scenes"][1]["blocks"].append({"kind": "mot", "text": "x"})
        st["scenes"][2]["say"] += " [c1]encore"
        st["scenes"][3]["blocks"][0]["items"].append("Un élément beaucoup trop long pour tenir sur une barre")
        st["scenes"][0]["tuile"] = {"label": "ÉTAPE", "n": 1}
        st["keyword"] = "DEUX MOTS"
        _, pb = schema.normaliser(st)
        txt = "\n".join(pb)
        for attendu in ("2 blocs au plus", "repères inconnus", "trop long", "pas de tuile sur l'accroche", "UN mot"):
            self.assertIn(attendu, txt)

    def test_ecran_trop_charge_refuse_avant_le_rendu(self):
        st = reserve("r1_monteur")
        st["scenes"][3]["blocks"].append({"kind": "liste", "items": ["un", "deux", "trois"]})
        _, pb = schema.normaliser(st)
        self.assertTrue(any("trop chargé" in p for p in pb), pb)

    def test_sans_sequence_filmee_pas_de_video(self):
        st = reserve("r2_zapper")
        st["scenes"][2]["blocks"] = [{"kind": "mot", "text": "Sous-titres"}]
        st["scenes"][2]["say"] = "Erreur deux : pas de sous-titres. Beaucoup de gens regardent sans le son, alors écris ce que tu dis."
        _, pb = schema.normaliser(st)
        self.assertTrue(any("séquences filmées" in p for p in pb), pb)

    def test_recherche_de_rush_en_anglais(self):
        st = reserve("r5_plans")
        st["scenes"][1]["blocks"][0]["q"] = "pot de crème posé"
        _, pb = schema.normaliser(st)
        self.assertTrue(any("anglais" in p for p in pb), pb)


class Garde(unittest.TestCase):
    def setUp(self):
        self.cfg, self.faits = cfg0(), faits_du_jour()

    def refus(self, modif) -> str:
        st, _ = schema.normaliser(reserve("r2_zapper"))
        modif(st)
        return "\n".join(garde.controle(st, self.cfg, self.faits))

    def test_promesses_interdites(self):
        cas = {
            "Avec ça, tu vas gagner de l'argent chaque jour.": "revenu",
            "C'est garanti, ta vidéo sera vue.": "garanti",
            "Ta vidéo devient virale.": "audience",
            "J'ai testé cette méthode pendant un mois.": "expérience personnelle",
            "Mes clients adorent cette astuce.": "clients",
            "Commente et je t'envoie la liste en privé.": "envoi en privé",
            "Des vidéos à l'infini, sans limite.": "illimité",
            "Passe par un VPN pour débloquer l'appli.": "contournement",
        }
        for phrase, motif in cas.items():
            txt = self.refus(lambda st, p=phrase: st["scenes"][1].update(say=st["scenes"][1]["say"] + " " + p))
            self.assertIn(motif, txt, phrase)

    def test_outil_nomme_sans_fait_refuse(self):
        txt = self.refus(lambda st: st["scenes"][1].update(say=st["scenes"][1]["say"] + " Ouvre CapCut et coupe le début."))
        self.assertIn("capcut", txt)

    def test_outil_couvert_par_un_fait_accepte(self):
        st, _ = schema.normaliser(reserve("r3_rushs"))
        self.assertEqual(garde.controle(st, self.cfg, self.faits), [])
        st["faits"] = []
        txt = "\n".join(garde.controle(st, self.cfg, self.faits))
        self.assertIn("pexels", txt); self.assertIn("gratuit", txt)

    def test_fait_suspendu_refuse(self):
        st, _ = schema.normaliser(reserve("r3_rushs"))
        faits = {k: v for k, v in self.faits.items() if k != "pexels-licence"}
        self.assertTrue(any("pexels-licence" in p for p in garde.controle(st, self.cfg, faits)))

    def test_chiffre_avec_unite_sans_source(self):
        txt = self.refus(lambda st: st["scenes"][1].update(say=st["scenes"][1]["say"] + " Tu perds 80 % des gens en 3 secondes."))
        self.assertIn("chiffre sans source", txt)
        self.assertEqual(self.refus(lambda st: None), "", "les simples comptes (3 erreurs, erreur 2) restent libres")

    def test_promesse_de_fin_seulement_la_suite(self):
        self.assertIn("vidéo suivante", self.refus(lambda st: st.update(promesse="le PDF avec tous les liens")))
        self.assertEqual(self.refus(lambda st: st.update(promesse="la partie 2 : le script exact")), "")

    def test_rush_jamais_presente_comme_un_temoignage(self):
        def modif(st):
            st["scenes"][2]["blocks"][0]["titre"] = "Avis *client*"
        self.assertIn("trompeuse", self.refus(modif))


class Fin(unittest.TestCase):
    def test_fin_sans_formation_tant_que_rien_n_est_confirme(self):
        cfg = cfg0()
        st, _ = writer.controler(reserve("r1_monteur"), cfg, faits_du_jour())
        fin = st["scenes"][-1]
        self.assertEqual(align.parse_say(fin["say"])[0], "Abonne-toi pour ne rien rater. Et commente MONTAGE si tu veux la partie 2 : les effets du montage.")
        self.assertNotIn("promo", fin)
        self.assertNotIn("promo", legende(st, cfg).lower())

    def test_formation_annoncee_seulement_si_promo_confirmee_et_lien(self):
        cfg = cfg0()
        cfg["offer"]["promo"] = {"confirmee": True, "jusquau": "2099-01-01"}
        self.assertFalse(writer.promo_active(cfg), "sans lien en bio, on n'annonce rien")
        cfg["offer"]["lien_bio"] = "https://exemple.com/formation"
        self.assertTrue(writer.promo_active(cfg))
        st, _ = writer.controler(reserve("r1_monteur"), cfg, faits_du_jour())
        self.assertTrue(st["scenes"][-1]["say"].endswith("[promo]La formation complète est en promo, lien en bio."))
        self.assertIn("lien en bio", legende(st, cfg))
        cfg["offer"]["promo"]["jusquau"] = "2020-01-01"
        self.assertFalse(writer.promo_active(cfg), "promotion terminée : l'agent arrête d'en parler tout seul")

    def test_legende_structure(self):
        cfg = cfg0()
        st, _ = writer.controler(reserve("r3_rushs"), cfg, faits_du_jour())
        txt = packs(st, cfg, "Images : Pexels (Ana B.)")["facebook"]["legende"]
        for frag in ("1️⃣", "⚠️ Gratuit ne veut pas dire sans règle", "💬 Commente RUSH si tu veux la suite : les plans à filmer", "🔔 Abonne-toi", "#astucevideo", "Images : Pexels (Ana B.)"):
            self.assertIn(frag, txt)


class Timeline(unittest.TestCase):
    def test_reperes_blocs_sous_titres_et_durees_des_rushs(self):
        cfg = cfg0()
        st, _ = writer.controler(reserve("r1_monteur"), cfg, faits_du_jour())
        b = timeline.build(st, voix(st), cfg)
        tl = b["timeline"]
        self.assertEqual([s["type"] for s in tl["scenes"]], ["ecran"] * 5 + ["fin"])
        self.assertEqual(tl["scenes"][0]["blocks"][0]["at"], 0.0, "le premier bloc est à l'image dès la première image")
        for a, c in zip(tl["scenes"], tl["scenes"][1:]):
            self.assertAlmostEqual(a["t1"], c["t0"], places=2)
        s4 = tl["scenes"][3]["blocks"][0]
        self.assertEqual(s4["kind"], "avant_apres")
        self.assertTrue(s4["at"] < s4["wipeAt"] < s4["fxAt"][0] < s4["fxAt"][1] < s4["fxAt"][2] < tl["scenes"][3]["t1"])
        self.assertEqual(set(b["rushs"]), set(schema.refs_in(st)))
        for ref, need in b["rushs"].items():
            self.assertGreater(need["duree"], 2.0)
        fin = tl["scenes"][-1]
        self.assertTrue(fin["t0"] < fin["clickAt"] < fin["boxAt"] < fin["kwAt"] < fin["promesseAt"] < fin["t1"])
        caps = tl["captions"]
        self.assertTrue(all(len(g["words"]) <= 4 for g in caps), "sous-titres courts : trois mots, quatre quand un petit mot serait resté seul")
        self.assertTrue(all(a["t1"] <= c["t0"] for a, c in zip(caps, caps[1:])), "les sous-titres ne se chevauchent pas")
        self.assertEqual(tl["cover"]["lines"], ["CETTE VIDÉO", "N'A PAS DE", "*MONTEUR*"])
        self.assertIn("pouce", tl["avatar"]["poses"])


class Rushs(unittest.TestCase):
    def setUp(self):
        self.lib = rushs.bibliotheque(ROOT)

    def test_bibliotheque_de_depart(self):
        self.assertGreaterEqual(len(self.lib), 12)
        for c in self.lib:
            self.assertTrue(c["url"].startswith("https://videos.pexels.com/"), c["id"])
            self.assertTrue(c["page"].startswith("https://www.pexels.com/video/"))
            self.assertTrue(min(c["w"], c["h"]) >= 720 and c["dur"] >= 5)

    def test_le_bon_rush_pour_la_bonne_phrase(self):
        cas = {"hands typing laptop keyboard": "px-10374892", "sewing machine hands fabric": "px-39761233", "product jar hand placing": "px-6343712",
               "cosmetic bottles table sunlight": "px-7614398", "phone holder tripod stable": "px-28311225", "hands holding product jar cream": "px-4351114"}
        for q, attendu in cas.items():
            rows = rushs.classer({"q": q, "cadre": "portrait"}, self.lib)
            self.assertEqual(rows[0][1]["id"], attendu, q)

    def test_rien_plutot_qu_un_rush_hors_sujet(self):
        for c in self.lib:
            self.assertLess(rushs.note_mots({"q": "cat playing piano"}, c), 0.5)

    def test_toutes_les_reserves_trouvent_leurs_rushs_sans_cle(self):
        for r in writer.reserves(cfg0()):
            st, _ = schema.normaliser(r)
            for b in rushs.besoins_de(st):
                best = [c for s, c in rushs.classer(b, self.lib) if rushs.note_mots(b, c) >= 0.5]
                self.assertTrue(best, f"{r['_reserve']} : rien pour « {b['q']} »")

    def test_personne_reconnaissable_jamais_dans_un_passage_negatif(self):
        b = {"q": "seller package shop", "cadre": "portrait", "sensible": True}
        self.assertEqual([c for _, c in rushs.classer(b, self.lib) if c.get("personnes")], [])
        st, _ = schema.normaliser(reserve("r2_zapper"))
        besoins = rushs.besoins_de(st)
        self.assertTrue(besoins[0]["sensible"], "« Erreur deux : pas de sous-titres » est un passage négatif")

    def test_refus_image_generee_et_definition_trop_faible(self):
        self.assertFalse(rushs.convient({"cadre": "portrait"}, {"w": 1080, "h": 1920, "dur": 9, "tags": ["ai generated", "woman"]})[0])
        self.assertFalse(rushs.convient({"cadre": "portrait"}, {"w": 360, "h": 640, "dur": 9, "tags": []})[0])
        self.assertFalse(rushs.convient({"cadre": "portrait"}, {"w": 1080, "h": 1920, "dur": 2, "tags": []})[0])

    def test_credit_dans_la_legende(self):
        ch = {"a": {"id": "px-1", "source": "pexels", "auteur": "Ana B.", "page": "p", "licence": "l"}, "b": {"id": "pb-2", "source": "pixabay", "auteur": "joe", "page": "p", "licence": "l"},
              "c": {"id": "px-1", "source": "pexels", "auteur": "Ana B.", "page": "p", "licence": "l"}}
        self.assertEqual(rushs.ligne_credit(ch), "Images : Pexels (Ana B.), Pixabay (joe)")
        self.assertEqual(len(rushs.credits(ch)), 2)


class Faits(unittest.TestCase):
    def test_fait_manuel_valable_un_temps_puis_expire(self):
        st = etat()
        self.assertIn("pexels-licence", scout.faits_confirmes(ROOT, st, today="2026-12-01"))
        self.assertNotIn("pexels-licence", scout.faits_confirmes(ROOT, st, today="2027-03-01"), "au-delà de 90 jours, il faut relire la page")

    def test_fait_automatique_suspendu_si_la_phrase_disparait(self):
        st = etat()
        logs = []
        scout.verifier_faits(ROOT, st, logs.append, force=True, fetch=lambda url: (200, "page réécrite, plus rien d'attendu"))
        ok = scout.faits_confirmes(ROOT, st)
        self.assertNotIn("remotion-principe", ok)
        self.assertIn("pexels-licence", ok, "un fait lu à la main ne dépend pas de la veille automatique")
        self.assertTrue(any("CHANGEMENT" in l for l in logs))


class Mode(unittest.TestCase):
    def test_mode_essai_automatique(self):
        sans_cles()
        self.assertTrue(config.essai({"publish": {"dry_run": "auto"}}), "aucune clé de publication : essai")
        os.environ["BUFFER_API_KEY"] = "x"
        try:
            self.assertFalse(config.essai({"publish": {"dry_run": "auto"}}), "la clé ajoutée, l'agent publie sans autre réglage")
            self.assertTrue(config.essai({"publish": {"dry_run": True}}), "dry_run: true arrête tout")
        finally:
            sans_cles()


class Stratege(unittest.TestCase):
    def setUp(self):
        self.cfg, self.faits, self.st = cfg0(), faits_du_jour(), etat()
        self.res = [r["_reserve"] for r in writer.reserves(self.cfg)]

    def post(self, pid, idee, reserve_=None, famille="methode", score=None, days=0, **extra):
        at = (now() - dt.timedelta(days=days)).isoformat(timespec="seconds")
        p = {"id": pid, "created": at, "title": f"vidéo {pid}", "keyword": "MOT", "duration": 46, "brief": {"idee": idee, "famille": famille, "hook_type": "resultat", "slot": "soir",
             **({"reserve": reserve_} if reserve_ else {})}, "published": {"facebook": {"status": "sent"}}, "stats": {}, **extra}
        if score is not None:
            p["score"] = score
        self.st.add_post(p)
        return p

    def test_essai_les_reserves_tournent_sans_rien_consommer(self):
        vus = []
        for n in range(6):
            self.st.save("essais", {"n": n})
            vus.append(strategist.choisir(ROOT, self.st, self.cfg, self.faits, random.Random(1), True, False, self.res)["reserve"])
        self.assertEqual(sorted(vus), sorted(self.res))

    def test_sans_modele_seulement_les_reserves_puis_rien(self):
        c = strategist.choisir(ROOT, self.st, self.cfg, self.faits, random.Random(3), False, False, self.res)
        self.assertIn(c["reserve"], self.res)
        for i in strategist.banque(ROOT)["idees"]:
            if i.get("reserve"):
                self.post("p-" + i["id"], i["id"], i["reserve"])
        self.assertIsNone(strategist.choisir(ROOT, self.st, self.cfg, self.faits, random.Random(3), False, False, self.res))
        self.assertIsNotNone(strategist.choisir(ROOT, self.st, self.cfg, self.faits, random.Random(3), False, True, self.res), "avec un modèle, les autres idées s'ouvrent")

    def test_la_suite_promise_passe_avant_tout(self):
        p = self.post("p1", "c01", "r1_monteur", "coulisses")
        strategist.noter_suite(self.st, p, reserve("r1_monteur"))
        c = strategist.choisir(ROOT, self.st, self.cfg, self.faits, random.Random(5), False, False, self.res)
        self.assertEqual(c["reserve"], "r4_effets")
        self.assertEqual(c["suite_de"], "p1")
        strategist.marquer_suite(self.st, "p1", "p2")
        c2 = strategist.choisir(ROOT, self.st, self.cfg, self.faits, random.Random(5), False, False, self.res)
        self.assertNotIn("suite_de", c2)

    def test_idee_sans_fait_confirme_ecartee(self):
        faits = {k: v for k, v in self.faits.items() if not k.startswith("pexels")}
        for seed in range(30):
            c = strategist.choisir(ROOT, self.st, self.cfg, faits, random.Random(seed), False, True, self.res)
            self.assertNotIn("pexels-licence", c["idee"].get("faits") or [])

    def test_plan_du_jour(self):
        plan = strategist.plan_day(self.st, self.cfg, "2026-11-12", random.Random(1))
        self.assertEqual(len(plan["slots"]), 2)
        self.assertTrue(set(plan["slots"]) <= set(self.cfg["schedule"]["slots"]))


class Bilan(unittest.TestCase):
    def setUp(self):
        self.cfg, self.st = cfg0(), etat()
        vrai = strategist.score_posts
        self.addCleanup(lambda: setattr(strategist, "score_posts", vrai))

    def remplir(self, n_par_famille=3):
        k = 0
        for fam, score in (("erreurs", 1.2), ("methode", -0.8), ("liste", 0.1)):
            for _ in range(n_par_famille):
                k += 1
                at = (now() - dt.timedelta(days=4)).isoformat(timespec="seconds")
                self.st.add_post({"id": f"p{k}", "created": at, "title": f"{fam} {k}", "keyword": "MOT", "duration": 44 if fam == "erreurs" else 62,
                                  "brief": {"idee": f"i{k}", "famille": fam, "hook_type": "probleme" if fam == "erreurs" else "resultat", "slot": "soir"},
                                  "published": {"facebook": {"status": "sent", "id": "x", "at": at}}, "score": score,
                                  "stats": {"facebook": [{"h": 30, "views": 1000 + 100 * k, "comments": k}]}})

    def test_pas_de_conclusion_sur_du_bruit(self):
        self.remplir(1)
        strategist.score_posts = lambda *_: None
        r = bilan.faire(self.st, self.cfg, ROOT, None, lambda *_: None)
        self.assertEqual(r["poids"], r["poids_avant"])
        self.assertIn("Rien n'est changé", r["constats"][0])

    def test_les_poids_bougent_dans_des_bornes(self):
        self.remplir(3)
        strategist.score_posts = lambda *_: None
        avant = strategist.poids(ROOT, self.st)
        r = bilan.faire(self.st, self.cfg, ROOT, None, lambda *_: None)
        self.assertGreater(r["poids"]["erreurs"], avant["erreurs"])
        self.assertLess(r["poids"]["methode"], avant["methode"])
        self.assertAlmostEqual(sum(r["poids"].values()), 1.0, places=2)
        self.assertGreaterEqual(min(r["poids"].values()), 0.05, "aucune famille ne disparaît")
        self.assertLess(r["poids"]["erreurs"] / avant["erreurs"], 1.6, "pas de virage brutal")
        self.assertAlmostEqual(strategist.poids(ROOT, self.st)["erreurs"], r["poids"]["erreurs"], places=3, msg="le stratège lit les nouveaux poids")
        md = (Path(self.st.dir) / "BILAN.md").read_text(encoding="utf-8")
        for frag in ("# Bilan du", "Décisions prises par l'agent", "Par accroche", "Les erreurs à éviter"):
            self.assertIn(frag, md)
        self.assertTrue(any(i.get("origine") == "bilan" for i in self.st.load("idees", [])), "la meilleure vidéo donne une variante")
        self.assertFalse(bilan.du(self.st, self.cfg), "le bilan suivant attend 3 jours")


class Porte(unittest.TestCase):
    def test_controle_qualite_en_echec_retient_la_video(self):
        st, _ = schema.normaliser(reserve("r3_rushs"))
        faits = faits_du_jour()
        self.assertEqual(porte.bloquants({}, st, {"ok": True}, faits), [])
        self.assertTrue(porte.bloquants({}, st, {"ok": False, "problems": ["durée 120 s"]}, faits))
        self.assertTrue(porte.bloquants({}, st, {"ok": True}, {k: v for k, v in faits.items() if k != "pixabay-licence"}))


class Parcours(unittest.TestCase):
    """Le réveil complet, avec une fabrication simulée (le rendu réel est essayé à part)."""
    def setUp(self):
        import run
        self.run = run
        self.cfg = cfg0()
        self.tmp = Path(tempfile.mkdtemp())
        self.st = State(self.tmp)
        self._orig = (run.OUT, run.produce.make_video, run.publish_all, run._host, run.veille)
        run.OUT = self.tmp / "out"
        run.OUT.mkdir()
        run.LINES.clear()
        faits = faits_du_jour()
        run.veille = lambda state, cfg, force=False, brain=None: faits

        def faux_rendu(story, cfg, out_dir, slug, log=print, workers=None, faits=None, state=None, brain=None):
            story, _ = writer.controler(story, cfg, faits or {}, strict=True)
            b = timeline.build(story, voix(story), cfg)
            ch = {ref: {"id": "px-10374892", "source": "pexels", "auteur": "", "page": "https://www.pexels.com/video/x-10374892/", "licence": "Licence Pexels",
                        "controle": "bibliothèque", "mesures": {"w": 1080, "h": 1920, "dur": 8.5, "nettete": 400, "mouvement": 10}} for ref in b["rushs"]}
            return {"video": str(out_dir / f"{slug}.mp4"), "thumb": str(out_dir / f"{slug}.jpg"), "thumb_ms": 3000, "duration": b["duration"], "words": b["words"],
                    "voice": ["test"], "voice_rate": "+15%", "audio": {"lufs": -14.1, "clarte_db": 22}, "render": {}, "qa": {"ok": True, "problems": [], "warnings": []},
                    "story": story, "scenes": [{"type": s["type"], "t0": s["t0"], "t1": s["t1"]} for s in b["timeline"]["scenes"]], "layout": {"warnings": []}, "rushs": ch}
        run.produce.make_video = faux_rendu

    def tearDown(self):
        r = self.run
        r.OUT, r.produce.make_video, r.publish_all, r._host, r.veille = self._orig
        sans_cles()

    def test_essai_rien_n_est_publie_ni_compte(self):
        post = self.run.make_one(self.st, self.cfg, "18:00")
        self.assertTrue(post["qa"]["ok"])
        self.assertEqual(self.st.posts, [])
        self.assertEqual(self.st.load("essais", {})["n"], 1)
        fiche_md = (self.run.OUT / f"{post['id']}.md").read_text(encoding="utf-8")
        for frag in ("## 1. Stratégie", "## 3. Séquences filmées et droits", "## 4. Script minuté", "## 6. Contrôle avant publication", "rien ne bloque"):
            self.assertIn(frag, fiche_md)
        self.assertTrue(any("MODE ESSAI" in l for l in self.run.LINES))

    def test_publication_reelle_sans_validation_humaine(self):
        os.environ["BUFFER_API_KEY"] = "cle"
        envois = []
        self.run._host = lambda post_id, res, cfg, state: f"https://exemple.github.io/v/{post_id}.mp4"

        def faux_envoi(video, story, thumb_ms, public_url, cfg, state, log=print, credit=""):
            envois.append((public_url, credit))
            return {"facebook": {"status": "sent", "id": "fb1", "via": "buffer", "at": now().isoformat(timespec="seconds")}}
        self.run.publish_all = faux_envoi
        post = self.run.make_one(self.st, self.cfg, "18:00")
        self.assertEqual(len(envois), 1, "la vidéo part seule, sans attente de validation")
        self.assertEqual(envois[0][1], "Images : Pexels")
        self.assertEqual([p["id"] for p in self.st.posts], [post["id"]])
        suites = self.st.load("suites", [])
        self.assertEqual(len(suites), 1, "la suite annoncée est inscrite")
        # le réveil suivant produit la suite promise
        post2 = self.run.make_one(self.st, self.cfg, "20:30")
        self.assertEqual(post2["brief"]["suite_de"], post["id"])
        self.assertEqual(post2["brief"]["reserve"], suites[0]["suite"]["reserve"])
        self.assertTrue(self.st.load("suites", [])[0]["faite"])

    def test_controle_qualite_en_echec_rien_ne_part(self):
        os.environ["BUFFER_API_KEY"] = "cle"
        vrai = self.run.produce.make_video

        def rate(*a, **k):
            r = vrai(*a, **k)
            r["qa"] = {"ok": False, "problems": ["voix couverte par le fond sonore"], "warnings": []}
            return r
        self.run.produce.make_video = rate
        self.run.publish_all = lambda *a, **k: self.fail("rien ne doit partir")
        post = self.run.make_one(self.st, self.cfg, "18:00")
        self.assertFalse(post["qa"]["ok"])
        self.assertEqual(self.st.posts, [])
        self.assertTrue(any("RETENUE" in l for l in self.run.LINES))

    def test_rush_introuvable_autre_sujet(self):
        vrai = self.run.produce.make_video
        vus = []

        def capricieux(story, *a, **k):
            vus.append(story.get("_reserve"))
            if len(vus) == 1:
                raise self.run.produce.RushIntrouvable("aucune séquence acceptable pour : « x »")
            return vrai(story, *a, **k)
        self.run.produce.make_video = capricieux
        post = self.run.make_one(self.st, self.cfg, "18:00")
        self.assertIsNotNone(post)
        self.assertEqual(len(vus), 2)
        self.assertNotEqual(vus[0], vus[1], "on ne maquille pas un manque : on change de sujet")


if __name__ == "__main__":
    unittest.main()
