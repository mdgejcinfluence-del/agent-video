"""Tests des échanges réseau contre de FAUX serveurs locaux (aucun appel réel, aucune clé).

Ils vérifient la logique : bascule entre fournisseurs, correction d'un storyboard refusé,
garde-fou de quota, forme exacte des requêtes Buffer. Ils ne prouvent pas que les vrais
services acceptent ces requêtes : cela ne se vérifie qu'avec de vraies clés.
"""
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

from studio import llm, writer  # noqa: E402
from studio.publish import publish_all  # noqa: E402
from studio.publish.buffer import Buffer, Enum, lit  # noqa: E402
from studio.state import State  # noqa: E402

DEMO = json.loads((ROOT / "examples" / "demo_storyboard.json").read_text(encoding="utf-8"))
SEEN: list[dict] = []
SCRIPT: dict[str, list] = {}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        raw = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(raw)))
        self.end_headers(); self.wfile.write(raw)

    def do_GET(self):
        if self.path.endswith("/models"):
            return self._send(200, {"data": [{"id": "vieux-modele"}, {"id": "nvidia/nemotron-3-ultra-550b-a55b"}]})
        self._send(404, {})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        SEEN.append({"path": self.path, "body": body, "auth": self.headers.get("Authorization")})
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
        key = self.path.split("/")[1]
        step = SCRIPT[key].pop(0) if SCRIPT.get(key) else (200, "{}")
        code, content = step
        if code != 200:
            return self._send(code, {"error": "x"})
        self._send(200, {"choices": [{"message": {"role": "assistant", "content": content}}]})


class Net(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = HTTPServer(("127.0.0.1", 0), Handler)
        cls.url = f"http://127.0.0.1:{cls.srv.server_port}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        os.environ.update({"KEY_A": "ka", "KEY_B": "kb", "BUFFER_API_URL": cls.url + "/buffer", "BUFFER_API_KEY": "bk"})

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        SEEN.clear(); SCRIPT.clear()
        self.state = State(Path(tempfile.mkdtemp()))
        self.cfg = {"_root": str(ROOT), "llm": {"keyless_fallback": False, "max_calls_per_video": 12, "providers": [
            {"name": "a", "base_url": self.url + "/a/v1", "key_env": "KEY_A", "model": "m", "rpm": 6000, "rpd": 50},
            {"name": "b", "base_url": self.url + "/b/v1", "key_env": "KEY_B", "model": "modele-retire", "prefer": ["nemotron-3-ultra"], "rpm": 6000, "rpd": 50},
            {"name": "sans_cle", "base_url": self.url + "/c/v1", "key_env": "KEY_ABSENTE", "model": "m"}]},
            "offer": {}, "niche": {}, "brand": {}}

    def brain(self):
        b = llm.Brain(self.cfg, self.state, lambda *_: None)
        b._pace = lambda p: None
        return b

    def test_bascule_et_correction(self):
        """A est en panne (429) -> on passe à B. B invente un chiffre -> refusé, l'erreur lui est renvoyée -> il corrige."""
        import studio.llm as L
        L.time.sleep = lambda *_: None
        bad = json.loads(json.dumps(DEMO)); bad["scenes"][1]["blocks"][1]["rows"][2] = "45 fois plus net"
        SCRIPT["a"] = [(429, "")] * 9
        SCRIPT["b"] = [(200, "Voici :\n```json\n" + json.dumps(bad) + "\n```"), (200, "<think>hmm</think>" + json.dumps(DEMO))]
        facts = [{"title": "démo", "url": "u", "facts": ["Étoiles GitHub : 72 000", "Gratuit jusqu'à 3 employés"]}]
        brief = {"format": "tuto", "hook": "promesse", "length": "moyen"}
        st = writer.write(self.brain(), brief, {"items": facts, "angle": ""}, self.cfg)
        self.assertEqual(st["keyword"], "MOTION")
        calls_b = [s for s in SEEN if s["path"].startswith("/b/")]
        self.assertEqual(len(calls_b), 2)
        self.assertEqual(calls_b[0]["auth"], "Bearer kb")
        self.assertEqual(calls_b[0]["body"]["model"], "nvidia/nemotron-3-ultra-550b-a55b", "modèle retiré -> remplacé par un modèle du catalogue")
        retry_msgs = calls_b[1]["body"]["messages"]
        self.assertIn("45", retry_msgs[-1]["content"]); self.assertIn("refusée", retry_msgs[-1]["content"])
        self.assertFalse(any(s["path"].startswith("/c/") for s in SEEN), "un fournisseur sans clé n'est jamais appelé")
        self.assertGreaterEqual(self.state.quota_used("llm:b"), 2)

    def test_garde_fou_de_quota(self):
        self.cfg["llm"]["providers"][0]["rpd"] = 1
        self.cfg["llm"]["providers"][1]["rpd"] = 1
        SCRIPT["a"] = [(200, "un")]; SCRIPT["b"] = [(200, "deux")]
        br = self.brain()
        self.assertEqual(br.chat([{"role": "user", "content": "x"}]), "un")
        self.assertEqual(br.chat([{"role": "user", "content": "x"}]), "deux")
        with self.assertRaises(llm.LLMError):
            br.chat([{"role": "user", "content": "x"}])
        self.assertEqual(len([s for s in SEEN if "/chat/completions" in s["path"]]), 2, "aucun appel au-delà du quota du jour")

    def test_budget_par_video(self):
        self.cfg["llm"]["max_calls_per_video"] = 2
        SCRIPT["a"] = [(200, "x")] * 5
        br = self.brain()
        br.chat([{"role": "user", "content": "x"}]); br.chat([{"role": "user", "content": "x"}])
        with self.assertRaises(llm.LLMError):
            br.chat([{"role": "user", "content": "x"}])

    def test_json_robuste(self):
        self.assertEqual(llm.extract_json('bla {"a": {"b": "}"}, "c": [1,2,],} fin')["c"], [1, 2])
        with self.assertRaises(ValueError):
            llm.extract_json('{"a": 1')

    def test_litteral_graphql(self):
        self.assertEqual(lit({"a": Enum("automatic"), "b": "x\"y", "c": [1, True], "d": None}), '{a: automatic, b: "x\\"y", c: [1, true]}')

    def test_buffer_publication_et_stats(self):
        import studio.publish as P
        P.time.sleep = lambda *_: None
        cfg = {"publish": {"dry_run": False, "via": "buffer", "networks": ["tiktok", "instagram", "facebook"], "ai_label": True, "hashtags": 3}}
        story = {"caption": "Légende.", "hashtags": ["ia", "claudecode", "outils", "x"], "title": "T"}
        out = publish_all("/tmp/x.mp4", story, 2400, "https://moi.github.io/agent/v/x.mp4", cfg, self.state, lambda *_: None)
        self.assertEqual(out["tiktok"]["status"], "sent"); self.assertEqual(out["tiktok"]["id"], "post_tt")
        self.assertEqual(out["instagram"]["status"], "sent")
        self.assertEqual(out["facebook"]["status"], "skipped", "pas de canal Facebook dans Buffer ni de jeton natif -> ignoré, sans bloquer les autres")
        creates = [s["body"]["query"] for s in SEEN if "createPost" in s["body"].get("query", "")]
        self.assertEqual(len(creates), 2)
        tt = next(q for q in creates if "c_tt" in q)
        for frag in ('schedulingType: automatic', 'mode: shareNow', 'url: "https://moi.github.io/agent/v/x.mp4"', 'thumbnailOffset: 2400',
                     'tiktok: {isAiGenerated: true}', '#ia #claudecode #outils'):
            self.assertIn(frag, tt)
        self.assertNotIn("#x", tt)
        self.assertIn("instagram: {type: reel, shouldShareToFeed: true, isAiGenerated: true}", next(q for q in creates if "c_ig" in q))
        m = Buffer("bk", self.state).metrics("post_tt")
        self.assertEqual((m["views"], m["likes"], m["comments"], m["saves"]), (1234, 80, 12, 30))
        self.assertGreater(self.state.quota_used("buffer"), 4)

    def test_releve_des_statistiques_puis_score(self):
        """Une vidéo publiée il y a 25 h via Buffer : un relevé est pris (une seule fois), puis elle est notée."""
        import datetime as dt
        from studio import stats, strategist
        from studio.state import now
        cfg = {"stats": {"check_after_hours": [24, 72, 168]}}
        for i, hours in enumerate([25, 26, 30, 2]):
            at = (now() - dt.timedelta(hours=hours)).isoformat(timespec="seconds")
            self.state.add_post({"id": f"p{i}", "created": at, "title": f"vidéo {i}", "brief": {"format": "liste"},
                                 "published": {"tiktok": {"via": "buffer", "id": f"post_{i}", "status": "sent", "at": at},
                                               "facebook": {"status": "skipped"}}, "stats": {}})
        n = stats.collect(self.state, cfg, lambda *_: None)
        self.assertEqual(n, 3, "les 3 vidéos de plus de 24 h sont relevées, pas celle de 2 h, ni le réseau ignoré")
        self.assertEqual(self.state.posts[0]["stats"]["tiktok"][0]["views"], 1234)
        self.assertEqual(stats.collect(self.state, cfg, lambda *_: None), 0, "pas de second relevé avant l'échéance suivante")
        strategist.score_posts(self.state, cfg)
        self.assertEqual([p.get("score") for p in self.state.posts], [0.0, 0.0, 0.0, None])

    def test_mode_essai_ne_publie_rien(self):
        cfg = {"publish": {"dry_run": True, "via": "buffer", "networks": ["tiktok"]}}
        out = publish_all("/tmp/x.mp4", {"caption": "c", "hashtags": []}, 0, None, cfg, self.state, lambda *_: None)
        self.assertEqual(out["tiktok"]["status"], "dry_run")
        self.assertEqual(SEEN, [])


if __name__ == "__main__":
    unittest.main()
