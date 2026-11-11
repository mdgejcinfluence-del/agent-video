"""Mémoire de l'agent : de simples fichiers JSON dans state/ (versionnés dans le dépôt).

  posts.json   chaque vidéo : sujet, format, où elle est publiée, relevés de statistiques, score
  quota.json   compteurs d'appels par jour (garde-fou des paliers gratuits)
  day.json     créneaux choisis pour chaque jour
  seen.json    sujets déjà traités (pour ne pas se répéter)
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path


def now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class State:
    def __init__(self, root: str | Path):
        self.dir = Path(root) / "state"
        self.dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, object] = {}

    def load(self, name: str, default):
        if name in self._cache:
            return self._cache[name]
        p = self.dir / f"{name}.json"
        try:
            obj = json.loads(p.read_text(encoding="utf-8")) if p.exists() else default
        except json.JSONDecodeError:
            obj = default
        self._cache[name] = obj
        return obj

    def save(self, name: str, obj=None) -> None:
        if obj is not None:
            self._cache[name] = obj
        p = self.dir / f"{name}.json"
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._cache[name], ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(p)

    # ------------------------------------------------------------------ quotas (par jour, UTC)
    def _q(self) -> dict:
        q = self.load("quota", {})
        today = now().strftime("%Y-%m-%d")
        for d in [d for d in q if d < (now() - dt.timedelta(days=40)).strftime("%Y-%m-%d")]:
            del q[d]
        q.setdefault(today, {})
        return q

    def quota_used(self, key: str, days: int = 1) -> int:
        q = self._q()
        ds = sorted(q)[-days:]
        return sum(int(q[d].get(key, 0)) for d in ds)

    def quota_add(self, key: str, n: int = 1) -> None:
        q = self._q()
        today = now().strftime("%Y-%m-%d")
        q[today][key] = int(q[today].get(key, 0)) + n
        self.save("quota", q)

    # ------------------------------------------------------------------ vidéos
    @property
    def posts(self) -> list[dict]:
        return self.load("posts", [])

    def add_post(self, post: dict) -> None:
        self.posts.append(post)
        self.save("posts")

    def save_posts(self) -> None:
        self.save("posts")

    def log(self, event: str, **data) -> None:
        with open(self.dir / "journal.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"t": now().isoformat(timespec="seconds"), "event": event, **data}, ensure_ascii=False) + "\n")
