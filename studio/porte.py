"""La porte de publication : ce qui doit être vrai avant qu'une vidéo parte sur les réseaux.

La machine peut écrire, rendre et contrôler un brouillon toute seule. Elle ne publie pas une affirmation commerciale,
un prix ou une promotion sans qu'une personne l'ait vérifié. Chaque condition ci-dessous se lit dans un fichier que
tu remplis toi-même (preuve.yaml, config.yaml) : l'agent ne peut pas la cocher à ta place.
"""
from __future__ import annotations

import datetime as dt

from . import preuves, writer


def promo_etat(cfg: dict, today: dt.date | None = None) -> tuple[bool, str]:
    """(la phrase de fin est-elle vraie aujourd'hui ?, explication)"""
    offer = cfg.get("offer") or {}
    if "promo" not in writer.cta_template(cfg).lower():
        return True, "la phrase de fin ne parle pas de promotion"
    promo = offer.get("promo") or {}
    if not promo.get("confirmee"):
        return False, "promotion non confirmée (offer.promo.confirmee) alors que la phrase de fin dit « en promo »"
    end = str(promo.get("jusquau") or "").strip()
    if not end:
        return False, "date de fin de la promotion absente (offer.promo.jusquau)"
    try:
        last = dt.date.fromisoformat(end)
    except ValueError:
        return False, f"date de fin de promotion illisible : « {end} » (attendu AAAA-MM-JJ)"
    today = today or dt.date.today()
    if today > last:
        return False, f"promotion terminée depuis le {end} : la phrase de fin ne serait plus vraie"
    return True, f"promotion confirmée jusqu'au {end}"


def bloquants(cfg: dict, pack: dict, qa: dict | None, suite: dict | None, today: dt.date | None = None) -> list[str]:
    """Raisons pour lesquelles cette vidéo ne peut PAS être publiée (liste vide = seule la validation humaine peut rester)."""
    out = []
    pcfg, offer = cfg.get("publish") or {}, cfg.get("offer") or {}
    if qa is not None and not qa.get("ok"):
        out.append("contrôle qualité en échec : " + "; ".join(qa.get("problems") or []))
    if pack.get("fictif") and not pcfg.get("exemples_fictifs", False):
        out.append(f"le dossier « {pack['id']} » est un exemple fictif : fournis un vrai cas (ou autorise publish.exemples_fictifs)")
    if not preuves.signee(pack):
        out.append(f"le dossier de preuve « {pack['id']} » n'est pas signé (valide_par) : personne n'a encore vérifié le produit, le prix, les droits et les affirmations")
    ok, why = promo_etat(cfg, today)
    if not ok:
        out.append(why)
    if "lien en bio" in writer.cta_template(cfg).lower() and not str(offer.get("lien_bio") or "").strip():
        out.append("page d'aiguillage non renseignée (offer.lien_bio) alors que la phrase de fin dit « lien en bio »")
    if "la suite" in writer.cta_template(cfg).lower() and not suite:
        out.append("aucune suite prévue pour cette série : ajoute un dossier de preuve avant de promettre « la suite »")
    return out


def validation_requise(cfg: dict) -> bool:
    return str((cfg.get("publish") or {}).get("validation", "chaque_video")).strip().lower() != "preuve_signee"
