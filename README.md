# Agent vidéo — 2 vidéos motion design par jour sur « créer avec Claude », qui renvoient vers ta formation

Un programme qui se réveille seul, lit les statistiques de tes vidéos, décide du prochain sujet,
écrit le scénario, fabrique la vidéo (motion design, voix, sous-titres, musique), la publie sur
TikTok, Instagram et Facebook, puis retient le résultat pour la fois suivante. Coût : 0 €.

```
réveil ─► statistiques ─► stratège ─► veille ─► scénariste ─► voix ─► son ─► rendu ─► contrôle ─► publication ─► mémoire
           (Buffer)     (formats qui   (GitHub)   (NVIDIA →     (edge →  (musique  (HTML →    qualité     (Buffer :      (state/)
                         marchent)                Groq → …)     Piper)   générée)  MP4)                   TikTok+IG+FB)
```

## La ligne du compte

- **De quoi parlent les vidéos.** De ce que Claude et Claude Code savent fabriquer : d'abord des
  vidéos motion design propres, ensuite des visuels, des sites, des contenus. Chaque vidéo donne
  envie d'apprendre à le faire soi-même. La veille ne retient que des sujets de ce domaine
  (`research.require_any` dans `config.yaml`).
- **Comment elles se terminent, toutes.** La voix dit : « Commente MOT si tu veux la suite. La
  formation complète est en promo, lien en bio. » L'écran affiche le mot-clé, puis « la formation
  est en promo, lien en bio ». La légende du post finit de la même façon.
- **Commenter ne fait rien recevoir.** Le commentaire sert à la portée de la vidéo. L'agent ne
  promet jamais un envoi, un guide ou un cadeau : cette fin est écrite par le code, mot pour mot,
  et le modèle ne peut pas la changer (`offer.cta_*` dans `config.yaml` pour la reformuler).
- **Le lien en bio est celui de ta page de vente.** C'est toi qui le places dans la bio de chaque
  réseau. L'agent ne publie aucun lien.

Exemple produit par cette chaîne : `python3 run.py demo` fabrique `out/demo.mp4` (40,8 s). Le
scénario de cet exemple est écrit à la main (`examples/demo_storyboard.json`) ; tout le reste sort
de la chaîne. Détail des services gratuits, de leurs quotas et de leurs conditions :
[`docs/STACK.md`](docs/STACK.md).

---

## Où on en est : ce qui a tourné, ce qui n'a pas tourné

| Brique | État au 11/11/2026 |
|---|---|
| Moteur de rendu, voix (edge et Piper), mixage, contrôle qualité | **A tourné** : la vidéo d'exemple en sort (1080×1920, 30 img/s, −14,2 LUFS). |
| Veille GitHub filtrée sur la ligne du compte | **A tourné.** |
| Chaîne complète en mode essai, sans aucune clé | **A tourné** : `python3 run.py tick --force` va du réveil à la vidéo en un peu plus de 2 minutes (scénario de réserve). |
| Logique interne (repères voix/image, réparation du scénario, fin imposée, mode essai, apprentissage du stratège, quotas, mesure du son) | **32 tests automatiques passent** (`python3 -m unittest discover -s tests`). |
| Tâche GitHub Actions | Voir l'onglet *Actions* du dépôt. |
| Écriture du scénario par NVIDIA / Groq | **Pas encore testée avec un vrai modèle** (aucune clé en place). Le dialogue avec le modèle est testé contre un faux serveur ; la qualité des scénarios se jugera sur les premiers essais. |
| Publication et statistiques par Buffer | **Jamais envoyé au vrai Buffer.** Requêtes écrites d'après sa documentation et testées contre un faux serveur. |
| Publication native Meta et TikTok, Cloudinary, voix Gemini | Écrites d'après les documentations, **non testées**. |
| Son (voix, musique, bruitages) | Mesuré par le calcul. Sur l'exemple : la voix dépasse le fond de 22 dB entre 1 et 4 kHz, et une transcription automatique de la vidéo finale retrouve tout le texte (elle note « Cloud » pour « Claude », qui se prononcent presque pareil en français). |

---

## Mise en route sur GitHub

Le code est dans le dépôt, la tâche planifiée est dans `.github/workflows/agent.yml`. Il reste :

1. **Ajouter les 3 clés** dans *Settings → Secrets and variables → Actions → New repository secret* :

   | Nom du secret | Où l'obtenir (gratuit, sans carte) | Rôle |
   |---|---|---|
   | `NVIDIA_API_KEY` | build.nvidia.com → *Get API Key* | écrit les scénarios (premier choix) |
   | `GROQ_API_KEY` | console.groq.com → *API Keys* | écrit les scénarios (secours) |
   | `BUFFER_API_KEY` | publish.buffer.com/settings/api | publie et lit les statistiques |

   Aucune clé n'est écrite dans le code : il ne lit que ces variables.
2. **Préparer Buffer.** Compte gratuit sur buffer.com → connecte tes 3 canaux : TikTok, Instagram
   (compte professionnel ou créateur) et ta Page Facebook → crée la clé d'API.
3. **Regarder un essai.** Onglet *Actions* → « Agent vidéo » → ouvre la dernière exécution. Le
   résumé montre le journal (sujet choisi, durée, contrôle qualité, légende prévue). La vidéo est
   en bas de page, dans *Artifacts*. Pour en lancer un tout de suite : *Run workflow* → commande
   `tick`, case « forcer » cochée. Pour vérifier les clés : commande `doctor`.
4. **Lancer.** Quand l'essai te convient, que la clé Buffer est en place et que la page de vente
   de la formation est en ligne avec son lien dans ta bio : dans `config.yaml`, passe
   `publish.dry_run` à `false` (icône crayon sur GitHub). À partir de là, l'agent publie
   2 vidéos par jour sans toi.

GitHub Pages doit servir la branche `studio-media` (*Settings → Pages → Deploy from a branch* →
`studio-media`, dossier `/ (root)`) : c'est là que Buffer vient chercher chaque vidéo.

### Mode essai et publication réelle

| | `dry_run: true` (essai) | `dry_run: false` (réel) |
|---|---|---|
| Vidéo fabriquée et contrôlée | oui | oui |
| Envoi sur les réseaux | non | oui |
| Sujet marqué comme traité, vidéo comptée dans l'apprentissage | non | oui |
| Scénarios de réserve (quand aucun modèle ne répond) | tournent en boucle, jamais consommés | chacun ne sert qu'une fois |
| Si aucun réseau ne reçoit la vidéo | — | l'exécution passe en échec, rien n'est compté |

En publication réelle, si aucune clé de modèle ne répond et que les 3 scénarios de réserve ont
déjà servi, l'exécution échoue (GitHub t'envoie un e-mail) : c'est le signal qu'une clé manque.

---

## Régler l'agent (`config.yaml`)

| Réglage | Effet |
|---|---|
| `niche.description`, `niche.audience`, `niche.line` | De quoi parlent les vidéos, pour qui, et la ligne à ne pas quitter. Le scénariste et le stratège les lisent à chaque vidéo. |
| `niche.keywords` | Ce que la veille cherche chaque jour sur GitHub (les 5 premiers). |
| `research.require_any`, `research.exclude_any` | Un sujet n'est retenu que si son nom, sa description ou ses thèmes contiennent l'un des mots exigés, et aucun des mots refusés. |
| `offer.cta_comment`, `offer.cta_say`, `offer.cta_sub`, `offer.caption_end` | La fin de chaque vidéo : ce que la voix dit après « Commente MOT », la dernière phrase, la ligne écrite à l'écran, la fin de la légende. À changer le jour où la promo s'arrête. |
| `offer.name`, `offer.points`, `offer.price`, `offer.pitch_every` | Quand `name` et `points` sont remplis, 1 vidéo sur `pitch_every` présente directement la formation. |
| `brand.theme`, `brand.accent`, `brand.avatar` | 4 thèmes (papier, ocean, menthe, nuit) ; `accent` impose ta couleur ; `avatar` affiche une photo dans une bulle sur l'écran final. |
| `schedule.slots`, `videos_per_day` | Créneaux candidats (heure locale) ; l'agent en choisit 2 par jour. Si tu les changes, change aussi les lignes `cron` de `.github/workflows/agent.yml`. |
| `voice.order`, `voice.edge_voice`, `voice.rate` | Moteur, voix et débit. `voice.pronounce` corrige la prononciation d'un mot. |
| `audio.music_db`, `audio.voice_margin_db` | Niveau de la musique, et marge minimale de la voix sur le fond : si la musique ou les bruitages s'en approchent trop, l'agent les baisse seul ; sous 6 dB de marge, la vidéo n'est pas publiée. |
| `strategy.explore` | Part d'essais nouveaux (0,2 = 1 décision sur 5 environ sort des sentiers battus). |
| `publish.dry_run` | `true` : mode essai (voir plus haut). |

## Comment il décide de la vidéo suivante

1. À 24 h, 72 h et 7 jours, il relève vues, commentaires, partages et enregistrements de chaque vidéo.
2. Il note chaque vidéo par rapport à **ta** médiane (0 = vidéo moyenne, +1 = deux fois mieux).
3. Pour le format, l'accroche, la longueur et le créneau, il tire au sort en favorisant ce qui a
   les meilleures notes, avec une part d'essais (`python3 run.py plan` affiche ce qu'il a appris).
4. Le modèle choisit le sujet parmi la veille du jour en lisant un résumé de tes meilleures et de
   tes pires vidéos. 1 vidéo sur 5 refait une gagnante sous un autre angle : c'est la « suite »
   annoncée à ceux qui commentent.
5. Tout chiffre du scénario doit figurer dans les faits de la veille, sinon le scénario est refusé.

Ce mécanisme est testé sur un monde simulé (`tests/test_core.py`) : avec un format qui rapporte
3 fois plus de vues, il le choisit plus d'une fois sur deux après 80 vidéos. Sur ton compte,
compte 3 à 4 semaines avant que les choix deviennent significatifs.

## Commandes

```bash
python3 run.py tick            # un réveil normal (ce que lance le serveur)
python3 run.py tick --force    # fabrique une vidéo tout de suite
python3 run.py make --story examples/demo_storyboard.json --no-publish   # à partir d'un scénario écrit à la main
python3 run.py demo            # la vidéo d'exemple
python3 run.py plan            # plan du jour + ce que le stratège a appris
python3 run.py stats           # relève les statistiques maintenant
python3 run.py doctor --live   # vérifie outils et clés (1 appel d'essai par clé)
```

## Ce qu'il faut savoir avant de publier

- **Ne lance pas avant la formation.** Chaque vidéo dit « la formation complète est en promo,
  lien en bio ». Tant que la page de vente n'existe pas, garde `dry_run: true`.
- **TikTok.** Sans Buffer, une application TikTok non auditée ne publie qu'en privé. Avec Buffer,
  c'est public, mais sans son tendance (l'API ne le permet pas).
- **Étiquette « généré par IA ».** Activée par défaut (`publish.ai_label`) : la voix est synthétique.
- **Les réserves vieillissent.** Les 3 scénarios de `examples/evergreen/` citent des chiffres
  relevés le 11/11/2026 (nombre d'étoiles GitHub, licence de Remotion). Leurs sources sont dans
  chaque fichier (`links`, `_sources`). Relis-les de temps en temps, ou remplace-les par les tiens.
- **Conditions des services gratuits.** NVIDIA réserve son offre gratuite au test ; edge-tts est
  un service non officiel ; la voix Piper demande de créditer « SIWIS ». Détails dans `docs/STACK.md`.
- **Conditions de GitHub.** Elles réservent Actions au développement du logiciel du dépôt et
  n'autorisent pas Pages comme hébergement gratuit d'une activité commerciale. Un robot qui publie
  des vidéos pour vendre une formation sort de ce cadre : GitHub peut arrêter la tâche ou fermer
  le dépôt. La variante « serveur à toi » ci-dessous n'a pas ce risque.

## Dépannage

| Symptôme | Cause probable |
|---|---|
| « écriture par le LLM impossible » | Clé absente ou quota du jour atteint : l'agent prend un scénario de réserve. Vérifie avec la commande `doctor`. |
| « aucun réseau n'a reçu la vidéo » | Clé Buffer absente, canal déconnecté dans Buffer, ou vidéo refusée : le détail est dans le journal de l'exécution. |
| « pas d'adresse publique pour la vidéo » | GitHub Pages ne sert pas la branche `studio-media`. |
| Les réveils GitHub s'arrêtent | GitHub suspend les tâches planifiées d'un dépôt public resté 60 jours sans activité. L'agent enregistre sa mémoire dans le dépôt à chaque réveil, ce qui devrait compter comme activité (non vérifié sur la durée). Si cela arrive : onglet *Actions* → « Agent vidéo » → *Enable workflow*. |

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
run.py                     point d'entrée
config.yaml                tous les réglages
studio/                    scout (veille) · strategist (décision) · writer (scénario + fin imposée) · llm (modèles) · schema (contrôle)
                           voice · align · music · mix · timeline · render · qa · produce
                           publish/ (buffer, meta, tiktok) · stats · mediahost · state
engine/                    moteur de rendu : player.html / .css / .js + polices
examples/                  scénario d'exemple + 3 scénarios de réserve
tests/                     32 tests automatiques
.github/workflows/         la tâche planifiée GitHub
deploy/                    variante serveur (systemd)
docs/                      STACK.md
state/                     mémoire de l'agent (remplie au fil des réveils)
```
