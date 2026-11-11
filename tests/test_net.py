"""Tests avec de faux serveurs : Gemini (catalogue, quotas, correction), banques de rushs, Buffer, relevé des statistiques.

    python3 -m unittest discover -s tests
"""
import datetime as dt
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from studio import config, llm, rushs, scout, writer  # noqa: E402
from studio.publish import publish_all  # noqa: E402
from studio.publish.buffer import Buffer, Enum, lit  # noqa: E402
from studio.state import State, now  # noqa: E402

SEEN: list[dict] = []
SCRIPT: dict[str, list] = {}          # modèle -> réponses successives (code, texte ou corps d'erreur)
CATALOGUE = ["gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-3.1-pro-preview", "gemini-3.8-flash-tts", "gemini-embedding-2"]
CLES = ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GROQ_API_KEY", "PEXELS_API_KEY", "PIXABAY_API_KEY", "BUFFER_API_KEY", "FB_PAGE_TOKEN", "IG_TOKEN", "TIKTOK_REFRESH_TOKEN")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        raw = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(raw)))
        self.end_headers(); self.wfile.write(raw)

    def do_GET(self):
        if self.path.startswith("/v1beta/models"):
            SEEN.append({"path": self.path, "key": self.headers.get("x-goog-api-key")})
            return self._send(200, {"models": [{"name": f"models/{m}", "supportedGenerationMethods": ["generateContent"]} for m in CATALOGUE]})
        self._send(404, {})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        SEEN.append({"path": self.path, "body": body, "key": self.headers.get("x-goog-api-key"), "auth": self.headers.get("Authorization")})
        if self.path.startswith("/buffer"):
            q = body["query"]
            if "organizations" in q:
                return self._send(200, {"data": {"account": {"organizations": [{"id": "org1"}]}}})
            if "channels(" in q:
                return self._send(200, {"data": {"channels": [{"id": "c_tt", "name": "moi", "service": "tiktok"},
                                                              {"id": "c_ig", "name": "moi", "service": "instagram"}]}})
            if "createPost" in q:
                if "c_ig" in q and "type: reel" not in q:
                    return self._send(200, {"data": {"createPost": {"message": "type manquant"}}})
                return self._send(200, {"data": {"createPost": {"post": {"id": "post_" + ("tt" if "c_tt" in q else "ig"), "status": "sending", "dueAt": None}}}})
            if "metrics" in q:
                return self._send(200, {"data": {"post": {"id": "x", "status": "sent", "metricsUpdatedAt": "2026-11-12T10:00:00Z",
                                 "metrics": [{"type": "views", "value": 1234.0, "unit": "count"}, {"type": "reactions", "value": 80.0, "unit": "count"},
                                             {"type": "comments", "value": 12.0, "unit": "count"}, {"type": "saves", "value": 30.0, "unit": "count"}]}}})
            return self._send(200, {"data": {"post": {"id": "x", "status": "sent"}}})
        if ":generateContent" in self.path:
            model = self.path.split("/models/")[1].split(":")[0]
            step = SCRIPT[model].pop(0) if SCRIPT.get(model) else (200, "{}")
            code, content = step
            if code != 200:
                return self._send(code, content if isinstance(content, dict) else {"error": {"message": str(content)}})
            return self._send(200, {"candidates": [{"content": {"role": "model", "parts": [{"text": "réflexion", "thought": True}, {"text": content}]}, "finishReason": "STOP"}]})
        self._send(404, {})


class Net(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = HTTPServer(("127.0.0.1", 0), Handler)
        cls.url = f"http://127.0.0.1:{cls.srv.server_port}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        for k in CLES + ("GEMINI_BASE_URL", "BUFFER_API_URL"):
            os.environ.pop(k, None)

    def setUp(self):
        SEEN.clear(); SCRIPT.clear()
        for k in CLES:
            os.environ.pop(k, None)
        os.environ.update({"GEMINI_BASE_URL": self.url + "/v1beta", "GEMINI_API_KEY": "cle-gemini", "BUFFER_API_URL": self.url + "/buffer", "BUFFER_API_KEY": "bk"})
        self.state = State(Path(tempfile.mkdtemp()))
        self.cfg = config.load()
        llm.time.sleep = lambda *_: None

    def brain(self):
        return llm.Brain(self.cfg, self.state, lambda *_: None)

    # ------------------------------------------------------------------ Gemini
    def test_choix_des_modeles_dans_le_catalogue(self):
        b = self.brain()
        self.assertEqual(b.modeles("ecriture"), ["gemini-3.8-flash", "gemini-3.5-flash-lite"], "ni « pro » (payant), ni voix, ni plongements")
        self.assertEqual(b.modeles("controle"), ["gemini-3.5-flash-lite", "gemini-3.8-flash"])
        self.assertEqual(SEEN[0]["key"], "cle-gemini")

    def test_quota_du_jour_bascule_sur_le_modele_suivant_et_s_en_souvient(self):
        SCRIPT["gemini-3.8-flash"] = [(429, {"error": {"message": "quota", "details": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}})]
        SCRIPT["gemini-3.5-flash-lite"] = [(200, '{"ok": true}')]
        b = self.brain()
        self.assertEqual(b.ask_json("s", "u"), {"ok": True})
        self.assertEqual(b.used, ["gemini/gemini-3.5-flash-lite"])
        self.assertEqual(self.brain().modeles("ecriture"), ["gemini-3.5-flash-lite"], "le modèle épuisé n'est plus sollicité aujourd'hui")

    def test_reponse_refusee_puis_corrigee(self):
        SCRIPT["gemini-3.8-flash"] = [(200, '{"n": 1}'), (200, '```json\n{"n": 2}\n```')]

        def valider(o):
            if o["n"] < 2:
                raise ValueError("n doit valoir au moins 2")
            return o
        b = self.brain()
        self.assertEqual(b.ask_json("système", "question", validate=valider), {"n": 2})
        posts = [s for s in SEEN if "generateContent" in s["path"]]
        self.assertEqual(len(posts), 2)
        tours = posts[1]["body"]["contents"]
        self.assertEqual([t["role"] for t in tours], ["user", "model", "user"])
        self.assertIn("n doit valoir au moins 2", tours[2]["parts"][0]["text"])
        self.assertEqual(posts[0]["body"]["systemInstruction"]["parts"][0]["text"], "système")
        self.assertEqual(posts[0]["body"]["generationConfig"]["responseMimeType"], "application/json")

    def test_images_envoyees_au_modele_de_controle(self):
        SCRIPT["gemini-3.5-flash-lite"] = [(200, json.dumps({"sequences": [{"n": 1, "montre": "un chat sur un piano", "note": 2, "texte_ou_logo": False,
                                                                        "visage_reconnaissable": False, "image_de_synthese": False}]}))]
        v = rushs.controle_vision(self.brain(), [{"id": "r1|px-1", "attendu": "des mains qui tapent sur un clavier", "phrase": "Étape un : le script.", "images": [b"\xff\xd8a", b"\xff\xd8b"]}])
        self.assertEqual(v["r1|px-1"]["note"], 2)
        post = [s for s in SEEN if "generateContent" in s["path"]][0]
        self.assertIn("gemini-3.5-flash-lite", post["path"])
        parts = post["body"]["contents"][0]["parts"]
        self.assertEqual(len([p for p in parts if "inlineData" in p]), 2)

    def test_plafond_par_video_et_par_jour(self):
        self.cfg["llm"]["max_calls_per_video"] = 2
        b = self.brain()
        SCRIPT["gemini-3.8-flash"] = [(200, '{"a": 1}')] * 3
        b.ask_json("s", "u"); b.ask_json("s", "u")
        with self.assertRaises(llm.LLMError):
            b.ask_json("s", "u")
        self.cfg["llm"]["max_par_jour"] = 2
        with self.assertRaises(llm.LLMError):
            self.brain().ask_json("s", "u")

    def test_storyboard_ecrit_par_le_modele_refuse_puis_accepte(self):
        """Le modèle promet un revenu : refus renvoyé ; il corrige : accepté, avec l'écran de fin ajouté par l'agent."""
        bon = json.loads((ROOT / "examples" / "reserve" / "p1_business.json").read_text(encoding="utf-8"))
        bon["suite"] = {"sujet": "Le prompt pour rédiger une annonce qui attire des clients"}
        mauvais = json.loads(json.dumps(bon))
        mauvais["scenes"][1]["say"] += " Avec ça, tu vas gagner de l'argent."
        SCRIPT["gemini-3.8-flash"] = [(200, json.dumps(mauvais)), (200, json.dumps(bon))]
        faits = scout.faits_confirmes(ROOT, self.state, today="2026-11-11")
        st = writer.write(self.brain(), {"id": "s10", "famille": "business", "hook_type": "question", "sujet": "Le prompt pour trouver une idée de business", "outil": "ChatGPT",
                                         "prochaine": {"id": "s11", "sujet": "Le prompt pour rédiger une annonce qui attire des clients"}}, faits, self.cfg, "", lambda *_: None)
        self.assertEqual(st["scenes"][-1]["type"], "fin")
        self.assertEqual(st["idee"], "s10")
        self.assertEqual(st["suite"]["idee"], "s11", "la suite annoncée est le sujet déjà choisi dans la banque")
        self.assertEqual(st["prompts"][0]["outil"], "ChatGPT")
        posts = [s for s in SEEN if "generateContent" in s["path"]]
        self.assertIn("promesse de revenu", posts[1]["body"]["contents"][2]["parts"][0]["text"])
        consigne = posts[0]["body"]["systemInstruction"]["parts"][0]["text"]
        for frag in ("RÈGLES DE VÉRITÉ", "PROMPTS, les COMMANDES et les TECHNIQUES", "Copie exactement cette instruction", "N'invente jamais une commande"):
            self.assertIn(frag, consigne)
        self.assertIn("LA VIDÉO SUIVANTE du compte sera", posts[0]["body"]["contents"][0]["parts"][0]["text"])

    def test_essai_reel_du_prompt_sur_gemini(self):
        """Le prompt est envoyé tel quel (aucune consigne, texte libre) ; l'écran « réponse » montre un extrait de la VRAIE réponse."""
        from studio import essai, porte
        faits = scout.faits_confirmes(ROOT, self.state, today="2026-11-11")
        st, _ = writer.controler(json.loads((ROOT / "examples" / "reserve" / "p1_business.json").read_text(encoding="utf-8")), self.cfg, faits)
        vraie = ("Voici 5 pistes pour Cotonou avec 50 000 FCFA.\n\n1. Vente d'ananas découpés\n- Investissement : 15 000 FCFA\n2. Recharge de crédit téléphonique\n"
                 "3. Couture de masques et sacs en pagne\n4. Lavage de motos à domicile\n5. Revente de poissons fumés\n\nPour les ananas : clients = bureaux et écoles ; "
                 "risque = les fruits abîmés ; premier pas = tester sur 10 ananas.")
        SCRIPT["gemini-3.8-flash"] = [(200, vraie)]
        infidele = {"titre": "5 idées pour Cotonou", "lignes": ["1. Ananas découpés", "2. Crédit téléphonique", "3. Masques et sacs en pagne", "4. Lavage de motos", "5. Élevage d'escargots géants"],
                    "dit": "[a]Voici la réponse : [a1]des ananas, [a2]du crédit, [a3]des sacs en pagne, [a4]le lavage de motos [a5]et des escargots. Vérifie toujours les prix."}
        fidele = json.loads(json.dumps(infidele)); fidele["lignes"][4] = "5. Revente de poissons fumés"
        fidele["dit"] = infidele["dit"].replace("des escargots", "du poisson fumé")
        detail = {"titre": "Idée 1 : ananas découpés", "lignes": ["Investissement : 15 000 FCFA", "Clients : bureaux et écoles", "Risque : les fruits abîmés", "Premier pas : tester sur 10 ananas"],
                  "dit": "Pour chaque idée, l'IA détaille [a1]l'investissement, [a2]les clients, [a3]le risque [a4]et le premier pas. Ses chiffres sont des estimations : vérifie les prix."}
        SCRIPT["gemini-3.5-flash-lite"] = [(200, json.dumps(infidele)), (200, json.dumps(fidele)), (200, json.dumps(detail))]
        out = essai.tester(st, self.cfg, self.brain(), faits, lambda *_: None, today="2026-11-11")
        f = out["prompts"][0]
        self.assertEqual((f["statut"], f["verification"]), ("testé", "essai réel"))
        self.assertIn("Gemini", f["teste_sur"]); self.assertIn("ananas", f["resultat_exemple"])
        posts = [x for x in SEEN if "generateContent" in x["path"]]
        envoi = posts[0]["body"]
        self.assertNotIn("systemInstruction", envoi, "l'instruction est envoyée seule, comme le ferait un utilisateur")
        self.assertNotIn("responseMimeType", envoi["generationConfig"])
        self.assertTrue(envoi["contents"][0]["parts"][0]["text"].startswith("Agis comme un consultant"))
        self.assertIn("Je vis à Cotonou et je dispose d'un capital de 50 000 FCFA", envoi["contents"][0]["parts"][0]["text"], "les [champs] sont remplis par l'exemple")
        self.assertIn("ligne infidèle", posts[2]["body"]["contents"][2]["parts"][0]["text"], "une ligne absente de la vraie réponse est refusée et renvoyée au modèle")
        blocs = [b for sc in out["scenes"] for b in sc.get("blocks") or [] if b.get("kind") == "reponse"]
        self.assertEqual(blocs[0]["lignes"][4], "5. Revente de poissons fumés")
        self.assertEqual(blocs[1]["titre"], "Idée 1 : ananas découpés")
        self.assertTrue(all(b["source"] == "Réponse de Gemini · testée le 11/11/2026" for b in blocs))
        self.assertIn("poisson fumé", out["scenes"][3]["say"], "la voix suit les vraies lignes")
        st2, pb = writer.controler(out, self.cfg, faits, strict=False)
        self.assertEqual(pb, [], "le storyboard mis à jour repasse tous les contrôles")
        self.assertEqual(porte.bloquants(self.cfg, st2, {"ok": True}, faits), [], "un prompt testé le jour même peut partir")

    def test_essai_impossible_le_prompt_est_rejete_et_la_video_retenue(self):
        from studio import essai, porte
        faits = scout.faits_confirmes(ROOT, self.state, today="2026-11-11")
        st, _ = writer.controler(json.loads((ROOT / "examples" / "reserve" / "p1_business.json").read_text(encoding="utf-8")), self.cfg, faits)
        SCRIPT["gemini-3.8-flash"] = [(400, "requête refusée")]
        SCRIPT["gemini-3.5-flash-lite"] = [(400, "requête refusée")]
        out = essai.tester(st, self.cfg, self.brain(), faits, lambda *_: None)
        self.assertEqual(out["prompts"][0]["statut"], "rejeté")
        self.assertTrue(any("instruction non vérifiée" in b for b in porte.bloquants(self.cfg, out, {"ok": True}, faits)))

    # ------------------------------------------------------------------ banques de rushs
    def test_pexels_et_pixabay_lus_selon_leur_documentation(self):
        os.environ.update({"PEXELS_API_KEY": "kp", "PIXABAY_API_KEY": "kx"})
        appels = []

        class Rep:
            def __init__(self, obj): self.obj = obj
            def raise_for_status(self): pass
            def json(self): return self.obj

        class Http:
            @staticmethod
            def get(url, params=None, headers=None, timeout=0):
                appels.append((url, params, headers))
                if "pexels" in url:
                    return Rep({"videos": [{"id": 2499611, "width": 1080, "height": 1920, "url": "https://www.pexels.com/video/hands-packing-a-box-2499611/", "duration": 22,
                                            "user": {"id": 1, "name": "Joey Farina", "url": "https://www.pexels.com/@joey"},
                                            "video_files": [{"id": 1, "quality": "hd", "file_type": "video/mp4", "width": 1080, "height": 1920, "link": "https://cdn/hd.mp4"},
                                                            {"id": 2, "quality": "sd", "file_type": "video/mp4", "width": 540, "height": 960, "link": "https://cdn/sd.mp4"},
                                                            {"id": 3, "quality": "hls", "file_type": "application/x-mpegURL", "width": None, "height": None, "link": "https://cdn/x.m3u8"}]}]})
                return Rep({"hits": [{"id": 125, "pageURL": "https://pixabay.com/videos/id-125/", "tags": "box, packing, hands", "duration": 12, "user": "Coverr",
                                      "videos": {"large": {"url": "", "width": 0, "height": 0, "size": 0}, "medium": {"url": "https://cdn/m.mp4", "width": 1920, "height": 1080},
                                                 "small": {"url": "https://cdn/s.mp4", "width": 1280, "height": 720}}},
                                     {"id": 126, "pageURL": "https://pixabay.com/videos/id-126/", "tags": "ai generated, box", "duration": 8, "user": "x",
                                      "videos": {"medium": {"url": "https://cdn/ia.mp4", "width": 1080, "height": 1920}}}]})
        got = rushs.chercher("hands packing box", "portrait", self.state, lambda *_: None, Http)
        self.assertEqual(appels[0][0], "https://api.pexels.com/v1/videos/search")
        self.assertEqual(appels[0][2]["Authorization"], "kp")
        self.assertEqual(appels[0][1]["orientation"], "portrait")
        self.assertEqual(appels[1][0], "https://pixabay.com/api/videos/")
        self.assertEqual(appels[1][1]["key"], "kx")
        px = next(c for c in got if c["id"] == "px-2499611")
        self.assertEqual((px["url"], px["auteur"], px["w"], px["h"]), ("https://cdn/hd.mp4", "Joey Farina", 1080, 1920))
        self.assertIn("packing", px["tags"])
        pb = next(c for c in got if c["id"] == "pb-125")
        self.assertEqual(pb["url"], "https://cdn/m.mp4")
        ok = [c["id"] for _, c in rushs.classer({"q": "hands packing box", "cadre": "portrait"}, got)]
        self.assertEqual(ok[0], "px-2499611")
        self.assertNotIn("pb-126", ok, "une image générée par IA n'est pas un rush")
        rushs.chercher("hands packing box", "portrait", self.state, lambda *_: None, Http)
        self.assertEqual(len(appels), 2, "même recherche dans les 24 h : pas de nouvel appel aux banques")

    def test_le_modele_refuse_un_rush_hors_sujet(self):
        """Deux séquences candidates : le modèle voit que la première ne montre pas ce qui est dit -> la seconde est prise."""
        self.cfg["rushs"]["candidats_regardes"] = 2
        lib = rushs.bibliotheque(ROOT)
        vrai = (rushs.telecharger, rushs.analyser, rushs.temoins)
        rushs.telecharger = lambda c, cache, http=None: Path(f"/tmp/{c['id']}.mp4")
        rushs.analyser = lambda f: {"ok": True, "problemes": [], "w": 1080, "h": 1920, "fps": 30, "dur": 10, "nettete": 300, "mouvement": 8, "luminosite": 120}
        rushs.temoins = lambda f, n=3, w=384: [b"\xff\xd8x"] * 3
        try:
            besoin = {"ref": "r2a", "q": "phone tripod filming", "voir": "un téléphone sur trépied", "cadre": "portrait", "phrase": "Pose ton téléphone.", "sensible": False}
            rows = [c["id"] for s, c in rushs.classer(besoin, lib)][:2]
            SCRIPT["gemini-3.5-flash-lite"] = [(200, json.dumps({"sequences": [
                {"n": 1, "montre": "un plan flou sans téléphone", "note": 3, "texte_ou_logo": False, "visage_reconnaissable": False, "image_de_synthese": False},
                {"n": 2, "montre": "un téléphone sur un trépied", "note": 9, "texte_ou_logo": False, "visage_reconnaissable": False, "image_de_synthese": False}]}))]
            logs = []
            got = rushs.choisir([besoin], self.cfg, self.state, self.brain(), ROOT, logs.append)
            self.assertEqual(got["r2a"]["id"], rows[1])
            self.assertIn("note 9/10", got["r2a"]["controle"])
            self.assertTrue(any("refusée" in l and rows[0] in l for l in logs))
        finally:
            rushs.telecharger, rushs.analyser, rushs.temoins = vrai

    # ------------------------------------------------------------------ Buffer et mesures
    def test_litteral_graphql(self):
        self.assertEqual(lit({"a": Enum("automatic"), "b": "x\"y", "c": [1, True], "d": None}), '{a: automatic, b: "x\\"y", c: [1, true]}')

    def test_buffer_publication_et_stats(self):
        import studio.publish as P
        P.time.sleep = lambda *_: None
        cfg = {"publish": {"dry_run": False, "via": "buffer", "networks": ["tiktok", "instagram", "facebook"], "ai_label": True, "hashtags": 3}, "offer": {}}
        st, _ = writer.controler(json.loads((ROOT / "examples" / "reserve" / "p1_business.json").read_text(encoding="utf-8")), self.cfg, {})
        out = publish_all("/tmp/x.mp4", st, 2400, "https://moi.github.io/agent/v/x.mp4", cfg, self.state, lambda *_: None, "Images : Pexels")
        self.assertEqual(out["tiktok"]["status"], "sent"); self.assertEqual(out["tiktok"]["id"], "post_tt")
        self.assertEqual(out["instagram"]["status"], "sent")
        self.assertEqual(out["facebook"]["status"], "skipped", "pas de canal Facebook dans Buffer ni de jeton natif -> ignoré, sans bloquer les autres")
        creates = [s["body"]["query"] for s in SEEN if "createPost" in s["body"].get("query", "")]
        self.assertEqual(len(creates), 2)
        tt = next(q for q in creates if "c_tt" in q)
        for frag in ('schedulingType: automatic', 'mode: shareNow', 'url: "https://moi.github.io/agent/v/x.mp4"', 'thumbnailOffset: 2400',
                     'tiktok: {isAiGenerated: true}', '#ChatGPT #PromptIA #IA', 'Commente BUSINESS', 'Le prompt à copier (ChatGPT)', 'Images : Pexels'):
            self.assertIn(frag, tt)
        self.assertIn("instagram: {type: reel, shouldShareToFeed: true, isAiGenerated: true}", next(q for q in creates if "c_ig" in q))
        m = Buffer("bk", self.state).metrics("post_tt")
        self.assertEqual((m["views"], m["likes"], m["comments"], m["saves"]), (1234, 80, 12, 30))

    def test_releve_des_statistiques_puis_score(self):
        """Une vidéo publiée il y a 25 h via Buffer : un relevé est pris (une seule fois), puis elle est notée."""
        from studio import stats, strategist
        cfg = {"stats": {"check_after_hours": [24, 72, 168]}}
        for i, hours in enumerate([25, 26, 30, 2]):
            at = (now() - dt.timedelta(hours=hours)).isoformat(timespec="seconds")
            self.state.add_post({"id": f"p{i}", "created": at, "title": f"vidéo {i}", "brief": {"famille": "prompts"}, "duration": 40,
                                 "published": {"tiktok": {"via": "buffer", "id": f"post_{i}", "status": "sent", "at": at},
                                               "facebook": {"status": "skipped"}}, "stats": {}})
        n = stats.collect(self.state, cfg, lambda *_: None)
        self.assertEqual(n, 3, "les 3 vidéos de plus de 24 h sont relevées, pas celle de 2 h, ni le réseau ignoré")
        self.assertEqual(self.state.posts[0]["stats"]["tiktok"][0]["views"], 1234)
        self.assertEqual(stats.collect(self.state, cfg, lambda *_: None), 0, "pas de second relevé avant l'échéance suivante")
        strategist.score_posts(self.state, cfg)
        self.assertEqual([p.get("score") for p in self.state.posts], [0.0, 0.0, 0.0, None])

    def test_mode_essai_ne_publie_rien(self):
        cfg = {"publish": {"dry_run": True, "via": "buffer", "networks": ["tiktok"]}, "offer": {}}
        st, _ = writer.controler(json.loads((ROOT / "examples" / "reserve" / "p1_business.json").read_text(encoding="utf-8")), self.cfg, {})
        out = publish_all("/tmp/x.mp4", st, 0, None, cfg, self.state, lambda *_: None)
        self.assertEqual(out["tiktok"]["status"], "dry_run")
        self.assertEqual(SEEN, [])


if __name__ == "__main__":
    unittest.main()
