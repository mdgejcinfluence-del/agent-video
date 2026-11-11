"""Chargement de la configuration (config.yaml) et des secrets (variables d'environnement / .env)."""
from __future__ import annotations

import copy
import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent

# Identité visuelle : papier quadrillé, encre bleu nuit, surligneur jaune d'or (les couleurs du personnage).
# Chaque clé devient une variable CSS du moteur de rendu (engine/player.css).
THEME = {"paper": "#F5F1E8", "ink": "#0E1A38", "mark": "#FFC531", "card": "#FFFFFF",
         "line": "rgba(14,26,56,.055)", "line2": "rgba(14,26,56,.09)", "bad": "#E5533D", "good": "#18A66B", "mute": "#6B7388"}
# clés d'environnement qui suffisent à publier pour de vrai
PUBLISH_KEYS = ("BUFFER_API_KEY", "FB_PAGE_TOKEN", "IG_TOKEN", "TIKTOK_REFRESH_TOKEN")


def theme_vars(cfg: dict) -> dict:
    """Variables CSS : le thème par défaut, modifié par brand.couleurs (papier, encre, surligneur)."""
    t = dict(THEME)
    c = ((cfg.get("brand") or {}).get("couleurs") or {})
    for src, dst in (("papier", "paper"), ("encre", "ink"), ("surligneur", "mark"), ("carte", "card")):
        if c.get(src):
            t[dst] = str(c[src])
    return t


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


def peut_publier() -> bool:
    """Vrai dès qu'une clé de publication est en place."""
    return any(secret(k) for k in PUBLISH_KEYS)


def essai(cfg: dict) -> bool:
    """Mode essai ? dry_run: true -> toujours ; false -> jamais ; auto (défaut) -> tant qu'aucune clé de publication n'existe.

    C'est ce qui permet à l'agent de démarrer tout seul : le jour où tu ajoutes la clé de publication, il publie.
    """
    v = (cfg.get("publish") or {}).get("dry_run", "auto")
    if isinstance(v, bool):
        return v
    if str(v).lower() in ("true", "1", "oui", "yes"):
        return True
    if str(v).lower() in ("false", "0", "non", "no"):
        return False
    return not peut_publier()
