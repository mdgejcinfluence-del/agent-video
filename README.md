# Agent vidéo — un compte de vidéos courtes qui tourne tout seul

Cet agent fabrique et publie des vidéos verticales de 40 à 70 secondes, sans personne aux commandes :
il choisit le sujet, écrit le texte, cherche de vraies séquences filmées dans des banques libres de droits,
vérifie qu'elles montrent bien ce que dit la voix, fait le montage, publie, relève les statistiques et
corrige sa route tous les trois jours. GitHub le réveille aux heures prévues ; ton ordinateur peut rester éteint.

Tant qu'aucune clé de publication n'est en place, il est en **mode essai** : il fabrique et contrôle les vidéos,
rien n'est publié. Le jour où tu ajoutes la clé, il publie, sans autre réglage.

---

## 1. Ce qu'il te reste à faire : les clés

Tout se passe dans ton dépôt GitHub : **Settings → Secrets and variables → Actions → New repository secret**.
Une clé ne s'écrit jamais ailleurs (ni dans le code, ni dans une conversation).

| Nom du secret | À quoi il sert | Où l'obtenir (gratuit) | Sans lui |
|---|---|---|---|
| `GEMINI_API_KEY` | Le cerveau : écrit les scénarios, regarde les séquences filmées, rédige le bilan | https://aistudio.google.com/apikey — crée la clé dans un projet **sans facturation** | L'agent n'a que ses 6 vidéos de réserve et n'écrit rien de nouveau |
| `PEXELS_API_KEY` | Cherche des séquences filmées sur Pexels | https://www.pexels.com/api/ (clé immédiate) | Seulement les 14 séquences de la bibliothèque de départ |
| `PIXABAY_API_KEY` | Cherche des séquences filmées sur Pixabay | https://pixabay.com/api/docs/ (la clé s'affiche une fois connecté) | idem |
| `BUFFER_API_KEY` | Publie sur Facebook, Instagram et TikTok, et lit les statistiques | https://buffer.com (offre gratuite : 3 canaux), puis *Settings → API* | Mode essai : rien n'est publié |

Les quatre ensemble = l'agent complet. À chaque réveil, il se sert de ce qu'il trouve.
**Conseil : ajoute `BUFFER_API_KEY` en dernier.** Avec les trois premières clés seulement, l'agent reste en mode essai : il écrit et
fabrique de vraies vidéos, visibles dans l'onglet Actions, sans rien publier. Regarde-en deux ou trois (l'écriture par Gemini n'a encore
jamais tourné avec une vraie clé), puis ajoute la clé Buffer : à partir de là, tout part en ligne sans validation.
À la place de Buffer, les API officielles fonctionnent aussi : `FB_PAGE_ID` + `FB_PAGE_TOKEN`, `IG_USER_ID` + `IG_TOKEN`,
`TIKTOK_CLIENT_KEY` + `TIKTOK_CLIENT_SECRET` + `TIKTOK_REFRESH_TOKEN` (et `publish.via: native` dans `config.yaml`).

Facultatif, dans `config.yaml` : `brand.name` et `brand.handle` (le nom du compte, affiché sur l'écran de fin),
`offer.lien_bio` + `offer.promo` (pour que l'agent annonce la formation à la fin de chaque vidéo — il n'en parle que si c'est rempli).

Pour vérifier : onglet **Actions → Agent vidéo → Run workflow → commande `doctor`**.

---

## 2. Le format des vidéos

Toutes les vidéos suivent la même grammaire, celle des comptes d'astuces qui retiennent leur public :

| Élément | Règle |
|---|---|
| Première image | Le titre de l'accroche est déjà lisible, le personnage est là, le premier visuel aussi. Pas de bonjour. |
| Sous-titres | En haut de l'écran, trois mots à la fois, le mot prononcé est surligné. |
| Écrans | 4 à 7 écrans de 5 à 10 secondes. Un point par écran, annoncé par une tuile numérotée (ÉTAPE 1, ERREUR 2, PLAN 3…). |
| Rythme | Un élément nouveau apparaît au mot près : liste, cartes « non / oui », pictogrammes, fenêtre, séquence filmée. |
| Personnage | Une mascotte dessinée (11 poses) qui change de pose à chaque écran. |
| Séquences filmées | 1 à 3 par vidéo : pour illustrer un geste, ou pour montrer un vrai avant / après de montage. |
| Limite honnête | Un écran et une ligne de la légende disent ce que la méthode ne fait pas. |
| Écran de fin | « Abonne-toi », un mot à commenter, et ce que la vidéo suivante apportera. |
| Légende | Accroche, étapes numérotées, ligne ⚠️, consigne 💬, 🔔, hashtags, crédit des images. |

Identité : papier quadrillé, encre bleu nuit, surligneur jaune — les couleurs du personnage. Tout se règle dans `config.yaml` (`brand.couleurs`).

---

## 3. Ce que l'agent fait à chaque réveil

1. **Mesures** — il lit les statistiques de chaque vidéo publiée (24 h, 72 h, 7 jours) par l'API du réseau, et note chaque vidéo.
2. **Bilan** — tous les 3 jours : ce qui marche, ce qui ne marche pas, nouveaux poids des familles de sujets, rapport dans `state/BILAN.md`.
3. **Veille** — il rouvre les pages officielles et reconfirme chaque fait qu'il a le droit de citer.
4. **Choix** — d'abord la suite promise par une vidéo précédente ; sinon une famille de sujets tirée selon ses poids, puis une idée jamais traitée.
5. **Écriture** — Gemini écrit le storyboard ; chaque refus des contrôles lui est renvoyé pour correction. Sans clé : une vidéo de réserve.
6. **Séquences filmées** — recherche sur Pexels et Pixabay, téléchargement, trois contrôles (voir plus bas).
7. **Montage** — voix, sous-titres au mot près, musique et bruitages générés, rendu image par image.
8. **Contrôle qualité** — format, durée, son, lisibilité, sous-titres. Un seul échec et la vidéo n'est pas publiée.
9. **Publication** — sans validation humaine, puis la suite annoncée est inscrite pour être produite dans les jours suivants.

Chaque vidéo a sa **fiche de production** (`out/<id>.md`) : pourquoi ce sujet, les faits et leurs sources, chaque séquence filmée
avec son auteur et sa page d'origine, le script minuté, les légendes par plateforme, les contrôles.

---

## 4. Les séquences filmées (« rushs »)

L'agent ne reçoit aucune image de ta part. Pour chaque passage qui en demande une, il :

1. **cherche** dans les banques avec quelques mots simples (« hands packing box ») ;
2. **contrôle la technique** : durée, définition une fois recadrée au format vertical, netteté, vrai mouvement, luminosité, pas de bandes noires ;
3. **contrôle la cohérence** : Gemini regarde trois images de chaque séquence candidate et dit ce qu'il voit. Une séquence qui ne montre pas
   ce que dit la phrase est refusée, comme une séquence qui porte un texte, un logo ou une image de synthèse. Sans Gemini, il compare les mots
   de la recherche aux étiquettes de la banque ;
4. **respecte les droits** : source, auteur et page d'origine notés dans la fiche, crédit ajouté à la légende ; une personne reconnaissable
   n'est jamais utilisée dans un passage négatif (erreur, arnaque…) ; une image de banque n'est jamais présentée comme un client ou un résultat.

S'il ne trouve rien d'acceptable, il **ne maquille pas le manque** : il change de sujet.

Le bloc « avant / après » est une vraie démonstration : la séquence brute, puis la même séquence avec des couleurs réglées, un zoom,
un titre, des sous-titres et une barre de progression — appliqués par le moteur de rendu de l'agent.

---

## 5. Ce que l'agent ne dira jamais

Il publie seul, donc ses garde-fous sont automatiques et sans exception (`studio/garde.py`) :

- aucune promesse de revenu, de vues, de résultat garanti, de rapidité ; aucun « illimité », « viral », « 100 % gratuit » ;
- aucune expérience inventée (« j'ai testé », « mes clients ») ;
- aucun envoi promis en privé : la seule promesse de fin est la vidéo suivante, et il la produit ;
- aucun outil nommé, aucun chiffre avec une unité, aucun « gratuit » sans un **fait vérifié** sur une page officielle (`data/faits.yaml`) ;
- aucune astuce de contournement (VPN, adresses jetables, essais gratuits à répétition), aucune imitation d'une personne réelle.

Avec Gemini, l'agent enrichit lui-même sa liste de faits : le modèle propose un fait, sa page officielle et une citation ; l'agent ouvre la page
et ne garde le fait que s'il y retrouve la citation mot pour mot. Chaque jour, il rouvre les pages : une phrase disparue suspend le fait.

---

## 6. Le bilan, tous les 3 jours

`state/BILAN.md` (lisible sur GitHub) contient : le nombre de vidéos mesurées, la note de chacune, les moyennes par famille de sujets,
par type d'accroche, par créneau et par durée, puis les décisions prises :

- le poids d'une famille monte ou descend d'au plus 35 % à la fois, et aucune famille ne disparaît ;
- une vidéo nettement au-dessus du lot donne naissance à une variante, placée en tête des idées ;
- avec Gemini : un diagnostic en clair et de nouvelles idées dans les familles qui marchent.

La note compare la rétention, les partages, les enregistrements et les commentaires à la médiane du compte.
Les vues seules ne désignent jamais une gagnante. Avec moins de 4 vidéos mesurées, le bilan constate et ne change rien.

---

## 7. Où on en est : ce qui a tourné, ce qui n'a pas tourné

| Brique | État au 11/11/2026 |
|---|---|
| Format « mascotte », moteur de rendu, voix, son, contrôle qualité | **A tourné sur GitHub** : les 6 vidéos de réserve fabriquées en entier en 7 minutes (40 à 46 s chacune, 1080×1920, contrôle qualité réussi), puis un réveil normal forcé (bilan, choix, vidéo, fiche, porte de publication) en 1 min 20. |
| Installation sur GitHub | Le 11/11/2026, les miroirs de paquets d'Ubuntu ne répondaient plus depuis les machines de GitHub : deux exécutions sont restées bloquées. Depuis, l'installation ne dépend plus d'eux (ffmpeg autonome gardé en cache), chaque étape a une durée maximale, et un rendu qui n'avance plus est arrêté. |
| Séquences filmées, sans clé | **A tourné** : 14 séquences Pexels choisies et regardées une par une, téléchargées, contrôlées, recadrées, montées. |
| Recherche Pexels / Pixabay par leurs API | **Jamais exécutée pour de vrai** (aucune clé en place). Écrite d'après leur documentation ; testée contre des réponses de même forme. |
| Écriture par Gemini, contrôle des séquences par l'image, bilan rédigé, nouveaux faits | **Jamais exécutés avec une vraie clé.** Testés contre un faux serveur Gemini (catalogue, quotas, corrections, images). La qualité des textes se jugera sur les premières vidéos. |
| Garde-fous, forme, stratège, bilan chiffré, parcours complet | **51 tests automatiques passent** (`python3 -m unittest discover -s tests`). |
| Publication et statistiques par Buffer | **Jamais envoyé au vrai Buffer.** Requêtes écrites d'après sa documentation, testées contre un faux serveur. |
| Réveils automatiques de GitHub | **Pas encore observés** sur ce dépôt (créé le 11/11/2026 ; un réveil prévu ce jour-là n'a pas eu lieu). Toutes les exécutions réussies ont été lancées à la main. |
| Son | Mesuré par le calcul (niveau, marge de la voix sur le fond). Une transcription automatique retrouve le texte prévu dans les 6 vidéos de réserve. **Personne n'a écouté ces vidéos** (ton de la voix, prononciation de « rush ») : écoute-les. |

---

## 8. Régler l'agent (`config.yaml`)

| Réglage | Effet |
|---|---|
| `brand.*` | Nom du compte, identifiant, promesse, public, couleurs, mention de fin. |
| `offer.cta` | La phrase de fin (`MOT` = le mot à commenter, `PROMESSE` = la suite annoncée). |
| `offer.lien_bio`, `offer.promo` | Remplis : la formation est annoncée à la fin de chaque vidéo. Vides : l'agent n'en parle pas. |
| `schedule.*` | Vidéos par jour (2), jours, créneaux candidats. L'agent apprend lesquels marchent. Si tu changes les créneaux, change aussi les lignes `cron` du fichier `.github/workflows/agent.yml`. |
| `video.seconds` | Durée visée (38 à 70 s). Hors format, la voix est rejouée une fois à un autre débit. |
| `voice.*`, `audio.*` | Voix, débit, prononciations, musique, marge de la voix sur le fond. |
| `rushs.*` | Contrôle par l'image, seuils d'acceptation, nombre de candidates regardées, repos d'une séquence déjà utilisée. |
| `publish.dry_run` | `auto` (essai tant qu'aucune clé de publication n'existe), `true` (toujours essai), `false` (publication réelle). |
| `publish.networks`, `publish.via` | Réseaux visés ; Buffer ou API officielles. |
| `bilan.*`, `strategy.*` | Rythme du bilan, minimum de vidéos, ampleur des corrections, part d'essais, délai avant de refaire un sujet. |

Les sujets sont dans `data/sujets.yaml` (7 familles, 24 idées de départ), les faits dans `data/faits.yaml`,
la bibliothèque de séquences dans `data/rushs.yaml`, les vidéos de réserve dans `examples/reserve/`.

## 9. Commandes

Dans l'onglet **Actions → Agent vidéo → Run workflow**, ou sur un ordinateur (`bash setup.sh` puis `python3 run.py …`) :

| Commande | Ce qu'elle fait |
|---|---|
| `tick` | Le réveil normal. Coche « forcer » pour fabriquer une vidéo tout de suite. |
| `demo` | Rend les 6 vidéos de réserve, sans rien publier. |
| `bilan` | Fait le bilan maintenant. |
| `doctor` | Vérifie l'installation, les clés (appel d'essai), les faits, les réserves. |
| `plan` | Le plan du jour et la prochaine vidéo. |
| `sujets` | La banque d'idées, les poids, les suites promises. |
| `rushs` | Essaie une recherche de séquence comme le ferait l'agent (champ « mots », en anglais). |
| `veille` | Rouvre les pages officielles et liste les faits confirmés. |

Les vidéos d'une exécution se téléchargent dans **Actions → l'exécution → Artifacts** pendant 14 jours.

## 10. Arrêter l'agent, dépannage

- **Tout arrêter** : `publish.dry_run: true` dans `config.yaml` (plus rien n'est publié), ou onglet Actions → Agent vidéo → « … » → *Disable workflow*.

| Message | Cause probable |
|---|---|
| « MODE ESSAI » | Aucune clé de publication, ou `dry_run: true`. |
| « rien à produire » | Sans `GEMINI_API_KEY`, les 6 réserves ont toutes été publiées depuis moins de 21 jours. |
| « écriture par le modèle impossible » | Clé absente, quota du jour atteint, ou trois réponses refusées par les contrôles : l'agent prend une réserve. |
| « rushs : rien d'acceptable pour … » | Aucune séquence ne passe les contrôles : l'agent change de sujet. |
| « formulation interdite », « outil nommé sans fait vérifié » | Le modèle a écrit quelque chose que les garde-fous refusent : le refus lui est renvoyé. Rien à faire. |
| « CHANGEMENT sur … » | Une page officielle ne contient plus la phrase attendue : le fait est suspendu. |
| « PUBLICATION RETENUE » | Contrôle qualité en échec ou fait suspendu : la raison suit. |
| « aucun réseau n'a reçu la vidéo » | Clé Buffer invalide, canal déconnecté, ou vidéo refusée : le détail est dans le journal. |
| « rendu trop lent » | La machine manque de mémoire ou le navigateur est bloqué : l'agent arrête ce rendu et réessaie au réveil suivant. |
| « Impossible d'installer ffmpeg » | Ni le téléchargement direct ni le gestionnaire de paquets n'ont répondu : panne de réseau passagère, le réveil suivant reprend. |
| Les réveils s'arrêtent | GitHub suspend les tâches planifiées d'un dépôt resté 60 jours sans activité : onglet Actions → « Enable workflow ». |

## 11. Variante : sur un serveur à toi

`bash setup.sh`, copie `.env.example` en `.env`, remplis les clés, puis installe `deploy/agent-video.service` et `deploy/agent-video.timer`
(systemd) : le minuteur lance `python3 run.py tick` aux mêmes heures.

## 12. Arborescence

```
run.py                     point d'entrée (tick, demo, bilan, doctor…)
config.yaml                tous les réglages
data/sujets.yaml           familles et idées de vidéos
data/faits.yaml            faits vérifiés (pages officielles)
data/rushs.yaml            bibliothèque de départ : 14 séquences libres de droits
examples/reserve/          6 storyboards prêts, pour tourner sans clé
engine/                    moteur de rendu (page HTML), polices, personnage (11 poses)
studio/strategist.py       choix du sujet, calendrier, notes
studio/writer.py           consigne du modèle, écran de fin, réserves
studio/schema.py           forme d'un storyboard
studio/garde.py            ce que l'agent n'a pas le droit de dire
studio/rushs.py            recherche, téléchargement et contrôle des séquences filmées
studio/llm.py              API Gemini (choix du modèle, quotas, corrections)
studio/timeline.py         synchronisation de l'image sur la voix
studio/produce.py          chaîne de fabrication
studio/voice.py, mix.py, music.py, render.py, qa.py    voix, son, rendu, contrôle qualité
studio/bilan.py            bilan automatique tous les 3 jours
studio/stats.py, publish/  statistiques et publication (Buffer, Meta, TikTok)
studio/scout.py            veille : faits reconfirmés, nouveaux faits vérifiés
state/                     mémoire de l'agent (vidéos, mesures, bilan, suites promises)
tests/                     51 tests
```

Polices : Montserrat (licence SIL Open Font). Personnage : créé pour ce compte. Musique et bruitages : générés par l'agent.
Séquences filmées : Pexels et Pixabay, sous leurs licences (usage gratuit, attribution non exigée, revente telle quelle interdite).
