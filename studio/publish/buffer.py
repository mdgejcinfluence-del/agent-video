"""Publication (et statistiques) via Buffer — https://developers.buffer.com

Pourquoi Buffer : l'API de publication de TikTok force en « privé » toutes les vidéos envoyées
par une application non auditée (audit de plusieurs semaines). Buffer est déjà audité : avec son
offre gratuite (3 canaux, 1 clé d'API), une seule clé publie en PUBLIC sur TikTok, Instagram et
Facebook, et renvoie aussi les statistiques. Limites de l'offre gratuite (documentation Buffer,
lue le 11/11/2026) : 150 requêtes / 15 min, 600 / jour, 1 000 par canal et par 30 jours
(3 000 maximum), 10 publications en attente par canal.

Buffer ne reçoit pas de fichier : il vient chercher la vidéo à une adresse publique
(voir studio/mediahost.py).
"""
from __future__ import annotations

import json
import os
import time

import requests

API = "https://api.buffer.com"
DAILY_BUDGET = 90          # 3 000 / 30 jours avec 3 canaux = 100 par jour ; on garde une marge
MONTHLY_BUDGET = 2700


class Enum(str):
    """Valeur écrite sans guillemets dans la requête GraphQL (énumération)."""


def lit(o) -> str:
    if isinstance(o, Enum):
        return str(o)
    if isinstance(o, bool):
        return "true" if o else "false"
    if isinstance(o, (int, float)):
        return str(o)
    if isinstance(o, str):
        return json.dumps(o, ensure_ascii=False)
    if isinstance(o, (list, tuple)):
        return "[" + ", ".join(lit(x) for x in o) + "]"
    if isinstance(o, dict):
        return "{" + ", ".join(f"{k}: {lit(v)}" for k, v in o.items() if v is not None) + "}"
    raise TypeError(type(o))


class Buffer:
    def __init__(self, key: str, state=None, session: requests.Session | None = None, api: str | None = None):
        self.key, self.state, self.http = key, state, session or requests.Session()
        self.api = api or os.environ.get("BUFFER_API_URL") or API
        self._channels: list[dict] | None = None

    def _budget(self) -> None:
        if self.state is None:
            return
        if self.state.quota_used("buffer") >= DAILY_BUDGET or self.state.quota_used("buffer", 30) >= MONTHLY_BUDGET:
            raise RuntimeError("budget de requêtes Buffer atteint (offre gratuite) : on réessaiera plus tard")
        self.state.quota_add("buffer")

    def gql(self, query: str) -> dict:
        for attempt in range(3):
            self._budget()
            r = self.http.post(self.api, headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.key}"},
                               json={"query": query}, timeout=60)
            if r.status_code == 429:
                time.sleep(min(float(r.headers.get("Retry-After", 20) or 20), 60))
                continue
            if r.status_code >= 500:
                time.sleep(5 * (attempt + 1))
                continue
            if r.status_code in (401, 403):
                raise RuntimeError(f"Buffer refuse la clé (HTTP {r.status_code}) : vérifie le secret BUFFER_API_KEY")
            body = r.json()
            if body.get("errors"):
                raise RuntimeError("Buffer : " + "; ".join(e.get("message", "?") for e in body["errors"])[:300])
            return body["data"]
        raise RuntimeError("Buffer : pas de réponse après 3 essais")

    def channels(self) -> list[dict]:
        if self._channels is None:
            orgs = self.gql("query { account { organizations { id } } }")["account"]["organizations"]
            out = []
            for o in orgs:
                data = self.gql(f"query {{ channels(input: {{ organizationId: {lit(o['id'])} }}) {{ id name service }} }}")
                out += data["channels"]
            self._channels = out
        return self._channels

    def channel_for(self, network: str) -> dict | None:
        return next((c for c in self.channels() if c["service"] == network), None)

    def post_video(self, network: str, text: str, video_url: str, thumb_ms: int = 1500, ai_label: bool = True) -> dict:
        ch = self.channel_for(network)
        if not ch:
            raise RuntimeError(f"aucun canal « {network} » connecté dans Buffer")
        inp: dict = {"text": text, "channelId": ch["id"], "schedulingType": Enum("automatic"), "mode": Enum("shareNow"),
                     "assets": [{"video": {"url": video_url, "metadata": {"thumbnailOffset": int(thumb_ms)}}}]}
        if network == "instagram":
            inp["metadata"] = {"instagram": {"type": Enum("reel"), "shouldShareToFeed": True, **({"isAiGenerated": True} if ai_label else {})}}
        elif network == "facebook":
            inp["assets"] = [{"video": {"url": video_url}}]
            inp["metadata"] = {"facebook": {"type": Enum("reel")}}
        elif network == "tiktok" and ai_label:
            inp["metadata"] = {"tiktok": {"isAiGenerated": True}}
        q = (f"mutation {{ createPost(input: {lit(inp)}) {{ ... on PostActionSuccess {{ post {{ id status dueAt }} }} "
             f"... on MutationError {{ message }} }} }}")
        res = self.gql(q)["createPost"]
        if res.get("message"):
            raise RuntimeError(f"Buffer a refusé la publication {network} : {res['message']}")
        return {"id": res["post"]["id"], "status": res["post"].get("status"), "channel": ch["name"]}

    def status(self, post_id: str) -> dict:
        d = self.gql(f"query {{ post(input: {{ id: {lit(post_id)} }}) {{ id status }} }}")["post"]
        return {"status": d.get("status")}

    def metrics(self, post_id: str) -> dict:
        d = self.gql(f"query {{ post(input: {{ id: {lit(post_id)} }}) {{ id status metrics {{ type value unit }} metricsUpdatedAt }} }}")["post"]
        m = {x["type"]: x["value"] for x in (d.get("metrics") or [])}
        out = {"views": m.get("views", m.get("impressions")), "likes": m.get("reactions", m.get("likes")), "comments": m.get("comments"),
               "shares": m.get("shares", m.get("reposts")), "saves": m.get("saves"), "reach": m.get("reach"),
               "watch": m.get("averageTimeWatched"), "status": d.get("status"), "updated": d.get("metricsUpdatedAt")}
        return {k: (int(v) if isinstance(v, float) and k not in ("watch",) else v) for k, v in out.items()}
