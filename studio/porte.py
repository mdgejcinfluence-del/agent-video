"""La porte de publication : ce qui doit être vrai pour qu'une vidéo parte seule sur les réseaux.

L'agent publie sans validation humaine. Il ne publie donc QUE ce que ses contrôles automatiques ont accepté :
  1. le storyboard respecte la forme et les garde-fous (aucune promesse, aucun chiffre sans source, aucun outil sans fait vérifié) ;
  2. chaque séquence filmée a passé ses contrôles (format, netteté, cohérence avec la phrase, droits) ;
  3. le contrôle qualité de la vidéo est réussi (format, durée, son, mise en page, sous-titres) ;
  4. si un fait vérifié cité a été suspendu par la veille entre l'écriture et la publication, la vidéo est retenue.
Pour tout arrêter : publish.dry_run: true dans config.yaml, ou désactiver la tâche dans l'onglet Actions.
"""
from __future__ import annotations


def bloquants(cfg: dict, story: dict, qa: dict | None, faits_ok: dict | None = None) -> list[str]:
    out = []
    if qa is not None and not qa.get("ok"):
        out.append("contrôle qualité en échec : " + " ; ".join(qa.get("problems") or ["raison inconnue"]))
    for fid in story.get("faits") or []:
        if faits_ok is not None and fid not in faits_ok:
            out.append(f"le fait « {fid} » n'est plus confirmé par la veille")
    return out
