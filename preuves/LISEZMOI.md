# Dossiers de preuve

Règle de l'agent : **pas de preuve, pas de vidéo.** Une vidéo ne montre que ce qui existe dans l'un de ces dossiers :
la demande écrite, le code réellement écrit, les images et les vidéos réellement rendues. Le moteur ne dessine aucun faux écran.

| Dossier | Série | Ce qu'il contient |
|---|---|---|
| `createur-intro-serie/` | Créateur / freelance | Une intro de série : demande, correction, code, premier rendu (avec son défaut), rendu final, version « charte générique ». |
| `commerce-karite-exemple/` | Commerçant | **Exemple fictif** : une photo d'exemple transformée en publicité de 6 secondes, avec sa correction. |
| `projet-remotion/` | — | Le projet Remotion qui a produit ces rendus (`npm install`, puis `npx remotion studio src/index.ts`). |

## Ajouter un vrai cas (c'est ce qui rend une vidéo publiable)

1. Copie un dossier, par exemple `commerce-karite-exemple/` vers `commerce-<nom>/`.
2. Mets dans `media/` la **vraie photo** du produit (avec l'accord du commerçant) et les rendus obtenus.
3. Écris dans `demande.md` la demande telle qu'elle a été donnée, mot pour mot. S'il y a eu une correction, écris-la dans `correction.md`.
4. Dans `preuve.yaml` : change `id`, mets `fictif: false`, remplis `offre` (nom, format, **prix vérifié**, consigne), `faits`, `limites`,
   la liste `sujets` (numéros de `data/sujets.yaml`) et la description de chaque média.
5. Quand tu as tout relu, signe : `valide_par: "ton nom"` et `valide_le: "AAAA-MM-JJ"`. Sans signature, la vidéo est fabriquée mais jamais publiée.

Vérifie un dossier avec : `python3 run.py preuves`.

## Ce que le code contrôle pour toi

- un extrait de demande affiché à l'écran doit se retrouver **mot pour mot** dans `demande.md` ou `correction.md` ;
- une ligne de code affichée doit se retrouver **telle quelle** dans l'un des fichiers listés dans `sources` ;
- un média cité doit exister ; un nombre prononcé ou affiché doit figurer dans `faits`, `offre`, la demande ou une source vérifiée ;
- si `fictif: true`, la mention « EXEMPLE FICTIF » reste à l'écran du début à la fin.

## Licence de Remotion (vérifiée le 2026-11-11 sur remotion.dev/docs/license/pricing)

Licence gratuite pour les particuliers et les organisations jusqu'à 3 personnes ; au-delà, licence payante.
Ce n'est pas un logiciel open source. Vérifie ta situation avant un usage commercial.
