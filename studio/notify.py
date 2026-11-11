"""Message Telegram après chaque exécution (optionnel, gratuit)."""
from __future__ import annotations

import requests

from .config import secret


def telegram(text: str, cfg: dict, log=print) -> None:
    if not (cfg.get("notify") or {}).get("telegram"):
        return
    tok, chat = secret("TELEGRAM_BOT_TOKEN"), secret("TELEGRAM_CHAT_ID")
    if not tok or not chat:
        return
    try:
        requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", json={"chat_id": chat, "text": text[:3900]}, timeout=20)
    except requests.RequestException as e:
        log(f"notification Telegram impossible ({type(e).__name__})")
