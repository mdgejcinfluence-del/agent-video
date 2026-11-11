"""Chargement de la configuration (config.yaml) et des secrets (variables d'environnement / .env)."""
from __future__ import annotations

import copy
import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent

THEMES = {
    "papier": {"bg": "#F4EFEA", "card": "#FDF9F6", "ink": "#1B1613", "muted": "#8C817A", "accent": "#D8572E",
               "accent2": "#EC7B50", "soft": "#F3CDBB", "good": "#2F9E5A", "bad": "#D9483F", "stamp": "#2F9E5A",
               "dot": "rgba(70,45,30,.17)"},
    "ocean": {"bg": "#EEF3F7", "card": "#FAFCFE", "ink": "#101C26", "muted": "#7B8894", "accent": "#1F6FEB",
              "accent2": "#4F97F7", "soft": "#C6DCF7", "good": "#1F9D63", "bad": "#D9483F", "stamp": "#E0662F",
              "dot": "rgba(20,50,80,.16)"},
    "menthe": {"bg": "#EFF5F0", "card": "#FBFDFB", "ink": "#12201A", "muted": "#7C8A82", "accent": "#178A57",
               "accent2": "#35AB74", "soft": "#C4E6D3", "good": "#178A57", "bad": "#D9483F", "stamp": "#E0662F",
               "dot": "rgba(20,70,45,.16)"},
    "nuit": {"bg": "#15110F", "card": "#221C19", "ink": "#F7F0EA", "muted": "#9C9089", "accent": "#F0774A",
             "accent2": "#FF9C70", "soft": "#4B2A1B", "good": "#3DBB73", "bad": "#E5564C", "stamp": "#3DBB73",
             "dot": "rgba(255,230,210,.10)"},
}


def _hex(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def _mix(a: str, b: str, k: float) -> str:
    x, y = _hex(a), _hex(b)
    return "#%02X%02X%02X" % tuple(round(x[i] + (y[i] - x[i]) * k) for i in range(3))


def theme_vars(cfg: dict) -> dict:
    """Variables CSS du thème ; une couleur de marque (brand.accent) remplace l'accent."""
    name = (cfg.get("brand") or {}).get("theme") or "papier"
    th = dict(THEMES.get(name, THEMES["papier"]))
    acc = ((cfg.get("brand") or {}).get("accent") or "").strip()
    if acc.startswith("#") and len(acc) == 7:
        th["accent"] = acc
        th["accent2"] = _mix(acc, "#FFFFFF", 0.22)
        th["soft"] = _mix(acc, th["bg"], 0.72)
    return th


def load_dotenv(path: Path | None = None) -> None:
    """Lit un fichier .env simple (CLE=valeur) sans dépendance externe."""
    path = path or ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _deep(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        out[k] = _deep(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load(path: str | Path | None = None) -> dict:
    load_dotenv()
    p = Path(path) if path else ROOT / "config.yaml"
    cfg = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    # surcharge possible par variable d'environnement (utile dans GitHub Actions)
    if os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes"):
        cfg.setdefault("publish", {})["dry_run"] = True
    if os.environ.get("DRY_RUN", "").lower() in ("0", "false", "no"):
        cfg.setdefault("publish", {})["dry_run"] = False
    cfg["_root"] = str(ROOT)
    return cfg


def secret(name: str) -> str | None:
    v = os.environ.get(name)
    return v.strip() if v and v.strip() else None
