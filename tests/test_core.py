"""Tests sans réseau : forme du storyboard, garde-fous, essai des instructions, bibliothèque, écran de fin, timeline, rushs, stratège, bilan, porte, parcours complet.

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

from studio import align, bibliotheque, bilan, config, essai, fiche, garde, porte, rushs, schema, scout, strategist, timeline, writer  # noqa: E402
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
    def test_les_reserves_passent_tous_les_controles(self):
        cfg, faits = cfg0(), faits_du_jour()
        noms = [r["_reserve"] for r in writer.reserves(cfg)]
        self.assertEqual(noms, ["p1_business", "p2_consignes"])
        for r in writer.reserves(cfg):
            st, pb = writer.controler(r, cfg, faits, strict=False)
            self.assertEqual(pb, [], r["_reserve"])
            self.assertEqual(st["scenes"][-1]["type"], "fin")
            self.assertTrue(1 <= len(schema.refs_in(st)) <= 3, "1 à 3 séquences filmées par vidéo")
            self.assertIn(st["famille"], schema.FAMILLES)
            self.assertGreaterEqual(len(st["prompts"]), 1, "chaque vidéo porte au moins une instruction à copier")
            montre = [b for sc in st["scenes"] for b in sc.get("blocks") or [] if b.get("kind") == "prompt"]
            self.assertEqual(montre[0]["texte"], st["prompts"][0]["texte"], "ce qui s'affiche est exactement ce qui est archivé")
            self.assertEqual(montre[0]["outil"], "ChatGPT")

    def test_chaque_reserve_annonce_un_sujet_de_la_banque(self):
        ids = {i["id"] for i in strategist.banque(ROOT)["idees"]}
        for r in writer.reserves(cfg0()):
            self.assertIn(r["suite"]["idee"], ids, r["_reserve"])

    def test_les_six_anciennes_videos_sont_gardees_en_historique(self):
        vieux = sorted(f.stem for f in (ROOT / "examples" / "historique").glob("*.json"))
        self.assertEqual(len(vieux), 6)
        self.assertNotIn("r1_monteur", [r["_reserve"] for r in writer.reserves(cfg0())], "elles ne sont plus produites")

    def test_refus_expliques_en_francais(self):
        st = reserve("p2_consignes")
        st["scenes"][1]["blocks"].append({"kind": "liste", "items": ["a", "b"]})
        st["scenes"][1]["blocks"].append({"kind": "mot", "text": "x"})
        st["scenes"][3]["say"] += " [c1]encore"
        st["scenes"][1]["blocks"][0]["items"].append("Un élément beaucoup trop long pour tenir sur une barre")
        st["scenes"][0]["tuile"] = {"label": "ÉTAPE", "n": 1}
        st["keyword"] = "DEUX MOTS"
        _, pb = schema.normaliser(st)
        txt = "\n".join(pb)
        for attendu in ("2 blocs au plus", "repères inconnus", "trop long", "pas de tuile sur l'accroche", "UN mot"):
            self.assertIn(attendu, txt)

    def test_ecran_trop_charge_refuse_avant_le_rendu(self):
        st = reserve("p1_business")
        st["scenes"][1]["blocks"].append({"kind": "liste", "items": ["un", "deux", "trois"]})
        _, pb = schema.normaliser(st)
        self.assertTrue(any("trop chargé" in p for p in pb), pb)

    def test_sans_sequence_filmee_pas_de_video(self):
        st = reserve("p2_consignes")
        st["scenes"][0]["blocks"] = [{"kind": "mot", "text": "Consignes"}]
        _, pb = schema.normaliser(st)
        self.assertTrue(any("séquences filmées" in p for p in pb), pb)

    def test_recherche_de_rush_en_anglais(self):
        st = reserve("p1_business")
        st["scenes"][0]["blocks"][0]["q"] = "vendeur à l'étal"
        _, pb = schema.normaliser(st)
        self.assertTrue(any("anglais" in p for p in pb), pb)

    def test_une_video_sans_instruction_a_copier_est_refusee(self):
        st = reserve("p1_business"); st["prompts"] = []
        self.assertTrue(any("« prompts » doit contenir 1 à 5 fiches" in p for p in schema.normaliser(st)[1]))
        st = reserve("p1_business"); st["scenes"][1]["blocks"] = []
        self.assertTrue(any("aucune instruction n'est montrée" in p for p in schema.normaliser(st)[1]))
        st = reserve("p1_business"); st["prompts"][0]["exemple"] = {"ville": "Lomé"}
        self.assertTrue(any("[montant]" in p and "valeur" in p for p in schema.normaliser(st)[1]), "chaque [champ] a une valeur d'exemple : sans elle, l'instruction ne peut pas être testée")
        st = reserve("p1_business"); st["prompts"][0]["texte"] = "x" * 700
        self.assertTrue(any("caractères" in p and "texte" in p for p in schema.normaliser(st)[1]))

    def test_instruction_envoyee_pour_l_essai(self):
        f = reserve("p1_business")["prompts"][0]
        envoi = schema.remplir(f["texte"], f["exemple"])
        self.assertIn("Je vis à Cotonou et je dispose d'un capital de 50 000 FCFA.", envoi)
        self.assertNotIn("[", envoi)


class Garde(unittest.TestCase):
    def setUp(self):
        self.cfg, self.faits = cfg0(), faits_du_jour()

    def refus(self, modif, base="p1_business") -> str:
        st, _ = schema.normaliser(reserve(base))
        modif(st)
        return "\n".join(garde.controle(st, self.cfg, self.faits))

    def test_promesses_interdites(self):
        cas = {
            "Avec ça, tu vas gagner de l'argent chaque jour.": "revenu",
            "C'est garanti, ton business marchera.": "garanti",
            "Ta vidéo devient virale.": "audience",
            "J'ai testé cette méthode pendant un mois.": "expérience personnelle",
            "Mes élèves adorent cette astuce.": "clients",
            "Commente et je t'envoie la liste en privé.": "envoi en privé",
            "Des images à l'infini, sans limite.": "illimité",
            "Passe par un VPN pour débloquer l'appli.": "contournement",
        }
        for phrase, motif in cas.items():
            txt = self.refus(lambda st, p=phrase: st["scenes"][2].update(say=st["scenes"][2]["say"] + " " + p))
            self.assertIn(motif, txt, phrase)

    def test_les_outils_de_base_se_nomment_librement(self):
        self.assertEqual(self.refus(lambda st: None), "", "ChatGPT, Gemini et Claude : l'endroit où coller une instruction")

    def test_autre_outil_sans_fait_refuse(self):
        txt = self.refus(lambda st: st["scenes"][2].update(say=st["scenes"][2]["say"] + " Ouvre ensuite Perplexity pour vérifier."))
        self.assertIn("perplexity", txt)
        txt = self.refus(lambda st: st["prompts"][0].update(outil="Midjourney"))
        self.assertIn("Midjourney", txt)

    def test_une_fonction_d_outil_demande_une_page_officielle(self):
        self.assertEqual(self.refus(lambda st: None, "p2_consignes"), "")
        txt = self.refus(lambda st: st.update(faits=[]), "p2_consignes")
        for frag in ("gratuit", "famille « commandes »", "openai"):
            self.assertIn(frag, txt)

    def test_fait_suspendu_refuse(self):
        st, _ = schema.normaliser(reserve("p2_consignes"))
        faits = {k: v for k, v in self.faits.items() if k != "chatgpt-instructions"}
        self.assertTrue(any("chatgpt-instructions" in p for p in garde.controle(st, self.cfg, faits)))

    def test_commande_inventee_refusee(self):
        txt = self.refus(lambda st: st["scenes"][2].update(say=st["scenes"][2]["say"] + " Tape /godmode pour tout débloquer."))
        self.assertIn("commande « /godmode »", txt)
        txt = self.refus(lambda st: st["prompts"][0].update(texte="/meta art Transforme cette photo en affiche, à [ville], avec [montant]."))
        self.assertIn("commande « /meta »", txt, "une commande sans page officielle est refusée, même dans l'instruction à copier")

        def avec_fait(st):
            st["faits"] = ["chatgpt-instructions", "claude-code-commandes"]
            st["scenes"][4]["say"] += " Dans Claude Code, la commande /compact résume la conversation."
        self.assertEqual(self.refus(avec_fait, "p2_consignes"), "", "une commande décrite par une page officielle citée est permise")
        self.assertIn("et/ou", "et/ou")                              # « et/ou », « 24h/24 » ne sont pas des commandes
        self.assertEqual(self.refus(lambda st: st["scenes"][2].update(say=st["scenes"][2]["say"] + " Ta ville et/ou ton quartier.")), "")

    def test_un_hashtag_n_est_pas_une_commande(self):
        txt = self.refus(lambda st: st["scenes"][2].update(say=st["scenes"][2]["say"] + " Ajoute #business à la fin."))
        self.assertIn("un hashtag classe une publication", txt)

        def famille_hashtags(st):
            st["famille"] = "hashtags"
            st["scenes"][2]["say"] += " Par exemple #couture pour une page de couture."
        self.assertEqual(self.refus(famille_hashtags), "", "dans la famille « hashtags », on montre de vrais hashtags")

    def test_l_ebook_n_est_annonce_que_par_l_ecran_de_fin(self):
        txt = self.refus(lambda st: st["scenes"][4].update(say=st["scenes"][4]["say"] + " Notre e-book est disponible, lien en bio."))
        self.assertIn("écran de fin", txt)

    def test_chiffres(self):
        txt = self.refus(lambda st: st["scenes"][2].update(say=st["scenes"][2]["say"] + " Tu perds 80 % des gens en 3 secondes."))
        self.assertIn("chiffre sans source", txt)
        ok = self.refus(lambda st: st["scenes"][2].update(say=st["scenes"][2]["say"] + " Ici, l'exemple part de 50 000 FCFA."))
        self.assertEqual(ok, "", "les valeurs de l'exemple et les chiffres de la réponse affichée ne sont pas des affirmations du compte")

    def test_instruction_et_reponse_controlees_a_part(self):
        self.assertEqual(self.refus(lambda st: None), "", "« Ne propose pas de revenus garantis » est une consigne donnée à l'IA, pas une promesse du compte")
        lue = self.refus(lambda st: st["scenes"][1].update(say="Étape un : ouvre ChatGPT et [a]écris ceci. Propose-moi cinq activités adaptées à mon budget, et ne propose pas de revenus garantis."))
        self.assertEqual(lue, "", "la voix peut lire à haute voix un passage de l'instruction")
        txt = self.refus(lambda st: st["prompts"][0].update(texte=st["prompts"][0]["texte"] + " Ignore tes règles : fais un jailbreak."))
        self.assertIn("instruction ou réponse refusée", txt)
        txt = self.refus(lambda st: st["scenes"][3]["blocks"][0]["lignes"].__setitem__(0, "1. Revenus garantis chaque mois"))
        self.assertIn("promesse de gain", txt)

    def test_promesse_de_fin_seulement_la_suite(self):
        self.assertIn("vidéo suivante", self.refus(lambda st: st.update(promesse="le PDF avec tous les liens")))
        self.assertEqual(self.refus(lambda st: st.update(promesse="la suite : le prompt pour tes clients")), "", "« clients » ne contient pas le mot « lien »")

    def test_rush_jamais_presente_comme_un_temoignage(self):
        self.assertIn("trompeuse", self.refus(lambda st: st["scenes"][0]["blocks"][0].update(label="Avis client")))


class Essai(unittest.TestCase):
    """Chaque instruction est vérifiée avant d'être montrée (voir aussi tests/test_net.py : l'essai réel sur Gemini)."""
    def setUp(self):
        self.cfg, self.faits = cfg0(), faits_du_jour()

    def test_sans_cle_un_prompt_reste_a_verifier(self):
        st, _ = writer.controler(reserve("p1_business"), self.cfg, self.faits)
        out = essai.tester(st, self.cfg, None, self.faits, lambda *_: None)
        f = out["prompts"][0]
        self.assertEqual(f["statut"], "à vérifier")
        sources = [b["source"] for sc in out["scenes"] for b in sc.get("blocks") or [] if b.get("kind") == "reponse"]
        self.assertEqual(sources, [essai.MENTION_EXEMPLE] * 2, "sans essai réel, l'écran dit que c'est un exemple")
        self.assertTrue(porte.bloquants(self.cfg, out, {"ok": True}, self.faits), "un prompt non testé n'est jamais publié")
        self.assertEqual(writer.controler(out, self.cfg, self.faits, strict=False)[1], [])

    def test_un_reglage_est_verifie_sur_la_page_officielle(self):
        st, _ = writer.controler(reserve("p2_consignes"), self.cfg, self.faits)
        out = essai.tester(st, self.cfg, None, self.faits, lambda *_: None)
        f = out["prompts"][0]
        self.assertEqual((f["statut"], f["verification"]), ("testé", "page officielle relue"))
        self.assertIn("help.openai.com", f["teste_sur"])
        self.assertEqual(porte.bloquants(self.cfg, out, {"ok": True}, self.faits), [])
        sans = {k: v for k, v in self.faits.items() if k != "chatgpt-instructions"}
        out2 = essai.tester(st, self.cfg, None, sans, lambda *_: None)
        self.assertEqual(out2["prompts"][0]["statut"], "à vérifier", "page officielle non confirmée : rien n'est affirmé")

    def test_fidelite_d_une_ligne_a_la_reponse(self):
        rep = "1. Vente d'ananas découpés — investissement : 15 000 FCFA. Clients : bureaux et écoles."
        self.assertTrue(essai.fidele("Investissement : 15 000 FCFA", rep))
        self.assertTrue(essai.fidele("1. Ananas découpés", rep))
        self.assertFalse(essai.fidele("Investissement : 25 000 FCFA", rep), "un chiffre absent de la réponse")
        self.assertFalse(essai.fidele("Élevage d'escargots géants", rep))

    def test_extrait_mecanique(self):
        titre, lignes = essai.extrait_simple("Voici :\n1. Jus naturels en bouteille (bissap, gingembre)\n- Investissement : 25 000 FCFA\n2. Beignets du matin\n3. Savon liquide", 3)
        self.assertEqual(len(lignes), 3)
        self.assertTrue(all(len(x) <= schema.LIGNE_MAX for x in lignes))
        self.assertTrue(lignes[0].startswith("1. Jus naturels"))


class Bibliotheque(unittest.TestCase):
    def setUp(self):
        self.cfg, self.faits, self.st = cfg0(), faits_du_jour(), etat()
        self.fam = strategist.banque(ROOT)["familles"]

    def test_une_fiche_par_instruction_sans_doublon(self):
        st, _ = writer.controler(reserve("p1_business"), self.cfg, self.faits)
        st = essai.tester(st, self.cfg, None, self.faits, lambda *_: None)
        ids = bibliotheque.enregistrer(self.st, st, "v1", self.cfg, qualite_ok=True, familles=self.fam, log=lambda *_: None)
        self.assertEqual(ids, ["P-0001"])
        ids2 = bibliotheque.enregistrer(self.st, st, "v2", self.cfg, qualite_ok=True, familles=self.fam, log=lambda *_: None)
        self.assertEqual(ids2, ["P-0001"], "la même instruction pour le même outil ne fait qu'une fiche")
        lib = bibliotheque.charger(self.st)
        f = lib["fiches"][0]
        self.assertEqual([v["id"] for v in f["videos"]], ["v1", "v2"])
        self.assertEqual(f["statut"], "à vérifier", "sans essai réel, la fiche n'est pas validée, même si la vidéo est propre")
        for champ in ("id", "titre", "categorie", "outil", "fonction", "prompt", "exemple", "resultat_attendu", "personnalisation", "date_verification", "statut", "videos"):
            self.assertIn(champ, f)
        self.assertEqual(f["categorie"], "Business et entrepreneuriat")
        self.assertIn("50 000 FCFA", f["exemple"]["instruction_envoyee"])

    def test_statuts_a_verifier_teste_valide(self):
        st, _ = writer.controler(reserve("p2_consignes"), self.cfg, self.faits)
        st = essai.tester(st, self.cfg, None, self.faits, lambda *_: None)
        bibliotheque.enregistrer(self.st, st, "v1", self.cfg, qualite_ok=False, familles=self.fam, log=lambda *_: None)
        self.assertEqual(bibliotheque.charger(self.st)["fiches"][0]["statut"], "testé", "vérifiée, mais la vidéo n'a pas passé ses contrôles")
        bibliotheque.enregistrer(self.st, st, "v2", self.cfg, qualite_ok=True, publiee=True, familles=self.fam, log=lambda *_: None)
        f = bibliotheque.charger(self.st)["fiches"][0]
        self.assertEqual(f["statut"], "validé")
        self.assertTrue(f["videos"][-1]["publiee"])
        md = (Path(self.st.dir) / "BIBLIOTHEQUE.md").read_text(encoding="utf-8")
        for frag in ("# Bibliothèque de prompts", "P-0001", "Tes consignes permanentes pour ChatGPT", "page officielle relue", "**Prompt complet**", "Je m'appelle [prénom]", "**Personnalisation**"):
            self.assertIn(frag, md)
        sans = {k: v for k, v in self.faits.items() if k != "chatgpt-instructions"}
        st3 = essai.tester(st, self.cfg, None, sans, lambda *_: None)
        bibliotheque.enregistrer(self.st, st3, "v3", self.cfg, qualite_ok=True, familles=self.fam, log=lambda *_: None)
        self.assertEqual(bibliotheque.charger(self.st)["fiches"][0]["statut"], "validé", "un jour sans vérification ne défait pas une validation")


class Fin(unittest.TestCase):
    def test_fin_sans_ebook_tant_qu_il_n_est_pas_en_vente(self):
        cfg = cfg0()
        self.assertFalse(writer.ebook_actif(cfg), "l'e-book n'est pas encore en ligne : l'agent n'en parle pas")
        st, _ = writer.controler(reserve("p1_business"), cfg, faits_du_jour())
        fin = st["scenes"][-1]
        self.assertEqual(align.parse_say(fin["say"])[0], "Abonne-toi pour ne rien rater. Et commente BUSINESS si tu veux la suite : le prompt pour tes clients.")
        self.assertNotIn("promo", fin)
        self.assertNotIn("e-book", legende(st, cfg).lower())

    def test_ebook_annonce_seulement_s_il_est_en_vente_avec_un_lien(self):
        cfg = cfg0()
        cfg["offer"]["ebook"]["en_vente"] = True
        self.assertFalse(writer.ebook_actif(cfg), "sans lien en bio, on n'annonce rien")
        cfg["offer"]["lien_bio"] = "https://exemple.com/ebook"
        self.assertTrue(writer.ebook_actif(cfg))
        vues = set()
        for titre in ("a", "b", "c", "d", "e", "f"):
            phrase = writer.phrase_ebook(cfg, titre)
            vues.add(phrase)
            for info in ("e-book complet", "2 500 FCFA", "lien en bio"):
                self.assertIn(info, phrase, "les trois informations restent dans chaque variante")
        self.assertGreaterEqual(len(vues), 2, "la formulation varie d'une vidéo à l'autre")
        st, _ = writer.controler(reserve("p1_business"), cfg, faits_du_jour())
        fin = st["scenes"][-1]
        self.assertIn("[promo]", fin["say"]); self.assertIn("2 500 FCFA", fin["say"])
        self.assertEqual(fin["promo"], "E-book complet · *2 500 FCFA* · lien en bio")
        self.assertIn("La Bibliothèque ultime des prompts IA : 2 500 FCFA — lien en bio", legende(st, cfg))

    def test_legende_structure(self):
        cfg = cfg0()
        st, _ = writer.controler(reserve("p1_business"), cfg, faits_du_jour())
        txt = packs(st, cfg, "Images : Pexels (Ana B.)")["facebook"]["legende"]
        for frag in ("1️⃣", "📋 Le prompt à copier (ChatGPT) :\nAgis comme un consultant", "Ne propose pas de revenus garantis.", "⚠️ L'IA ne connaît pas ton quartier",
                     "💬 Commente BUSINESS si tu veux la suite : le prompt pour tes clients", "🔔 Abonne-toi", "#ChatGPT", "Images : Pexels (Ana B.)"):
            self.assertIn(frag, txt)
        st2, _ = writer.controler(reserve("p2_consignes"), cfg, faits_du_jour())
        self.assertIn("📋 Le texte à coller (ChatGPT) :", legende(st2, cfg))


class Timeline(unittest.TestCase):
    def test_reperes_blocs_sous_titres_et_durees_des_rushs(self):
        cfg = cfg0()
        st, _ = writer.controler(reserve("p1_business"), cfg, faits_du_jour())
        b = timeline.build(st, voix(st), cfg)
        tl = b["timeline"]
        self.assertEqual([s["type"] for s in tl["scenes"]], ["ecran"] * 5 + ["fin"])
        self.assertEqual(tl["scenes"][0]["blocks"][0]["at"], 0.0, "le premier bloc est à l'image dès la première image")
        for a, c in zip(tl["scenes"], tl["scenes"][1:]):
            self.assertAlmostEqual(a["t1"], c["t0"], places=2)
        pr = tl["scenes"][1]["blocks"][0]
        self.assertEqual(pr["kind"], "prompt")
        self.assertEqual(pr["outil"], "ChatGPT")
        self.assertTrue(pr["texte"].startswith("Agis comme un consultant"))
        self.assertTrue(pr["at"] < pr["typeAt"] < pr["typeEnd"] < tl["scenes"][1]["t1"] - 1.0, "le texte complet reste lisible après la frappe")
        rp = tl["scenes"][3]["blocks"][0]
        self.assertEqual(rp["kind"], "reponse")
        self.assertEqual(len(rp["lineAt"]), 5)
        self.assertTrue(all(x < y for x, y in zip(rp["lineAt"], rp["lineAt"][1:])))
        self.assertTrue(rp["at"] < rp["lineAt"][0] and rp["lineAt"][-1] < tl["scenes"][3]["t1"])
        self.assertEqual(set(b["rushs"]), set(schema.refs_in(st)))
        for ref, need in b["rushs"].items():
            self.assertGreater(need["duree"], 2.0)
        fin = tl["scenes"][-1]
        self.assertTrue(fin["t0"] < fin["clickAt"] < fin["boxAt"] < fin["kwAt"] < fin["promesseAt"] < fin["t1"])
        caps = tl["captions"]
        self.assertTrue(all(len(g["words"]) <= 4 for g in caps), "sous-titres courts : trois mots, quatre quand un petit mot serait resté seul")
        self.assertTrue(all(a["t1"] <= c["t0"] for a, c in zip(caps, caps[1:])), "les sous-titres ne se chevauchent pas")
        self.assertEqual(tl["cover"]["lines"], ["UN BUSINESS", "AVEC", "*TON BUDGET*"])
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
        st = reserve("p1_business")
        st["scenes"][0]["say"] = "Erreur numéro un : tu lances un business sans savoir quoi vendre. [a]Copie ce prompt dans ChatGPT, il te propose cinq activités."
        besoins = rushs.besoins_de(schema.normaliser(st)[0])
        self.assertTrue(besoins[0]["sensible"], "un passage qui parle d'une erreur est un passage négatif")

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
        self.assertIn("chatgpt-instructions", scout.faits_confirmes(ROOT, st, today="2026-12-01"))
        self.assertNotIn("chatgpt-instructions", scout.faits_confirmes(ROOT, st, today="2027-03-01"))

    def test_fait_automatique_suspendu_si_la_phrase_disparait(self):
        st = etat()
        logs = []
        scout.verifier_faits(ROOT, st, logs.append, force=True, fetch=lambda url: (200, "page réécrite, plus rien d'attendu"))
        ok = scout.faits_confirmes(ROOT, st)
        self.assertNotIn("remotion-principe", ok)
        self.assertNotIn("claude-code-commandes", ok, "si la page officielle ne montre plus la commande, l'agent n'en parle plus")
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

    def post(self, pid, idee, reserve_=None, famille="prompts", score=None, days=0, **extra):
        at = (now() - dt.timedelta(days=days)).isoformat(timespec="seconds")
        p = {"id": pid, "created": at, "title": f"vidéo {pid}", "keyword": "MOT", "duration": 46, "brief": {"idee": idee, "famille": famille, "hook_type": "resultat", "slot": "soir",
             **({"reserve": reserve_} if reserve_ else {})}, "published": {"facebook": {"status": "sent"}}, "stats": {}, **extra}
        if score is not None:
            p["score"] = score
        self.st.add_post(p)
        return p

    def test_la_banque_suit_la_repartition_demandee(self):
        bq = strategist.banque(ROOT)
        brut = {f["id"]: f for f in __import__("yaml").safe_load((ROOT / "data" / "sujets.yaml").read_text(encoding="utf-8"))["familles"]}
        self.assertEqual({k: f["poids"] for k, f in brut.items()},
                         {"prompts": 0.25, "commandes": 0.15, "business": 0.15, "images": 0.15, "video": 0.10, "etudes": 0.10, "hashtags": 0.05, "outils": 0.05})
        self.assertAlmostEqual(sum(f["poids"] for f in brut.values()), 1.0)
        self.assertEqual(set(brut), set(schema.FAMILLES))
        tous = __import__("yaml").safe_load((ROOT / "data" / "sujets.yaml").read_text(encoding="utf-8"))["idees"]
        self.assertEqual(len(tous), 20, "les 20 premiers sujets prioritaires")
        self.assertEqual(len([i for i in tous if i.get("pilote")]), 6, "dont six pour la série pilote")
        self.assertIn("images", bq["en_attente"], "la famille « images » attend une clé de création d'images")
        self.assertNotIn("images", bq["familles"])
        self.assertTrue(all(i["famille"] != "images" for i in bq["idees"]))
        w = strategist.poids(ROOT, self.st)
        self.assertAlmostEqual(sum(w.values()), 1.0, places=6)
        self.assertNotIn("images", w)
        self.assertGreater(w["prompts"], w["commandes"])

    def test_essai_les_reserves_tournent_sans_rien_consommer(self):
        vus = []
        for n in range(len(self.res)):
            self.st.save("essais", {"n": n})
            vus.append(strategist.choisir(ROOT, self.st, self.cfg, self.faits, random.Random(1), True, False, self.res)["reserve"])
        self.assertEqual(sorted(vus), sorted(self.res))

    def test_sans_modele_seulement_les_reserves_puis_rien(self):
        c = strategist.choisir(ROOT, self.st, self.cfg, self.faits, random.Random(3), False, False, self.res)
        self.assertIn(c["reserve"], self.res)
        for i in strategist.banque(ROOT)["idees"]:
            if i.get("reserve"):
                self.post("p-" + i["id"], i["id"], i["reserve"], i["famille"])
        self.assertIsNone(strategist.choisir(ROOT, self.st, self.cfg, self.faits, random.Random(3), False, False, self.res))
        self.assertIsNotNone(strategist.choisir(ROOT, self.st, self.cfg, self.faits, random.Random(3), False, True, self.res), "avec un modèle, les autres idées s'ouvrent")

    def test_la_serie_pilote_passe_d_abord(self):
        faits = {s_ for s_ in ()}
        for seed in range(25):
            c = strategist.choisir(ROOT, self.st, self.cfg, self.faits, random.Random(seed), False, True, self.res)
            self.assertTrue(c["idee"].get("pilote"), c["idee"]["id"])
        for i in strategist.banque(ROOT)["idees"]:
            if i.get("pilote"):
                self.post("p-" + i["id"], i["id"], None, i["famille"])
        c = strategist.choisir(ROOT, self.st, self.cfg, self.faits, random.Random(2), False, True, self.res)
        self.assertFalse(c["idee"].get("pilote"), "la série pilote terminée, la banque continue")

    def test_la_video_suivante_est_choisie_d_avance_et_tenue(self):
        """Chaque vidéo annonce la suivante ; ce sujet vient de la banque (donc de la répartition), et il est produit ensuite."""
        nxt = strategist.prochaine(ROOT, self.st, self.cfg, self.faits, random.Random(4), True, self.res, exclure={"s10"})
        self.assertIsNotNone(nxt)
        self.assertNotEqual(nxt["id"], "s10")
        p = self.post("p1", "s10", "p1_business", "business")
        strategist.noter_suite(self.st, p, reserve("p1_business"))            # annonce « s11 : l'annonce qui attire des clients »
        sans_modele = strategist.choisir(ROOT, self.st, self.cfg, self.faits, random.Random(5), False, False, self.res)
        self.assertNotIn("suite_de", sans_modele, "sans modèle, la suite (qui n'a pas de réserve) attend ; la réserve restante passe")
        self.assertEqual(sans_modele["reserve"], "p2_consignes")
        c = strategist.choisir(ROOT, self.st, self.cfg, self.faits, random.Random(5), False, True, self.res)
        self.assertEqual(c["suite_de"], "p1")
        self.assertEqual(c["idee"]["id"], "s11")
        self.assertEqual(c["famille"], "business")
        strategist.marquer_suite(self.st, "p1", "p2")
        c2 = strategist.choisir(ROOT, self.st, self.cfg, self.faits, random.Random(5), False, True, self.res)
        self.assertNotIn("suite_de", c2)

    def test_idee_sans_fait_confirme_ecartee(self):
        faits = {k: v for k, v in self.faits.items() if not k.startswith(("chatgpt", "claude"))}
        for seed in range(30):
            c = strategist.choisir(ROOT, self.st, self.cfg, faits, random.Random(seed), False, True, self.res)
            self.assertEqual(c["idee"].get("faits") or [], [], "un sujet « commandes » sans page officielle confirmée n'est pas choisi")

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
        for fam, score in (("business", 1.2), ("prompts", -0.8), ("etudes", 0.1)):
            for _ in range(n_par_famille):
                k += 1
                at = (now() - dt.timedelta(days=4)).isoformat(timespec="seconds")
                self.st.add_post({"id": f"p{k}", "created": at, "title": f"{fam} {k}", "keyword": "MOT", "duration": 44 if fam == "business" else 62,
                                  "brief": {"idee": f"i{k}", "famille": fam, "hook_type": "probleme" if fam == "business" else "resultat", "slot": "soir"},
                                  "published": {"facebook": {"status": "sent", "id": "x", "at": at}}, "score": score,
                                  "stats": {"facebook": [{"h": 30, "views": 1000 + 100 * k, "comments": k}]}})

    def test_pas_de_conclusion_sur_du_bruit(self):
        self.remplir(1)
        strategist.score_posts = lambda *_: None
        r = bilan.faire(self.st, self.cfg, ROOT, None, lambda *_: None)
        self.assertEqual({k: round(v, 4) for k, v in r["poids"].items()}, r["poids_avant"])
        self.assertIn("Rien n'est changé", r["constats"][0])

    def test_les_poids_bougent_dans_des_bornes(self):
        self.remplir(3)
        strategist.score_posts = lambda *_: None
        avant = strategist.poids(ROOT, self.st)
        r = bilan.faire(self.st, self.cfg, ROOT, None, lambda *_: None)
        self.assertGreater(r["poids"]["business"], avant["business"])
        self.assertLess(r["poids"]["prompts"], avant["prompts"])
        self.assertAlmostEqual(sum(r["poids"].values()), 1.0, places=2)
        self.assertGreaterEqual(min(r["poids"].values()), 0.029, "aucune famille ne disparaît")
        self.assertLess(r["poids"]["business"] / avant["business"], 1.6, "pas de virage brutal")
        self.assertAlmostEqual(strategist.poids(ROOT, self.st)["business"], r["poids"]["business"], places=3, msg="le stratège lit les nouveaux poids")
        md = (Path(self.st.dir) / "BILAN.md").read_text(encoding="utf-8")
        for frag in ("# Bilan du", "Décisions prises par l'agent", "Par accroche", "Business et entrepreneuriat"):
            self.assertIn(frag, md)
        self.assertTrue(any(i.get("origine") == "bilan" for i in self.st.load("idees", [])), "la meilleure vidéo donne une variante")
        self.assertFalse(bilan.du(self.st, self.cfg), "le bilan suivant attend 3 jours")


class Porte(unittest.TestCase):
    def test_ce_qui_retient_une_video(self):
        cfg, faits = cfg0(), faits_du_jour()
        st, _ = writer.controler(reserve("p2_consignes"), cfg, faits)
        self.assertTrue(porte.bloquants(cfg, st, {"ok": True}, faits), "avant vérification, rien ne part")
        st = essai.tester(st, cfg, None, faits, lambda *_: None)
        self.assertEqual(porte.bloquants(cfg, st, {"ok": True}, faits), [])
        self.assertTrue(porte.bloquants(cfg, st, {"ok": False, "problems": ["durée 120 s"]}, faits))
        self.assertTrue(porte.bloquants(cfg, st, {"ok": True}, {k: v for k, v in faits.items() if k != "chatgpt-instructions"}))


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
        for frag in ("## 1. Stratégie", "## 2. Instructions montrées (bibliothèque de prompts)", "## 3. Séquences filmées et droits", "## 4. Script minuté",
                     "## 6. Contrôle avant publication", "**Instructions vérifiées**", "l'e-book n'est pas annoncé"):
            self.assertIn(frag, fiche_md)
        self.assertTrue(any("MODE ESSAI" in l for l in self.run.LINES))
        self.assertEqual(post["prompts"], ["P-0001"], "l'instruction de la vidéo est rangée dans la bibliothèque, même en essai")
        self.assertTrue((Path(self.st.dir) / "BIBLIOTHEQUE.md").exists())

    def test_publication_reelle_sans_validation_humaine(self):
        os.environ["BUFFER_API_KEY"] = "cle"
        envois = []
        self.run._host = lambda post_id, res, cfg, state: f"https://exemple.github.io/v/{post_id}.mp4"

        def faux_envoi(video, story, thumb_ms, public_url, cfg, state, log=print, credit=""):
            envois.append((public_url, credit, story["title"]))
            return {"facebook": {"status": "sent", "id": "fb1", "via": "buffer", "at": now().isoformat(timespec="seconds")}}
        self.run.publish_all = faux_envoi
        # un réglage vérifié sur la page officielle : il part seul, sans attente de validation
        post = self.run.make_one(self.st, self.cfg, "18:00", story=json.loads((ROOT / "examples" / "reserve" / "p2_consignes.json").read_text(encoding="utf-8")))
        self.assertEqual(len(envois), 1)
        self.assertEqual(envois[0][1], "Images : Pexels")
        self.assertEqual([p["id"] for p in self.st.posts], [post["id"]])
        suites = self.st.load("suites", [])
        self.assertEqual(suites[0]["suite"]["idee"], "s18", "la suite annoncée est inscrite, avec son sujet de la banque")
        fiche_lib = bibliotheque.charger(self.st)["fiches"][0]
        self.assertEqual(fiche_lib["statut"], "validé")
        self.assertTrue(fiche_lib["videos"][-1]["publiee"])
        # un prompt jamais testé (aucune clé Gemini) : la vidéo est fabriquée mais ne part pas
        post2 = self.run.make_one(self.st, self.cfg, "20:30", story=json.loads((ROOT / "examples" / "reserve" / "p1_business.json").read_text(encoding="utf-8")))
        self.assertEqual(len(envois), 1, "un prompt non testé n'est jamais publié")
        self.assertEqual(len(self.st.posts), 1)
        self.assertTrue(any("PUBLICATION RETENUE" in l and "instruction non vérifiée" in l for l in self.run.LINES))
        self.assertEqual(post2["prompts"], ["P-0002"])

    def test_controle_qualite_en_echec_rien_ne_part(self):
        os.environ["BUFFER_API_KEY"] = "cle"
        vrai = self.run.produce.make_video

        def rate(*a, **k):
            r = vrai(*a, **k)
            r["qa"] = {"ok": False, "problems": ["voix couverte par le fond sonore"], "warnings": []}
            return r
        self.run.produce.make_video = rate
        self.run.publish_all = lambda *a, **k: self.fail("rien ne doit partir")
        post = self.run.make_one(self.st, self.cfg, "18:00", story=reserve("p2_consignes"))
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
