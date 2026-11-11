# Agent vidéo — un compte de vidéos courtes qui tourne tout seul

Cet agent fabrique et publie des vidéos verticales de 40 à 70 secondes, sans personne aux commandes.
Depuis le 11 novembre 2026, il a **une seule spécialité : les prompts, les commandes et les techniques d'intelligence artificielle**.
Chaque vidéo est une démonstration que le spectateur peut refaire : « Ouvre l'outil. Copie exactement cette instruction. Voici ce que tu obtiens. »

Il choisit le sujet, écrit le texte, **essaie réellement l'instruction**, cherche de vraies séquences filmées dans des banques libres de droits,
fait le montage, range l'instruction dans sa **bibliothèque de prompts**, publie, relève les statistiques et corrige sa route tous les trois jours.
GitHub le réveille aux heures prévues ; ton ordinateur peut rester éteint.

Tant qu'aucune clé de publication n'est en place, il est en **mode essai** : il fabrique et contrôle les vidéos, rien n'est publié.

---

## 0. La ligne éditoriale

Public : des jeunes francophones qui débutent avec l'IA (étudiants, entrepreneurs, commerçants, créateurs, monteurs, graphistes).
Plus de conseils généraux de commerce, de réglages de caméra ou de montage : les six premières vidéos sont gardées comme historique (`examples/historique/`).

| Famille (`data/sujets.yaml`) | Part de départ | Ce qu'elle montre |
|---|---|---|
| Prompts ChatGPT, Gemini et Claude | 25 % | Un prompt précis, son texte exact, un extrait de la réponse |
| Commandes et fonctions méconnues | 15 % | Une commande ou un réglage **décrit par une page officielle** (jamais une commande inventée) |
| Business et entrepreneuriat | 15 % | Trouver une idée, une annonce, un prix — sans jamais promettre un gain |
| Images et création graphique | 15 % | **En attente** : il faut montrer l'image obtenue, ce qui demande une clé payante de création d'images |
| Vidéo et création audiovisuelle | 10 % | Scénario, storyboard : les instructions qui donnent le résultat |
| Études et productivité | 10 % | Professeur particulier, fiche de révision… |
| Hashtags et réseaux sociaux | 5 % | De vrais hashtags pour une publication — jamais présentés comme une commande d'IA |
| Autres outils et découvertes | 5 % | Un outil, avec une page officielle à l'appui |

Tant que la famille « Images » attend, sa part est répartie sur les autres. Le bilan corrige ensuite ces parts d'après les mesures.

La banque contient **20 sujets prioritaires**, dont **6 pour la série pilote** (marqués `pilote: true`, ils passent en premier) :
une idée de business avec ton budget · les instructions personnalisées de ChatGPT · ChatGPT en professeur particulier ·
le prompt qui cherche les faiblesses d'un projet · le scénario d'une publicité courte · les hashtags d'une page Facebook.
Deux storyboards de réserve sont écrits à l'avance (`examples/reserve/`) : `p1_business` et `p2_consignes`.

**Chaque instruction est vérifiée avant d'être montrée** (`studio/essai.py`) :

- un *prompt* est réellement envoyé à Gemini, ses [champs] remplis par un exemple ; l'écran « réponse » montre un extrait de cette vraie réponse,
  avec la mention « Réponse de Gemini · testée le … » ;
- une *commande* ou un *réglage* (ChatGPT, Claude Code…) : l'agent ne peut pas cliquer dans l'application ; il vérifie que la page officielle
  citée a été relue et confirmée le jour même (`data/faits.yaml`).

Une instruction non vérifiée n'est **jamais publiée**. Sans clé Gemini, une vidéo de prompt peut être fabriquée en essai (son écran « réponse » dit
alors « Exemple de réponse »), mais elle reste retenue.

**La bibliothèque de prompts** (`state/BIBLIOTHEQUE.md`, lisible sur GitHub) : chaque instruction montrée y a sa fiche — identifiant (P-0001), titre,
catégorie, outil, fonction, prompt complet, exemple, résultat attendu, personnalisation, date et mode de vérification, statut
(à vérifier · testé · validé · rejeté), vidéos. Deux instructions identiques ne font qu'une fiche. Les fiches « validé » sont la matière de l'e-book.

**L'e-book** (« La Bibliothèque ultime des prompts IA », 2 500 FCFA) n'est pas encore en vente : l'agent n'en parle dans aucune vidéo.
Le jour où il est en ligne, deux lignes de `config.yaml` suffisent : `offer.lien_bio` (son adresse) et `offer.ebook.en_vente: true`.
L'écran de fin dira alors la phrase prévue (e-book complet, 2 500 FCFA, lien en bio), avec ses variantes.

---

## 1. Ce qu'il te reste à faire : les clés

Tout se passe dans ton dépôt GitHub : **Settings → Secrets and variables → Actions → New repository secret**.
Une clé ne s'écrit jamais ailleurs (ni dans le code, ni dans une conversation).

| Nom du secret | À quoi il sert | Où l'obtenir (gratuit) | Sans lui |
|---|---|---|---|
| `GEMINI_API_KEY` | Le cerveau : écrit les scénarios, **essaie chaque prompt**, regarde les séquences filmées, rédige le bilan | https://aistudio.google.com/apikey — crée la clé dans un projet **sans facturation** | L'agent n'a que ses 2 vidéos de réserve, n'écrit rien de nouveau et **ne publie aucun prompt** (il ne peut pas le tester) |
| `PEXELS_API_KEY` | Cherche des séquences filmées sur Pexels | https://www.pexels.com/api/ (clé immédiate) | Seulement les 14 séquences de la bibliothèque de départ |
| `PIXABAY_API_KEY` | Cherche des séquences filmées sur Pixabay | https://pixabay.com/api/docs/ (la clé s'affiche une fois connecté) | idem |
| `BUFFER_API_KEY` | Publie sur Facebook, Instagram et TikTok, et lit les statistiques | https://buffer.com (offre gratuite : 3 canaux), puis *Settings → API* | Mode essai : rien n'est publié |

Les quatre ensemble = l'agent complet. À chaque réveil, il se sert de ce qu'il trouve.
**Conseil : ajoute `BUFFER_API_KEY` en dernier.** Avec les trois premières clés seulement, l'agent reste en mode essai : il écrit, teste et
fabrique de vraies vidéos, visibles dans l'onglet Actions, sans rien publier. Regarde-en deux ou trois (l'écriture et l'essai par Gemini n'ont encore
jamais tourné avec une vraie clé), puis ajoute la clé Buffer : à partir de là, tout part en ligne sans validation.
À la place de Buffer, les API officielles fonctionnent aussi : `FB_PAGE_ID` + `FB_PAGE_TOKEN`, `IG_USER_ID` + `IG_TOKEN`,
`TIKTOK_CLIENT_KEY` + `TIKTOK_CLIENT_SECRET` + `TIKTOK_REFRESH_TOKEN` (et `publish.via: native` dans `config.yaml`).

Facultatif, dans `config.yaml` : `brand.name` et `brand.handle` (le nom du compte, affiché sur l'écran de fin).

Pour vérifier : onglet **Actions → Agent vidéo → Run workflow → commande `doctor`**.

---

## 2. Le format des vidéos

Toutes les vidéos suivent la même grammaire, celle des comptes d'astuces qui retiennent leur public :

| Élément | Règle |
|---|---|
| Première image | Le titre de l'accroche est déjà lisible, le personnage est là, le premier visuel aussi. Pas de bonjour. |
| Sous-titres | En haut de l'écran, trois mots à la fois, le mot prononcé est surligné. |
| Écrans | 4 à 7 écrans de 5 à 15 secondes. Un point par écran, annoncé par une tuile numérotée (ÉTAPE 1, ÉTAPE 2…). |
| L'instruction | Une fenêtre au nom de l'outil affiche le **texte exact à copier**, tapé au clavier ; les [champs à remplacer] sont surlignés. Le même texte est dans la légende. |
| La réponse | Une fenêtre « Réponse de l'IA » montre 2 à 5 lignes de la réponse, et dit d'où elle vient (réponse réelle testée le jour même, ou exemple). |
| Rythme | Un élément nouveau apparaît au mot près : liste, cartes « avant / après », pictogrammes, séquence filmée. |
| Personnage | Une mascotte dessinée (11 poses) qui change de pose à chaque écran. |
| Séquences filmées | 1 à 3 par vidéo : la situation du spectateur (des mains sur un clavier, un vendeur et ses colis…). |
| Limite honnête | Un écran et une ligne de la légende disent ce qu'il faut vérifier (les chiffres d'une IA sont des estimations ; une fonction dépend de l'offre ou de la version). |
| Écran de fin | « Abonne-toi », un mot à commenter, et ce que la vidéo suivante apportera. |
| Légende | Accroche, étapes numérotées, 📋 l'instruction à copier, ligne ⚠️, consigne 💬, 🔔, hashtags, crédit des images. |

Identité : papier quadrillé, encre bleu nuit, surligneur jaune — les couleurs du personnage. Tout se règle dans `config.yaml` (`brand.couleurs`).

---

## 3. Ce que l'agent fait à chaque réveil

1. **Mesures** — il lit les statistiques de chaque vidéo publiée (24 h, 72 h, 7 jours) par l'API du réseau, et note chaque vidéo.
2. **Bilan** — tous les 3 jours : ce qui marche, ce qui ne marche pas, nouveaux poids des familles de sujets, rapport dans `state/BILAN.md`.
3. **Veille** — il rouvre les pages officielles et reconfirme chaque fait qu'il a le droit de citer.
4. **Choix** — d'abord le sujet annoncé par la vidéo précédente ; sinon la série pilote, puis une famille tirée selon ses parts et une idée jamais traitée.
   Le sujet de la vidéo **suivante** est choisi au même moment, dans la banque : la vidéo l'annonce à la fin, et l'agent le produit ensuite.
5. **Écriture** — Gemini écrit le storyboard et la fiche de l'instruction ; chaque refus des contrôles lui est renvoyé pour correction. Sans clé : une vidéo de réserve.
5 bis. **Essai de l'instruction** — le prompt est envoyé à Gemini tel qu'un utilisateur le saisirait ; l'écran « réponse » reprend un extrait fidèle de la vraie réponse.
6. **Séquences filmées** — recherche sur Pexels et Pixabay, téléchargement, trois contrôles (voir plus bas).
7. **Montage** — voix, sous-titres au mot près, musique et bruitages générés, rendu image par image.
8. **Contrôle qualité** — format, durée, son, lisibilité, sous-titres. Un seul échec et la vidéo n'est pas publiée.
9. **Bibliothèque** — la fiche de l'instruction est rangée (`state/BIBLIOTHEQUE.md`), avec son statut et l'identifiant de la vidéo.
10. **Publication** — sans validation humaine, seulement si l'instruction a été vérifiée ; puis la suite annoncée est inscrite pour être produite.

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
- ChatGPT, Gemini et Claude se nomment librement comme l'endroit où coller une instruction ; tout autre outil, et toute fonction, tout menu, tout « gratuit »,
  toute limite d'un outil demande un **fait vérifié** sur une page officielle (`data/faits.yaml`) ;
- **aucune commande inventée** : une commande (/mot) n'est montrée que si une page officielle citée la contient ; une commande de Claude Code n'est jamais
  présentée comme une commande de Claude ; un hashtag n'est jamais présenté comme une commande d'IA ;
- aucun chiffre avancé par le compte sans source (les chiffres de l'exemple et ceux de la réponse affichée sont ceux de l'IA, et la vidéo le dit) ;
- l'e-book n'est annoncé que par l'écran de fin, et seulement quand il est en vente ;
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

| Brique | État au 11/11/2026 (soir) |
|---|---|
| Nouvelle ligne éditoriale : banque de sujets, familles, consigne d'écriture, garde-fous, bibliothèque | **En place.** 69 tests automatiques passent (`python3 -m unittest discover -s tests`). |
| Les deux vidéos de réserve (`p1_business`, `p2_consignes`) | **Fabriquées en entier** (52 à 56 s, 1080×1920, contrôle qualité réussi). Une transcription automatique retrouve le texte prévu ; « prompt » et « ChatGPT » sont maintenant prononcés correctement (réglés dans `voice.pronounce`). **Personne n'a écouté ces vidéos.** |
| Réglage vérifié sur une page officielle (`p2_consignes`) | **A tourné** : page d'aide d'OpenAI lue le 11/11/2026 (à la main : elle refuse les robots, valable 90 jours). Trois autres pages officielles sont rouvertes automatiquement chaque jour. |
| Essai réel d'un prompt sur Gemini, extrait de la vraie réponse | **Jamais exécuté avec une vraie clé.** Testé contre un faux serveur Gemini. Tant qu'il n'a pas tourné, la vidéo `p1_business` montre un *exemple* de réponse (écrit à l'avance) et ne peut pas être publiée. |
| Écriture des nouvelles vidéos par Gemini | **Jamais exécutée avec une vraie clé.** La qualité des textes se jugera sur les premières vidéos. |
| Famille « Images et création graphique » | **En attente** : aucun moyen gratuit de créer l'image du résultat par l'API. |
| E-book | **Non annoncé** (il n'est pas en vente). Phrase et écran prêts, éteints. |
| Recherche Pexels / Pixabay par leurs API, publication et statistiques par Buffer | **Jamais exécutées pour de vrai** (aucune clé en place) ; testées contre des réponses de même forme. |
| Réveils automatiques de GitHub | **Aucun n'a eu lieu** le 11/11/2026 (jour de création du dépôt) : ni celui de 11 h 20, ni celui de 16 h 40 UTC. Toutes les exécutions réussies ont été lancées à la main (bouton « Run workflow »). À surveiller dans l'onglet Actions : une ligne marquée « Scheduled ». |

---

## 8. Régler l'agent (`config.yaml`)

| Réglage | Effet |
|---|---|
| `brand.*` | Nom du compte, identifiant, promesse, public, couleurs, mention de fin. |
| `offer.cta` | La phrase de fin (`MOT` = le mot à commenter, `PROMESSE` = la suite annoncée). |
| `offer.lien_bio`, `offer.ebook.en_vente` | Les deux remplis : l'e-book est annoncé à la fin de chaque vidéo (prix, lien en bio). Sinon l'agent n'en parle pas. |
| `editorial.*` | Les outils qu'on peut nommer librement, ceux qui demandent une page officielle, et l'essai réel des prompts (`test_prompts`). |
| `schedule.*` | Vidéos par jour (2), jours, créneaux candidats. L'agent apprend lesquels marchent. Si tu changes les créneaux, change aussi les lignes `cron` du fichier `.github/workflows/agent.yml`. |
| `video.seconds` | Durée visée (38 à 70 s). Hors format, la voix est rejouée une fois à un autre débit. |
| `voice.*`, `audio.*` | Voix, débit, prononciations, musique, marge de la voix sur le fond. |
| `rushs.*` | Contrôle par l'image, seuils d'acceptation, nombre de candidates regardées, repos d'une séquence déjà utilisée. |
| `publish.dry_run` | `auto` (essai tant qu'aucune clé de publication n'existe), `true` (toujours essai), `false` (publication réelle). |
| `publish.networks`, `publish.via` | Réseaux visés ; Buffer ou API officielles. |
| `bilan.*`, `strategy.*` | Rythme du bilan, minimum de vidéos, ampleur des corrections, part d'essais, délai avant de refaire un sujet. |

Les sujets sont dans `data/sujets.yaml` (8 familles, 20 sujets prioritaires), les faits dans `data/faits.yaml`,
la bibliothèque de séquences dans `data/rushs.yaml`, les vidéos de réserve dans `examples/reserve/`, les six premières vidéos dans `examples/historique/`.
Pour ajouter un sujet : une ligne dans `data/sujets.yaml` (`id`, `famille`, `outil`, `sujet`, `angle`).

## 9. Commandes

Dans l'onglet **Actions → Agent vidéo → Run workflow**, ou sur un ordinateur (`bash setup.sh` puis `python3 run.py …`) :

| Commande | Ce qu'elle fait |
|---|---|
| `tick` | Le réveil normal. Coche « forcer » pour fabriquer une vidéo tout de suite. |
| `demo` | Rend les vidéos de réserve, sans rien publier. |
| `bilan` | Fait le bilan maintenant. |
| `doctor` | Vérifie l'installation, les clés (appel d'essai), les faits, les réserves. |
| `plan` | Le plan du jour et la prochaine vidéo. |
| `sujets` | La banque d'idées (★ = série pilote), les parts des familles, les suites promises. |
| `bibliotheque` | La bibliothèque de prompts : chaque instruction montrée, son statut, ses vidéos. |
| `rushs` | Essaie une recherche de séquence comme le ferait l'agent (champ « mots », en anglais). |
| `veille` | Rouvre les pages officielles et liste les faits confirmés. |

Les vidéos d'une exécution se téléchargent dans **Actions → l'exécution → Artifacts** pendant 14 jours.

## 10. Arrêter l'agent, dépannage

- **Tout arrêter** : `publish.dry_run: true` dans `config.yaml` (plus rien n'est publié), ou onglet Actions → Agent vidéo → « … » → *Disable workflow*.

| Message | Cause probable |
|---|---|
| « MODE ESSAI » | Aucune clé de publication, ou `dry_run: true`. |
| « rien à produire » | Sans `GEMINI_API_KEY`, les réserves ont toutes été publiées depuis moins de 21 jours. |
| « instruction non vérifiée » | Un prompt n'a pas pu être testé (pas de clé Gemini, quota du jour atteint) ou la page officielle d'une commande n'est plus confirmée : la vidéo est fabriquée mais retenue. |
| « commande … : aucune page officielle citée ne la décrit » | Le modèle a écrit une commande qui n'est dans aucun fait vérifié : le refus lui est renvoyé. Rien à faire. |
| « écriture par le modèle impossible » | Clé absente, quota du jour atteint, ou trois réponses refusées par les contrôles : l'agent prend une réserve. |
| « rushs : rien d'acceptable pour … » | Aucune séquence ne passe les contrôles : l'agent change de sujet. |
| « formulation interdite », « outil nommé sans fait vérifié » | Le modèle a écrit quelque chose que les garde-fous refusent : le refus lui est renvoyé. Rien à faire. |
| « CHANGEMENT sur … » | Une page officielle ne contient plus la phrase attendue : le fait est suspendu. |
| « PUBLICATION RETENUE » | Contrôle qualité en échec, fait suspendu ou instruction non vérifiée : la raison suit. |
| « aucun réseau n'a reçu la vidéo » | Clé Buffer invalide, canal déconnecté, ou vidéo refusée : le détail est dans le journal. |
| « rendu trop lent » | La machine manque de mémoire ou le navigateur est bloqué : l'agent arrête ce rendu et réessaie au réveil suivant. |
| « Impossible d'installer ffmpeg » | Ni le téléchargement direct ni le gestionnaire de paquets n'ont répondu : panne de réseau passagère, le réveil suivant reprend. |
| Les réveils s'arrêtent | GitHub suspend les tâches planifiées d'un dépôt resté 60 jours sans activité : onglet Actions → « Enable workflow ». |
| Aucun réveil automatique (aucune ligne « Scheduled » dans l'onglet Actions) | Constaté le 11/11/2026, jour de création du dépôt. En attendant : « Run workflow », commande `tick`, case « forcer ». Si cela dure, il faut un réveil extérieur (un service gratuit qui appuie sur ce bouton aux heures voulues). |

## 11. Variante : sur un serveur à toi

`bash setup.sh`, copie `.env.example` en `.env`, remplis les clés, puis installe `deploy/agent-video.service` et `deploy/agent-video.timer`
(systemd) : le minuteur lance `python3 run.py tick` aux mêmes heures.

## 12. Arborescence

```
run.py                     point d'entrée (tick, demo, bilan, doctor…)
config.yaml                tous les réglages
data/sujets.yaml           les 8 familles, leur part, les 20 sujets prioritaires (★ série pilote)
data/faits.yaml            faits vérifiés (pages officielles) : fonctions, menus et commandes qu'on a le droit de montrer
data/rushs.yaml            bibliothèque de départ : 14 séquences libres de droits
examples/reserve/          2 storyboards prêts (business, instructions personnalisées), pour tourner sans clé
examples/historique/       les six premières vidéos (ancienne ligne éditoriale), gardées, plus produites
engine/                    moteur de rendu (page HTML), polices, personnage (11 poses)
studio/strategist.py       choix du sujet, calendrier, notes
studio/writer.py           consigne du modèle, écran de fin, réserves
studio/schema.py           forme d'un storyboard
studio/garde.py            ce que l'agent n'a pas le droit de dire (dont : aucune commande inventée)
studio/essai.py            l'essai de chaque instruction avant de la montrer (Gemini, ou page officielle)
studio/bibliotheque.py     la bibliothèque de prompts (state/BIBLIOTHEQUE.md)
studio/porte.py            ce qui doit être vrai pour qu'une vidéo soit publiée
studio/rushs.py            recherche, téléchargement et contrôle des séquences filmées
studio/llm.py              API Gemini (choix du modèle, quotas, corrections)
studio/timeline.py         synchronisation de l'image sur la voix
studio/produce.py          chaîne de fabrication
studio/voice.py, mix.py, music.py, render.py, qa.py    voix, son, rendu, contrôle qualité
studio/bilan.py            bilan automatique tous les 3 jours
studio/stats.py, publish/  statistiques et publication (Buffer, Meta, TikTok)
studio/scout.py            veille : faits reconfirmés, nouveaux faits vérifiés
state/                     mémoire de l'agent (vidéos, mesures, bilan, suites promises, bibliothèque de prompts)
tests/                     69 tests
```

Polices : Montserrat (licence SIL Open Font). Personnage : créé pour ce compte. Musique et bruitages : générés par l'agent.
Séquences filmées : Pexels et Pixabay, sous leurs licences (usage gratuit, attribution non exigée, revente telle quelle interdite).
