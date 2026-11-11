"""Chargement de la configuration (config.yaml) et des secrets (variables d'environnement / .env)."""
from __future__ import annotations

import copy
import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent

# Deux séries, deux identités visuelles : on reconnaît le public visé avant d'avoir lu un mot.
# Chaque clé devient une variable CSS du moteur de rendu (engine/player.css).
THEMES = {
    # série Créateur / freelance : studio de nuit, violet et citron
    "nuit": {"bg": "#0E1014", "card": "#181B22", "ink": "#F4F5F7", "muted": "#8D95A3",
             "accent": "#8B5CF6", "on-accent": "#FFFFFF", "accent2": "#C6F432", "on-accent2": "#0E1014", "em": "#C6F432",
             "soft": "rgba(139,92,246,.30)", "good": "#3DDC97", "bad": "#FF5C5C", "warn": "#FFB020", "warn-ink": "#FFB020",
             "dot": "rgba(255,255,255,.07)", "line": "rgba(255,255,255,.10)", "shadow": "rgba(0,0,0,.45)",
             "code-bg": "#0A0C10", "code-ink": "#D7DCE5", "bezel": "#2A2E38", "rail": "#C6F432", "mark-bg": "#C6F432", "mark-ink": "#0E1014"},
    # série Commerçant : papier ivoire, vert profond et jaune d'étiquette
    "ivoire": {"bg": "#FFF8EC", "card": "#FFFFFF", "ink": "#14231B", "muted": "#6E7A72",
               "accent": "#0B4F3A", "on-accent": "#FFFFFF", "accent2": "#FFC83D", "on-accent2": "#14231B", "em": "#0B4F3A",
               "soft": "rgba(255,200,61,.34)", "good": "#1E9E61", "bad": "#D9483F", "warn": "#FFB020", "warn-ink": "#8A5200",
               "dot": "rgba(20,35,27,.09)", "line": "rgba(20,35,27,.11)", "shadow": "rgba(60,40,10,.16)",
               "code-bg": "#12201A", "code-ink": "#E6EFE9", "bezel": "#14231B", "rail": "#0B4F3A", "mark-bg": "#FFC83D", "mark-ink": "#14231B"},
}
SEGMENTS = ("commercant", "createur_freelance")
DEFAULT_THEME = {"commercant": "ivoire", "createur_freelance": "nuit"}


def segment_cfg(cfg: dict, segment: str) -> dict:
    return ((cfg.get("segments") or {}).get(segment) or {})


def theme_vars(cfg: dict, segment: str = "createur_freelance") -> dict:
    """Variables CSS de la série du segment."""
    name = segment_cfg(cfg, segment).get("theme") or DEFAULT_THEME.get(segment, "nuit")
    return dict(THEMES.get(name) or THEMES[DEFAULT_THEME.get(segment, "nuit")])


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
