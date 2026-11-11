"""Le « cerveau » : l'API Gemini de Google (palier gratuit), appelée directement en REST.

Deux niveaux de tâche :
  - « ecriture » : écrire un scénario, le bilan des mesures -> le modèle Flash le plus récent ;
  - « controle » : regarder des images de rushs, classer, vérifier -> le modèle Flash-Lite le plus récent
    (quota gratuit beaucoup plus large).
Les noms de modèles changent plusieurs fois par an : l'agent lit le catalogue (GET /models) à chaque
exécution et choisit lui-même. Sur « quota dépassé » ou « modèle retiré », il passe au suivant.
Si GROQ_API_KEY existe, Groq sert de secours pour le texte seul. Aucun appel n'est payant tant que la
clé vient d'un projet Google sans facturation.
"""
from __future__ import annotations

import base64
import json
import os
import re
import time

import requests

from .config import secret

GEMINI = "https://generativelanguage.googleapis.com/v1beta"
SECOURS = ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash", "gemini-3.5-flash-lite",
           "gemini-3.1-flash-lite", "gemini-2.5-flash", "gemini-2.5-flash-lite"]
EXCLUS = ("tts", "image", "live", "embedding", "robotics", "audio", "computer", "omni", "veo", "lyria", "imagen", "gemma", "aqa", "learnlm", "nano")


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


def classer(noms: list[str], niveau: str) -> list[str]:
    """Ordre de préférence parmi les modèles du catalogue. Jamais de modèle « pro » (payant) ni spécialisé."""
    rows = []
    for n in noms:
        n = n.split("models/")[-1]
        low = n.lower()
        if not low.startswith("gemini-") or any(x in low for x in EXCLUS) or "pro" in low.split("-"):
            continue
        if "flash" not in low:
            continue
        m = re.match(r"gemini-(\d+(?:\.\d+)?)", low)
        ver = float(m.group(1)) if m else 0.0
        lite = "lite" in low
        stable = not any(x in low for x in ("preview", "exp", "latest")) and not re.search(r"-\d{2}-\d{2}$|-\d{3}$", low)
        rows.append((n, ver, lite, stable))
    if niveau == "controle":
        key = lambda r: (0 if r[2] else 1, -r[1], 0 if r[3] else 1, r[0])      # Flash-Lite d'abord, le plus récent
    else:
        key = lambda r: (1 if r[2] else 0, -r[1], 0 if r[3] else 1, r[0])      # Flash d'abord, le plus récent
    out = []
    for r in sorted(rows, key=key):
        if r[0] not in out:
            out.append(r[0])
    return out


class Brain:
    def __init__(self, cfg: dict, state=None, log=print, session: requests.Session | None = None):
        self.cfg, self.state, self.log = cfg, state, log
        self.http = session or requests.Session()
        l = cfg.get("llm") or {}
        self.base = (os.environ.get("GEMINI_BASE_URL") or l.get("base_url") or GEMINI).rstrip("/")
        self.temperature = float(l.get("temperature", 0.8))
        self.budget = int(l.get("max_calls_per_video", 10))
        self.par_jour = int(l.get("max_par_jour", 60))
        self.imposes = {k: [str(x) for x in (v or [])] for k, v in (l.get("modeles") or {}).items()}
        self.calls = 0
        self.used: list[str] = []
        self._catalogue: list[str] | None = None
        self._morts: set[str] = set()
        self._groq_mort = False

    # ------------------------------------------------------------------ disponibilité
    def key(self) -> str | None:
        return secret("GEMINI_API_KEY") or secret("GOOGLE_API_KEY")

    def available(self) -> bool:
        return bool(self.key() or secret("GROQ_API_KEY"))

    def vision(self) -> bool:
        return bool(self.key())

    def _today(self) -> str:
        return time.strftime("%Y-%m-%d", time.gmtime())

    def _epuise(self, model: str) -> bool:
        if model in self._morts:
            return True
        if self.state is None:
            return False
        return (self.state.load("llm", {}).get("epuises") or {}).get(model) == self._today()

    def _marquer_epuise(self, model: str) -> None:
        self._morts.add(model)
        if self.state is not None:
            d = self.state.load("llm", {})
            d["epuises"] = {k: v for k, v in (d.get("epuises") or {}).items() if v == self._today()}
            d["epuises"][model] = self._today()
            self.state.save("llm", d)

    def modeles(self, niveau: str) -> list[str]:
        """Modèles à essayer, dans l'ordre : ceux imposés dans config.yaml, puis le catalogue classé."""
        if self._catalogue is None:
            self._catalogue = []
            try:
                r = self.http.get(f"{self.base}/models", params={"pageSize": 200}, headers={"x-goog-api-key": self.key() or ""}, timeout=25)
                if r.ok:
                    self._catalogue = [m.get("name", "").split("models/")[-1] for m in (r.json().get("models") or [])
                                       if "generateContent" in (m.get("supportedGenerationMethods") or ["generateContent"])]
                else:
                    self.log(f"cerveau : catalogue Gemini illisible (HTTP {r.status_code}) — liste de secours")
            except Exception as e:  # noqa: BLE001
                self.log(f"cerveau : catalogue Gemini injoignable ({type(e).__name__}) — liste de secours")
        cat = self._catalogue or SECOURS
        ordre = [m for m in self.imposes.get(niveau, []) if not self._catalogue or m in self._catalogue] + classer(cat, niveau)
        out = []
        for m in ordre:
            if m not in out and not self._epuise(m):
                out.append(m)
        return out

    # ------------------------------------------------------------------ appels
    def _compte(self, model: str) -> None:
        self.calls += 1
        if self.state is not None:
            self.state.quota_add("llm:gemini")
            self.state.quota_add(f"llm:{model}")

    def _gemini(self, system: str, turns: list[dict], images: list[bytes] | None, niveau: str, temperature: float, max_tokens: int, errors: list[str]) -> str | None:
        key = self.key()
        if not key:
            return None
        if self.state is not None and self.state.quota_used("llm:gemini") >= self.par_jour:
            errors.append(f"gemini: plafond de {self.par_jour} appels par jour atteint (llm.max_par_jour)")
            return None
        contents = []
        for i, t in enumerate(turns):
            parts = [{"text": t["text"]}]
            if i == 0 and images:
                parts += [{"inlineData": {"mimeType": "image/jpeg", "data": base64.b64encode(b).decode()}} for b in images]
            contents.append({"role": t["role"], "parts": parts})
        for model in self.modeles(niveau)[:4]:
            body = {"systemInstruction": {"parts": [{"text": system}]}, "contents": contents,
                    "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens, "responseMimeType": "application/json"}}
            for attempt in range(3):
                try:
                    r = self.http.post(f"{self.base}/models/{model}:generateContent", headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                                       json=body, timeout=180)
                except requests.RequestException as e:
                    errors.append(f"{model}: réseau {type(e).__name__}")
                    time.sleep(2 * (attempt + 1))
                    continue
                self._compte(model)
                txt = r.text[:600]
                if r.status_code == 429:
                    if "PerDay" in txt or "per day" in txt.lower() or attempt == 2:
                        errors.append(f"{model}: quota du jour atteint")
                        self._marquer_epuise(model)
                        break
                    m = re.search(r'"retryDelay"\s*:\s*"(\d+)', txt)
                    wait = min(int(m.group(1)) + 1 if m else 15 * (attempt + 1), 45)
                    errors.append(f"{model}: limite par minute, attente {wait} s")
                    time.sleep(wait)
                    continue
                if r.status_code in (500, 502, 503, 504):
                    errors.append(f"{model}: HTTP {r.status_code}")
                    time.sleep(4 * (attempt + 1))
                    continue
                if r.status_code in (401, 403):
                    errors.append(f"gemini: clé refusée (HTTP {r.status_code}) {txt[:140]}")
                    return None
                if not r.ok:
                    errors.append(f"{model}: HTTP {r.status_code} {txt[:140]}")
                    self._morts.add(model)                       # modèle retiré, ou requête qu'il n'accepte pas
                    break
                try:
                    data = r.json()
                    cand = (data.get("candidates") or [{}])[0]
                    text = "".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts") or [] if not p.get("thought"))
                except Exception:  # noqa: BLE001
                    errors.append(f"{model}: réponse illisible")
                    break
                if not text.strip():
                    why = cand.get("finishReason") or (data.get("promptFeedback") or {}).get("blockReason") or "vide"
                    errors.append(f"{model}: réponse vide ({why})")
                    if why == "MAX_TOKENS" and body["generationConfig"]["maxOutputTokens"] < 32000:
                        body["generationConfig"]["maxOutputTokens"] *= 2      # modèle « à réflexion » : il lui faut plus de marge
                        continue
                    break
                self.used.append(f"gemini/{model}")
                return text
        return None

    def _groq(self, system: str, turns: list[dict], temperature: float, max_tokens: int, errors: list[str]) -> str | None:
        key = secret("GROQ_API_KEY")
        if not key or self._groq_mort:
            return None
        g = (self.cfg.get("llm") or {}).get("groq") or {}
        model = g.get("model", "llama-3.3-70b-versatile")
        msgs = [{"role": "system", "content": system}] + [{"role": "assistant" if t["role"] == "model" else "user", "content": t["text"]} for t in turns]
        body = {"model": model, "messages": msgs, "temperature": temperature, "max_tokens": min(max_tokens, 8000), "response_format": {"type": "json_object"}}
        for attempt in range(3):
            try:
                r = self.http.post((g.get("base_url") or "https://api.groq.com/openai/v1").rstrip("/") + "/chat/completions",
                                   headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, json=body, timeout=120)
            except requests.RequestException as e:
                errors.append(f"groq: réseau {type(e).__name__}")
                time.sleep(2 * (attempt + 1))
                continue
            self.calls += 1
            if self.state is not None:
                self.state.quota_add("llm:groq")
            if r.status_code in (429, 500, 502, 503):
                errors.append(f"groq: HTTP {r.status_code}")
                time.sleep(5 * (attempt + 1))
                continue
            if not r.ok:
                errors.append(f"groq: HTTP {r.status_code} {r.text[:120]}")
                self._groq_mort = True
                return None
            try:
                text = r.json()["choices"][0]["message"].get("content") or ""
            except Exception:  # noqa: BLE001
                errors.append("groq: réponse illisible")
                return None
            if text.strip():
                self.used.append(f"groq/{model}")
                return text
        return None

    def chat(self, system: str, turns: list[dict], images: list[bytes] | None = None, niveau: str = "ecriture",
             temperature: float | None = None, max_tokens: int = 8192) -> str:
        if self.calls >= self.budget:
            raise LLMError(f"budget d'appels atteint ({self.budget} par vidéo)")
        temperature = self.temperature if temperature is None else temperature
        errors: list[str] = []
        text = self._gemini(system, turns, images, niveau, temperature, max_tokens, errors)
        if text is None and not images:
            text = self._groq(system, turns, temperature, max_tokens, errors)
        if text is None:
            raise LLMError("aucun modèle n'a répondu" + (" — " + " | ".join(errors[-5:]) if errors else " (aucune clé GEMINI_API_KEY)"))
        return text

    def ask_json(self, system: str, user: str, images: list[bytes] | None = None, niveau: str = "ecriture", validate=None,
                 retries: int = 2, temperature: float | None = None, max_tokens: int = 8192, purpose: str = ""):
        """Demande un objet JSON ; `validate(obj)` peut lever une erreur dont le message est renvoyé au modèle."""
        turns = [{"role": "user", "text": user}]
        last = None
        for _attempt in range(retries + 1):
            text = self.chat(system, turns, images=images, niveau=niveau, temperature=temperature, max_tokens=max_tokens)
            try:
                obj = extract_json(text)
                return validate(obj) if validate else obj
            except Exception as e:  # noqa: BLE001 — on renvoie l'erreur au modèle pour qu'il corrige
                last = e
                self.log(f"cerveau : réponse rejetée ({purpose or 'json'}) — {str(e)[:300]}")
                turns = turns[:1] + [{"role": "model", "text": text[:9000]},
                                     {"role": "user", "text": f"Ta réponse est refusée pour ces raisons :\n{e}\nCorrige chaque point et renvoie UNIQUEMENT l'objet JSON complet."}]
        raise LLMError(f"JSON invalide après {retries + 1} essais : {last}")
