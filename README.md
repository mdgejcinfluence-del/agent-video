# Agent vidéo — des démonstrations « preuve à l'appui » pour deux publics, qui mènent à ta formation

Un programme qui se réveille seul, vérifie ses sources, choisit un sujet, écrit le scénario, fabrique
la vidéo (motion design, voix, sous-titres, musique), contrôle ce qu'elle affirme, puis la présente
à ta validation avant de la publier sur TikTok, Instagram et Facebook. Coût des services : 0 €.

```
réveil ─► mesures ─► veille ─► stratège ─► scénariste ─► garde-fous ─► voix ─► rendu ─► contrôle ─► porte de publication ─► mémoire
          (Buffer)   (pages     (public,    (NVIDIA →     (preuve,      (edge →  (HTML →   qualité     (preuve signée, promo     (state/)
                     officielles) sujet,     Groq → …,     nombres,      Piper)   MP4)                  confirmée, ta validation)
                                 preuve)    ou réserve)   formulations)
```

## Le positionnement

Tiré de l'étude de marché du 11 novembre 2026 : on ne vend pas « Claude sait faire des vidéos ».
On montre **un résultat utile à une personne précise**, on prouve comment il a été obtenu, et on
vend la méthode pour le refaire avec ses propres éléments.

**Deux publics, deux séries, jamais mélangés dans une même vidéo.**

| | Série « Vidéos pour ton commerce » | Série « Motion design reproductible » |
|---|---|---|
| Pour qui | commerçants, artisans, prestataires | créateurs de contenu et freelances |
| Ce que la vidéo montre | un produit, une offre, une publicité prête à publier | une demande écrite, le code, l'aperçu, la correction, le rendu |
| Ce qu'on n'y voit jamais | du code, un terminal, une liste d'outils | une promesse de revenu, de vues ou de « remplacement d'un monteur » |
| Identité visuelle | ivoire, vert profond, jaune | nuit, violet, citron |

**Pas de preuve, pas de vidéo.** Une vidéo ne montre que ce qui existe dans un dossier
`preuves/<id>/` : la demande écrite, le code réellement écrit, les images et les vidéos réellement
rendues. Le moteur ne dessine aucun faux écran. Quand l'exemple est inventé, la mention
« EXEMPLE FICTIF » reste à l'écran du début à la fin.

**Le fil d'une vidéo (35 à 45 secondes), toujours le même :**

| Moment | Ce qui se passe |
|---|---|
| 0–5 s | Le résultat est à l'image dès la première image ; la voix dit l'accroche, puis nomme la personne. |
| 5–25 s | Trois étapes liées, chacune avec sa preuve : extrait de la demande, lignes de code, rendu, avant/après, défaut entouré puis corrigé. |
| 25–33 s | Ce qui a été vérifié, et une limite utile : un prérequis, un coût, ce qui n'est pas inclus. |
| 33–45 s | La phrase de fin, dite et écrite mot pour mot, identique pour les deux publics. |

**La phrase de fin** : « Commente MOT si tu veux la suite. La formation complète est en promo, lien
en bio. » `MOT` est remplacé par le mot-clé de la vidéo ; rien d'autre ne change. Elle est écrite
par le code : le modèle ne peut ni la reformuler ni y ajouter une amorce. Aucun envoi n'est promis
(commenter ne fait rien recevoir). « La suite » est la vidéo suivante de la même série : l'agent
vérifie qu'elle existe avant de publier.

## Ce que tu dois fournir pour publier

L'agent prépare tout seul. Il ne publie que lorsque ces points sont vrais — et c'est toi qui les rends vrais :

1. **De vrais cas.** Les deux dossiers fournis servent à montrer le format :
   `createur-intro-serie` (une vraie démonstration, à relire et à signer) et
   `commerce-karite-exemple` (**exemple fictif** : produit, prix et photo inventés).
   Pour la série commerce, il faut la photo, le prix et la consigne d'un vrai commerce :
   voir [`preuves/LISEZMOI.md`](preuves/LISEZMOI.md).
2. **Ta signature sur chaque dossier** (`valide_par` dans `preuve.yaml`) : tu as vérifié le produit,
   le prix, les droits et les affirmations.
3. **La promotion** : `offer.promo.confirmee: true` et sa date de fin dans `config.yaml`. La phrase
   de fin dit « en promo » ; après la date, la publication se suspend toute seule.
4. **La page d'aiguillage** (`offer.lien_bio`) : le lien de ta bio, avec deux boutons visibles,
   « Commerçant » et « Créateur / freelance », chacun vers sa page de vente.
5. **Les 3 clés** (plus bas), puis `publish.dry_run: false`.

Ensuite, chaque vidéo attend ton accord (réglage `publish.validation`). `python3 run.py doctor`
et `python3 run.py plan` te disent à tout moment ce qui manque.

---

## Où on en est : ce qui a tourné, ce qui n'a pas tourné

| Brique | État au 11/11/2026 |
|---|---|
| Moteur de rendu v2, voix, mixage, contrôle qualité | **A tourné** en local : les 6 vidéos de réserve passent tous les contrôles ; une vidéo complète sort en 2 minutes (36,5 s, 1080×1920, 30 img/s, −14,2 LUFS). |
| Dossiers de preuve | **Réels pour la technique** : les rendus de `preuves/*/media/` ont été calculés par Remotion 4.0.542 à partir du projet `preuves/projet-remotion/` (rejoués à l'identique, à l'octet près). Le premier rendu défectueux et sa correction sont de vrais rendus. **Fictif pour le commerce** : produit, prix et photo d'exemple. |
| Veille des faits | **A tourné** : les 4 pages officielles de Remotion ont été rouvertes et les 6 faits reconfirmés (licence gratuite jusqu'à 3 personnes, tarifs, principe du rendu). |
| Garde-fous (preuve mot pour mot, nombres, formulations, un seul public, phrase de fin) | **60 tests automatiques passent** (`python3 -m unittest discover -s tests`). |
| Chaîne complète en mode essai, sans aucune clé | **A tourné** en local (`python3 run.py make --no-publish`). Sur GitHub : voir l'onglet *Actions*. |
| Écriture du scénario par NVIDIA / Groq | **Pas encore testée avec un vrai modèle** (aucune clé en place). Le dialogue est testé contre un faux serveur, y compris le refus d'un extrait reformulé. La qualité des scénarios se jugera sur les premiers essais. |
| Attente de validation, puis publication | Logique testée (faux hébergement, faux Buffer). **Jamais exécutée pour de vrai.** |
| Publication et mesures par Buffer | **Jamais envoyé au vrai Buffer.** Requêtes écrites d'après sa documentation. |
| YouTube Shorts | Le texte est préparé dans chaque fiche de production ; **la publication n'est pas reliée** (l'offre gratuite de Buffer couvre 3 canaux). |
| Son | Mesuré par le calcul (voix 22 dB au-dessus du fond). **Personne n'a écouté ces vidéos** : écoute-les. |

---

## Mise en route sur GitHub

Le code est dans le dépôt, la tâche planifiée est dans `.github/workflows/agent.yml`. Il reste :

1. **Ajouter les 3 clés** dans *Settings → Secrets and variables → Actions → New repository secret* :

   | Nom du secret | Où l'obtenir (gratuit, sans carte) | Rôle |
   |---|---|---|
   | `NVIDIA_API_KEY` | build.nvidia.com → *Get API Key* | écrit les scénarios (premier choix) |
   | `GROQ_API_KEY` | console.groq.com → *API Keys* | écrit les scénarios (secours) |
   | `BUFFER_API_KEY` | publish.buffer.com/settings/api | publie et lit les mesures |

   Aucune clé n'est écrite dans le code : il ne lit que ces variables.
2. **Préparer Buffer.** Compte gratuit sur buffer.com → connecte tes 3 canaux : TikTok, Instagram
   (compte professionnel ou créateur) et ta Page Facebook → crée la clé d'API.
3. **Regarder un essai.** Onglet *Actions* → « Agent vidéo » → ouvre la dernière exécution. Le
   résumé montre le journal (public, sujet, preuve, durée, contrôle qualité, ce qui bloquerait la
   publication). En bas de page, *Artifacts* contient la vidéo **et sa fiche de production**
   (`.md`). Pour lancer un essai tout de suite : *Run workflow* → commande `tick`, case « forcer ».
   Les essais alternent les deux séries.
4. **Remplir ce qui manque** (section précédente), puis passer `publish.dry_run` à `false`.
5. **Valider chaque vidéo.** Quand une vidéo est prête, le journal donne son adresse pour la
   regarder et son identifiant. Pour la publier : *Run workflow* → commande `valider`, champ
   « vidéo » = l'identifiant (ou `tout`). Une vidéo non validée en 7 jours est abandonnée.

GitHub Pages sert la branche `studio-media` : c'est là que la vidéo attend ta validation et que
Buffer vient la chercher. Le réglage est déjà fait sur ce dépôt.

### Mode essai et publication réelle

| | `dry_run: true` (essai) | `dry_run: false` (réel) |
|---|---|---|
| Vidéo fabriquée et contrôlée, fiche de production écrite | oui | oui, si rien ne bloque |
| Sujets | tournent en boucle, rien n'est consommé | chaque sujet × accroche ne sert qu'une fois en 21 jours |
| Exemple fictif | montré (étiqueté) | **jamais publié**, sauf `publish.exemples_fictifs: true` |
| Si une condition manque (preuve non signée, promo non confirmée, pas de suite…) | le journal dit ce qui bloquerait | **aucune vidéo n'est fabriquée**, le journal dit quoi corriger |
| Envoi sur les réseaux | non | après ta validation (ou directement si `validation: preuve_signee`) |
| S'il n'y a plus rien d'honnête à produire | — | l'agent s'arrête et te dit quelle preuve ajouter |

---

## Les dossiers de preuve

```
preuves/
  createur-intro-serie/      preuve.yaml · demande.md · correction.md · media/ (rendu, premier rendu raté, version sans charte)
  commerce-karite-exemple/   EXEMPLE FICTIF — preuve.yaml · demande.md · correction.md · media/ (photo, rendus)
  projet-remotion/           le projet qui a produit ces rendus (npm install, puis npx remotion studio src/index.ts)
```

`preuve.yaml` dit ce que la vidéo a le droit d'affirmer (`faits`), ce qu'il faut savoir (`limites`),
les sujets couverts (`sujets`) et, pour un commerce, l'offre exacte (`offre`). Le code contrôle :

- un extrait de demande affiché doit se retrouver **mot pour mot** dans `demande.md` ou `correction.md` ;
- une ligne de code affichée doit se retrouver **telle quelle** dans un fichier du projet ;
- un nombre dit ou affiché doit figurer dans le dossier ou dans un fait vérifié par la veille ;
- un média cité doit exister.

Ajouter un vrai cas : [`preuves/LISEZMOI.md`](preuves/LISEZMOI.md). Vérifier : `python3 run.py preuves`.

## La banque de sujets et la note

`data/sujets.yaml` contient les 16 sujets de l'étude, dans l'ordre de lancement : motion design,
puis visuels, sites, contenus. Chaque sujet reçoit une note de 0 à 5 :

| Critère | Poids | D'où vient la valeur |
|---|---:|---|
| Intensité du problème pour ce public | 30 % | estimation de départ dans `sujets.yaml` (à corriger avec tes retours) |
| Preuve visuelle réelle | 25 % | calculée : 0 sans dossier, 2 exemple fictif, 4 réel, 5 réel et signé |
| Signal de demande vérifiable | 20 % | tes mesures, ou ce que tu saisis (`demande`) ; **0 tant que rien n'est mesuré**, et la fiche le dit |
| Adéquation à la formation | 15 % | estimation de départ dans `sujets.yaml` |
| Fraîcheur vérifiée | 10 % | calculée : faits reconfirmés par la veille, actualité récente des outils |

C'est un outil de tri interne, pas une prévision. Aujourd'hui, 6 sujets sur 16 ont une preuve :
`python3 run.py sujets` montre la liste et ce qu'il faut fournir pour les autres.

**Comment il choisit.** Les deux séries alternent (une vidéo par public et par jour). Pour un
public : d'abord les sujets jamais traités, dans l'ordre des thèmes puis par note ; ensuite un
sujet déjà traité, avec **la même preuve et une autre accroche** (résultat d'abord, problème
d'abord, contraste). On ne change qu'un facteur à la fois.

## La veille quotidienne

`data/faits.yaml` liste les seuls prix, licences et fonctionnalités d'outils qu'une vidéo peut
citer, avec leur page officielle et la phrase qui doit s'y trouver. Chaque jour, l'agent rouvre ces
pages. Si la phrase a disparu, le fait est suspendu, les vidéos qui le citent ne partent plus, et le
journal écrit « CHANGEMENT ». Un fait non reconfirmé depuis 3 jours n'est plus utilisable.
« Gratuit » et « open source » ne passent que dans une phrase qui porte leur précision
(« gratuite jusqu'à 3 personnes »). Seules des pages publiques sont lues.

## La fiche de production

Pour chaque vidéo, `out/<id>.md` (dans *Artifacts*) contient, dans cet ordre : 1. fiche stratégie ·
2. sources et veille · 3. références publiques observées · 4. trois accroches et celle retenue ·
5. script minuté (durées mesurées) · 6. storyboard · 7. phrase de fin, état de la promotion et du
lien en bio · 8. pack de publication pour TikTok, Instagram Reels, YouTube Shorts et Facebook Reels ·
9. contrôle avant publication. C'est le document à relire avant de valider.

## Les mesures

À 24 h, 72 h et 7 jours, l'agent relève ce que les réseaux donnent. La note de qualité d'une vidéo
compare la part regardée, les partages, les enregistrements et les commentaires à ceux des vidéos
**du même public sur le même réseau** ; les vues servent de dénominateur, jamais de score. Il faut
3 vidéos comparables avant toute note. L'agent ne voit ni les clics sur ton lien ni les ventes :
saisis-les dans `data/mesures.yaml`. Sans eux, il ne dira jamais qu'une vidéo « vend ».

---

## Régler l'agent (`config.yaml`)

| Réglage | Effet |
|---|---|
| `segments.*` | Les deux publics : cible, ce qu'ils veulent, règles d'écriture, étiquette de série, couleurs, page de vente. |
| `offer.cta` | La phrase de fin (doit contenir `MOT`). À ne changer que par décision de ta part, par exemple quand la promotion s'arrête. |
| `offer.cta_mot_fixe` | Vide : un mot-clé par vidéo. Rempli : le même mot dans toutes les vidéos. |
| `offer.promo`, `offer.lien_bio` | Ce qui rend la phrase de fin vraie. Sans eux, rien n'est publié. |
| `schedule.videos_per_day`, `schedule.jours`, `schedule.slots` | 2 vidéos par jour par défaut. L'étude conseille de commencer par 2 par public et par semaine : `videos_per_day: 1` et `jours: [1, 2, 4, 5]`. Si tu changes les créneaux, change aussi les lignes `cron` de `.github/workflows/agent.yml`. |
| `video.seconds` | Format visé (35–45 s). Si la vidéo sort hors format, la voix est rejouée une fois à un autre débit. |
| `voice.*`, `audio.*` | Voix, débit, prononciations, niveau de la musique, marge de la voix sur le fond. |
| `publish.validation` | `chaque_video` (chaque vidéo attend ton accord) ou `preuve_signee` (un dossier signé suffit). |
| `publish.exemples_fictifs` | `false` : un exemple fictif n'est jamais publié. |
| `publish.dry_run` | `true` : mode essai. |
| `strategy.repeat_days`, `strategy.explore` | Délai avant de refaire un sujet à l'identique ; part d'essais dans le choix de l'accroche et des créneaux. |

## Commandes

```bash
python3 run.py tick --force                          # fabrique une vidéo tout de suite
python3 run.py make --segment commercant --no-publish  # une vidéo pour un public précis, sans rien publier
python3 run.py demo                                  # une vidéo d'exemple par public
python3 run.py plan                                  # plan du jour, prochaine vidéo de chaque série, ce qui bloque
python3 run.py sujets                                # les 16 sujets notés
python3 run.py preuves                               # état des dossiers de preuve
python3 run.py veille                                # rouvre les pages officielles maintenant
python3 run.py attente                               # vidéos qui attendent ta validation
python3 run.py valider 20261112-0730-photo           # publie une vidéo que tu as regardée
python3 run.py doctor --live                         # outils, clés, preuves, faits, porte de publication, hébergement
```

## Ce qu'il faut savoir avant de publier

- **L'agent n'invente pas tes preuves.** Avec les 2 dossiers fournis, chaque série couvre 3 sujets :
  3 vidéos par série sans clé de modèle (les scénarios de réserve), 9 au plus avec un modèle
  (3 sujets × 3 accroches). Ensuite il s'arrête, jusqu'à ce que tu ajoutes un dossier ou que
  21 jours soient passés. À 2 vidéos par jour, cela fait 3 à 9 jours : chaque nouveau dossier
  ouvre de nouveaux sujets.
- **Licence de Remotion** (vérifiée le 11/11/2026 sur remotion.dev) : gratuite pour les particuliers
  et les organisations jusqu'à 3 personnes, payante au-delà ; ce n'est pas un logiciel open source.
  L'agent ne se sert pas de Remotion pour fabriquer ses vidéos (il a son propre moteur) : Remotion
  n'a servi qu'à produire les démonstrations des dossiers de preuve.
- **« Écrit par Claude Code » ?** Le code des démonstrations fournies a été écrit par un agent de
  code pendant la préparation, pas dans ta session Claude Code. Les vidéos disent « un agent de
  code, comme Claude Code ». Pour dire « c'est Claude Code qui l'a écrit », refais la démonstration
  chez toi avec `demande.md`, remplace les fichiers, et signe.
- **TikTok.** Sans Buffer, une application TikTok non auditée ne publie qu'en privé. Avec Buffer,
  c'est public, mais sans son tendance.
- **Étiquette « généré par IA ».** Activée par défaut (`publish.ai_label`) : la voix est synthétique.
- **Conditions des services gratuits.** NVIDIA réserve son offre gratuite au test ; edge-tts est
  un service non officiel ; la voix Piper demande de créditer « SIWIS ». Détails dans `docs/STACK.md`.
- **Conditions de GitHub.** Elles réservent Actions au développement du logiciel du dépôt et
  n'autorisent pas Pages comme hébergement gratuit d'une activité commerciale. Un robot qui publie
  des vidéos pour vendre une formation sort de ce cadre : GitHub peut arrêter la tâche ou fermer
  le dépôt. La variante « serveur à toi » ci-dessous n'a pas ce risque.

## Dépannage

| Symptôme | Cause probable |
|---|---|
| « PUBLICATION SUSPENDUE » | Une condition manque : la liste numérotée qui suit dit laquelle (preuve non signée, promotion, lien en bio, suite, exemple fictif). |
| « rien à produire pour la série… » | Tous les sujets couverts par une preuve ont été traités récemment : ajoute un dossier de preuve. |
| « écriture par le modèle impossible » | Clé absente ou quota du jour atteint : l'agent prend un scénario de réserve (3 par série). |
| « … refusée : extrait introuvable mot pour mot » | Le modèle a reformulé la demande : le refus lui est renvoyé, il corrige. Rien à faire. |
| « CHANGEMENT sur … » | Une page officielle ne contient plus la phrase attendue : relis-la et corrige `data/faits.yaml`. |
| « aucun réseau n'a reçu la vidéo » | Clé Buffer absente, canal déconnecté, ou vidéo refusée : le détail est dans le journal. |
| Les réveils GitHub s'arrêtent | GitHub suspend les tâches planifiées d'un dépôt public resté 60 jours sans activité : onglet *Actions* → « Agent vidéo » → *Enable workflow*. |

## Variante : sur un serveur à toi

```bash
git clone <adresse du dépôt> agent && cd agent
bash setup.sh                         # ffmpeg, Python, Chromium
cp .env.example .env && nano .env     # tes clés (dont CLOUDINARY_URL)
python3 run.py doctor
sudo cp deploy/agent-video.* /etc/systemd/system/     # adapte User= et WorkingDirectory= dans le .service
sudo systemctl daemon-reload && sudo systemctl enable --now agent-video.timer
```

Dans `config.yaml` : `publish.media_host: cloudinary`. Le rendu a été testé sur une machine de
2 cœurs et 2 Go de mémoire ; pas en dessous. Cette variante n'a jamais été exécutée de bout en bout.

## Arborescence

```
run.py                     point d'entrée (toutes les commandes)
config.yaml                les réglages : publics, phrase de fin, promotion, calendrier, publication
data/                      sujets.yaml (16 sujets) · faits.yaml (faits vérifiés) · references.yaml · mesures.yaml (clics et ventes, à la main)
preuves/                   les dossiers de preuve + le projet Remotion qui a produit les rendus
examples/reserve/          6 scénarios écrits à l'avance (3 par série), soumis aux mêmes contrôles
studio/                    strategist (choix) · writer (scénario + phrase de fin) · garde (fond) · schema (forme) · preuves · porte (publication)
                           fiche (fiche de production) · scout (veille) · llm · voice · align · music · mix · timeline · render · qa · produce
                           publish/ (packs par plateforme, buffer, meta, tiktok) · stats · mediahost · state
engine/                    moteur de rendu : player.html / .css / .js + polices
tests/                     60 tests automatiques
.github/workflows/         la tâche planifiée GitHub
deploy/                    variante serveur (systemd)
docs/                      STACK.md
state/                     mémoire de l'agent (remplie au fil des réveils)
```
