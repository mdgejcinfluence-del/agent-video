"""Le « cerveau » : une chaîne de fournisseurs de modèles gratuits, compatibles avec l'API OpenAI.

Ordre défini dans config.yaml (NVIDIA d'abord). Pour chaque appel :
  1. on prend le premier fournisseur qui a une clé et du quota restant aujourd'hui ;
  2. en cas d'erreur (quota, panne, modèle retiré) on passe au suivant ;
  3. le garde-fou de quota (compteurs par jour dans state/) empêche de dépasser les paliers gratuits.
Aucun de ces appels n'est payant : si aucune clé gratuite ne répond, l'appel échoue (et l'agent
utilise alors son scénario de secours sans LLM), il ne bascule jamais vers une offre payante.
"""
from __future__ import annotations

import json
import re
import time

import requests

from .config import secret

# Fournisseurs sans clé, utilisés en dernier recours (qualité moindre, mais l'agent ne s'arrête jamais).
KEYLESS = [
    {"name": "pollinations", "base_url": "https://text.pollinations.ai/openai", "key_env": None, "model": "openai",
     "path": "", "rpm": 1.25, "rpd": 120},          # palier anonyme observé : 1 réponse toutes les 45 s par adresse IP
    {"name": "llm7", "base_url": "https://api.llm7.io/v1", "key_env": None, "model": "default", "rpm": 10, "rpd": 150},
]


class LLMError(RuntimeError):
    pass


def extract_json(text: str):
    """Récupère l'objet JSON d'une réponse de modèle (balises de réflexion, ```json, texte autour…)."""
    if text is None:
        raise ValueError("réponse vide")
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S | re.I).strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.S)
    if fence:
        text = fence.group(1).strip()
    start = text.find("{")
    if start < 0:
        raise ValueError("aucun objet JSON dans la réponse")
    depth, in_str, esc_ = 0, False, False
    for i in range(start, len(text)):
        c = text[i]
        if in_str:
            if esc_:
                esc_ = False
            elif c == "\\":
                esc_ = True
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                blob = text[start:i + 1]
                try:
                    return json.loads(blob)
                except json.JSONDecodeError:
                    blob = re.sub(r",\s*([}\]])", r"\1", blob)          # virgules finales
                    return json.loads(blob)
    raise ValueError("objet JSON incomplet (réponse tronquée ?)")


class Brain:
    def __init__(self, cfg: dict, state=None, log=print, session: requests.Session | None = None):
        self.cfg, self.state, self.log = cfg, state, log
        self.http = session or requests.Session()
        lcfg = cfg.get("llm", {})
        self.providers = [dict(p) for p in lcfg.get("providers", [])]
        if lcfg.get("keyless_fallback", False):
            self.providers += [dict(p) for p in KEYLESS]
        self.temperature = float(lcfg.get("temperature", 0.8))
        self.budget = int(lcfg.get("max_calls_per_video", 14))
        self.calls = 0
        self.dead: set[str] = set()
        self._last: dict[str, float] = {}
        self._models: dict[str, str] = {}
        self.used: list[str] = []

    # ------------------------------------------------------------------ quotas
    def _key(self, p: dict) -> str | None:
        return secret(p["key_env"]) if p.get("key_env") else "sans-cle"

    def available(self) -> list[dict]:
        out = []
        for p in self.providers:
            if p["name"] in self.dead or not self._key(p):
                continue
            if self.state is not None and self.state.quota_used(f"llm:{p['name']}") >= int(p.get("rpd", 10 ** 9)):
                continue
            out.append(p)
        return out

    def _pace(self, p: dict) -> None:
        gap = 60.0 / max(0.5, float(p.get("rpm", 30)))
        wait = self._last.get(p["name"], 0) + gap - time.time()
        if wait > 0:
            time.sleep(min(wait, 60))
        self._last[p["name"]] = time.time()

    # ------------------------------------------------------------------ modèles
    def _model(self, p: dict, key: str) -> str:
        if p["name"] in self._models:
            return self._models[p["name"]]
        model = p.get("model") or ""
        try:
            if p.get("key_env"):
                r = self.http.get(p["base_url"].rstrip("/") + "/models", headers={"Authorization": f"Bearer {key}"}, timeout=20)
                ids = [m.get("id", "") for m in (r.json().get("data") or [])] if r.ok else []
                ids = [i.split("models/")[-1] for i in ids]
                if ids and model not in ids:
                    for pref in p.get("prefer", []):
                        hit = next((i for i in ids if pref.lower() in i.lower()), None)
                        if hit:
                            self.log(f"cerveau : {p['name']} — modèle « {model} » absent du catalogue, remplacé par « {hit} »")
                            model = hit
                            break
        except Exception:  # noqa: BLE001 — catalogue indisponible : on garde le modèle configuré
            pass
        self._models[p["name"]] = model
        return model

    # ------------------------------------------------------------------ appel
    def chat(self, messages: list[dict], json_mode: bool = False, temperature: float | None = None,
             max_tokens: int = 4096, purpose: str = "") -> str:
        if self.calls >= self.budget:
            raise LLMError(f"budget d'appels atteint ({self.budget} par vidéo)")
        errors = []
        for p in self.available():
            key = self._key(p)
            model = self._model(p, key)
            url = p["base_url"].rstrip("/") + p.get("path", "/chat/completions")
            body = {"model": model, "messages": messages, "temperature": self.temperature if temperature is None else temperature,
                    "max_tokens": max_tokens}
            if json_mode:
                body["response_format"] = {"type": "json_object"}
            for attempt in range(4):
                self._pace(p)
                try:
                    headers = {"Content-Type": "application/json"}
                    if p.get("key_env"):
                        headers["Authorization"] = f"Bearer {key}"
                    r = self.http.post(url, headers=headers, json=body, timeout=120)
                except requests.RequestException as e:
                    errors.append(f"{p['name']}: réseau {type(e).__name__}")
                    time.sleep(2 * (attempt + 1))
                    continue
                self.calls += 1
                if self.state is not None:
                    self.state.quota_add(f"llm:{p['name']}")
                if r.status_code == 400 and "token limit" in r.text and body["max_tokens"] < 16000:
                    body["max_tokens"] = min(16000, body["max_tokens"] * 2)     # modèle « à réflexion » : il lui faut plus de marge
                    errors.append(f"{p['name']}: limite de sortie, nouvel essai à {body['max_tokens']} jetons")
                    continue
                if r.status_code == 400 and "response_format" in body:
                    body.pop("response_format")            # ce fournisseur ne connaît pas le mode JSON
                    continue
                if r.status_code == 402 and "FREE_LIMIT" in r.text:       # limite de débit du palier anonyme, pas une demande de paiement
                    errors.append(f"{p['name']}: limite de débit")
                    time.sleep(46)
                    continue
                if r.status_code in (429, 500, 502, 503, 504, 529):
                    errors.append(f"{p['name']}: HTTP {r.status_code}")
                    ra = r.headers.get("Retry-After")
                    time.sleep(min(float(ra) if ra and ra.replace('.', '', 1).isdigit() else 3 * (attempt + 1), 20))
                    continue
                if not r.ok:
                    errors.append(f"{p['name']}: HTTP {r.status_code} {r.text[:120]}")
                    if r.status_code in (401, 402, 403, 404):
                        self.dead.add(p["name"])
                    break
                try:
                    msg = r.json()["choices"][0]["message"]
                    text = msg.get("content") or ""
                except Exception:  # noqa: BLE001
                    errors.append(f"{p['name']}: réponse illisible")
                    break
                if not text.strip():
                    errors.append(f"{p['name']}: réponse vide")
                    continue
                self.used.append(f"{p['name']}/{model}")
                return text
            # ce fournisseur n'a rien donné : on ne le sollicite plus pour cette vidéo (ni temps ni quota gaspillés)
            self.dead.add(p["name"])
        raise LLMError("aucun modèle gratuit n'a répondu" + (" — " + " | ".join(errors[-6:]) if errors else " (aucune clé configurée)"))

    def ask_json(self, system: str, user: str, validate=None, retries: int = 2, temperature: float | None = None,
                 max_tokens: int = 4096, purpose: str = ""):
        """Demande un objet JSON ; `validate(obj)` peut lever une erreur dont le message est renvoyé au modèle."""
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        last = None
        for attempt in range(retries + 1):
            text = self.chat(messages, json_mode=True, temperature=temperature, max_tokens=max_tokens, purpose=purpose)
            try:
                obj = extract_json(text)
                return validate(obj) if validate else obj
            except Exception as e:  # noqa: BLE001 — on renvoie l'erreur au modèle pour qu'il corrige
                last = e
                self.log(f"cerveau : réponse rejetée ({purpose or 'json'}) — {str(e)[:150]}")
                messages = messages[:2] + [{"role": "assistant", "content": text[:6000]},
                                           {"role": "user", "content": f"Ta réponse est refusée : {e}. Corrige et renvoie UNIQUEMENT l'objet JSON complet."}]
        raise LLMError(f"JSON invalide après {retries + 1} essais : {last}")
