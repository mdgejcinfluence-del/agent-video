# La pile 100 % gratuite — quotas, sources, et ce que chaque gratuité coûte vraiment

Vérifié le 11 novembre 2026. « Vérifié ici » = je l'ai fait tourner dans mon bac à sable.
« D'après la doc » = lu, pas exécuté (il faut tes clés).

Besoin réel de l'agent : **2 vidéos par jour**, soit environ 20 à 30 appels de modèle, 10 à 14
synthèses vocales, 2 rendus de 2 à 4 minutes et 6 publications par jour. Tous les paliers
gratuits ci-dessous couvrent ce volume avec une large marge ; l'agent tient en plus ses propres
compteurs (`state/quota.json`) et s'arrête avant chaque limite.

## 1. Le cerveau (écrire le scénario, choisir le sujet)

L'agent appelle les modèles **directement** (API compatible OpenAI). Il n'utilise pas le montage
« Claude Code + proxy » de la vidéo YouTube : pour une chaîne fixe (sujet → scénario → contrôle),
un appel direct consomme 1 requête là où un agent Claude Code en consommerait des dizaines, et il
ne casse pas à chaque mise à jour de Claude Code. Même cerveau NVIDIA, sans l'intermédiaire.

| Fournisseur (ordre d'essai) | Palier gratuit | Carte bancaire | Statut | Source |
|---|---|---|---|---|
| **NVIDIA NIM** — `nvidia/nemotron-3-ultra-550b-a55b` | ~40 requêtes/min | non | Catalogue lu ici (84 modèles, celui-ci présent). Appel non testé (pas de clé). | agentdeals.dev/llm-api-pricing · `integrate.api.nvidia.com/v1/models` |
| Groq — `openai/gpt-oss-120b` | 30 req/min, 1 000 req/jour, 200 000 jetons/jour | non | D'après la doc | dev.to/aifree (10/10/2026) · agentdeals.dev |
| Google Gemini (AI Studio) | modèles Flash gratuits, débit limité | non | D'après la doc | dev.to/aifree · agentdeals.dev |
| OpenRouter (modèles `:free`) | 20 req/min, **50 req/jour** | non | D'après la doc | openrouter.ai/docs/api_reference/limits |

- Bascule automatique : si un fournisseur répond « quota » ou tombe, l'agent passe au suivant ;
  si un modèle est retiré du catalogue (c'est arrivé à Kimi K3 chez NVIDIA le 15/10/2026), il en
  choisit un autre dans la liste `prefer`.
- Si **aucun** modèle ne répond, l'agent publie une vidéo « de réserve » (3 scénarios écrits et
  vérifiés à la main dans `examples/evergreen/`). Il ne bascule jamais vers du payant.
- **Le prix caché de NVIDIA** : ses conditions d'essai n'autorisent que le test et l'évaluation,
  pas la production, et l'accès peut être coupé sans préavis (agentdeals.dev, vérifié le
  02/11/2026). Un agent qui publie tous les jours, c'est de la production. À toi de décider ;
  ajouter une clé Groq ou Gemini te protège d'une coupure.
- Services sans clé (Pollinations, LLM7) : testés ici. Ils répondent à une petite question, mais
  échouent sur le long message du scénario (limite de sortie, 1 réponse toutes les 45 s). Ils
  sont donc désactivés par défaut (`llm.keyless_fallback`).

## 2. La voix

| Moteur | Gratuit ? | Qualité | Statut | À savoir |
|---|---|---|---|---|
| **edge-tts** (voix neuronales de Microsoft Edge) — par défaut | oui, sans clé | naturelle ; donne l'instant exact de chaque mot | **Vérifié ici** (13 voix françaises ; `fr-FR-RemyMultilingualNeural`) | Service **non officiel** : c'est la « lecture à voix haute » d'Edge utilisée hors d'Edge. Microsoft peut la bloquer, et cet usage n'est pas couvert par une licence commerciale (freeapihub.com, 18/09/2026). |
| Gemini TTS (clé AI Studio) | palier gratuit limité en débit | naturelle | D'après la doc, **non testé** | API officielle. Pas d'horodatage par mot : sous-titres calés par estimation. |
| **Piper** `fr_FR-siwis-medium` — secours | oui, 100 % local, illimité | correcte mais plus « robot » | **Vérifié ici** (4 s pour une phrase) | Logiciel GPL-3.0 ; voix entraînée sur un jeu de données CC-BY 4.0 : il faut créditer « SIWIS » quelque part (bio ou page ressources). |

Je recommande de démarrer avec edge, en sachant ce que c'est ; si tu veux une pile sans zone
grise, mets `voice.order: ["gemini", "piper"]`.

## 3. L'image : motion design par le code

| Brique | Rôle | Statut |
|---|---|---|
| Moteur maison `engine/` (HTML + CSS + JavaScript) | scènes, cartes, sous-titres, mascotte, transitions ; chaque image est calculée à partir du temps, sans hasard | **Vérifié ici** |
| Chromium sans écran (Playwright, Apache-2.0) | photographie chaque image | **Vérifié ici** : 14 images/s sur 2 cœurs, 80 s pour une vidéo de 39 s |
| ffmpeg (LGPL/GPL) | assemble en MP4 H.264 1080×1920, 30 img/s | **Vérifié ici** |
| Polices Inter Tight, Instrument Serif, JetBrains Mono, Caveat | licence OFL (fournies dans `engine/fonts/` avec leurs licences) | — |

Pas de Remotion (gratuit seulement sous conditions), pas d'After Effects, pas de générateur
vidéo payant. La mascotte est un dessin original (ce n'est pas celle de Claude).

**Avatar** : l'agent peut afficher une photo (la tienne, par exemple) dans une
bulle sur l'écran final (`brand.avatar`). Un avatar qui
parle avec les lèvres synchronisées demande une carte graphique : je n'ai pas trouvé de moyen
gratuit, fiable et sans intervention de le faire tourner 2 fois par jour. Non inclus.

## 4. Le son

Musique et bruitages sont **synthétisés par l'agent** (numpy) : aucune licence, aucune
réclamation de droits d'auteur possible, une boucle différente par vidéo. Niveau final normalisé
à −14 LUFS (mesuré : −14,1). Musique et bruitages s'effacent quand la voix parle, et le « ding »
du mot-clé attend que le mot soit prononcé.

À chaque vidéo, l'agent mesure de combien la voix dépasse le fond entre 1 et 4 kHz, la zone qui
porte l'intelligibilité de la parole (23,8 dB sur l'exemple). Sous 14 dB, il baisse le fond ;
sous 6 dB, la vidéo n'est pas publiée. Ces seuils viennent d'un seul essai, sur la vidéo
d'exemple : la reconnaissance vocale restait stable entre 24 et 12 dB de marge et se dégradait
nettement à 0 dB.

Limite honnête : je ne peux pas écouter le résultat, je l'ai contrôlé par ces mesures et par une
reconnaissance vocale. Si la musique ne te plaît pas, dépose tes propres fichiers dans
`assets/music/` ou mets `audio.music: false`.

## 5. Le serveur et la mémoire

| Option | Coût | Carte | Statut | À savoir |
|---|---|---|---|---|
| **GitHub Actions** (dépôt public) — par défaut | 0 €, minutes illimitées | non | Fichier écrit, **non exécuté** | Réveils à heure fixe (retard possible de 5 à 30 min). **Les conditions de GitHub réservent Actions à la construction, au test et au déploiement du logiciel du dépôt** ; un robot de publication sort de ce cadre. C'est très répandu et la charge est minime (2 × 4 min par jour), mais ce n'est pas un usage autorisé : GitHub peut arrêter la tâche, désactiver le dépôt, voire suspendre le compte. |
| GitHub Pages (branche `studio-media`) | 0 € | non | Partie Git **vérifiée ici** sur un dépôt local ; service non testé | Héberge les vidéos que Buffer vient chercher. Dépôt public obligatoire en gratuit ; 1 Go par site, 100 Go de trafic par mois. **Les conditions de GitHub disent que Pages n'est pas autorisé comme hébergement gratuit pour faire tourner une activité commerciale** ; une page ressources qui mène à ta formation, plus des vidéos servies à Buffer, entre dans ce cas. |
| Serveur personnel (Oracle Cloud Always Free, vieux PC sous Linux, etc.) + Cloudinary pour les vidéos | 0 € | Oracle demande une carte pour vérifier l'identité (sans débit) | Fichiers `deploy/` écrits, **non exécutés** | La voie conforme aux conditions de chacun. Même code, réveil par `systemd`. |

Sources : docs.github.com/en/site-policy/github-terms/github-terms-for-additional-products-and-features (rubriques Actions et Pages) et docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits, lues le 11/11/2026.

La mémoire de l'agent (`state/*.json`) est enregistrée dans le dépôt après chaque réveil.

## 6. Publier et lire les statistiques

| Voie | Coût | Ce que ça permet | Statut |
|---|---|---|---|
| **Buffer** (offre gratuite) — par défaut | 0 €, sans carte | 3 canaux (TikTok + Instagram + Page Facebook), 1 clé d'API : publication **publique** et statistiques par vidéo. Limites : 150 requêtes / 15 min, 600 / jour, 1 000 par canal sur 30 jours (3 000 max), 10 publications en attente par canal. L'agent en consomme environ 25 par jour. | Requêtes écrites d'après developers.buffer.com et testées contre un faux serveur. **Jamais envoyées au vrai Buffer.** |
| API TikTok native | 0 € | Tant que ton application n'a pas passé l'audit de TikTok : publication **privée uniquement**, sur un compte lui-même privé. Sans audit, seul le mode « brouillon dans ta boîte TikTok » sert à quelque chose (tu touches « publier »). | D'après la doc, non testé |
| API Meta native (Facebook Reels, Instagram Reels) | 0 € | Publication sur ta Page et ton compte professionnel. L'application doit être en mode « Live », sinon les publications ne sont visibles que de ses administrateurs. | D'après la doc (v26.0), non testé |

Pourquoi Buffer en premier : c'est la seule voie gratuite que j'ai trouvée pour publier sur
TikTok **en public et sans intervention** dès aujourd'hui. L'audit TikTok prend plusieurs
semaines et est souvent refusé (sources : schedulenchill.com, postzen.dev, usecarly.com, 2026).

Ce qui reste hors de portée gratuitement : l'envoi automatique d'un message privé à chaque
personne qui commente. L'agent ne promet donc jamais un envoi. Chaque vidéo se termine par
« Commente MOT si tu veux la suite. La formation complète est en promo, lien en bio. » : le
commentaire sert à la portée de la vidéo, et le lien en bio mène à la formation.

## 7. Ce que je n'ai pas retenu

- **Multiplier les comptes gratuits** pour dépasser un quota : inutile à 2 vidéos par jour, et
  c'est le moyen le plus sûr de faire fermer les comptes.
- **ElevenLabs gratuit** : usage commercial interdit sur l'offre gratuite.
- **OpenRouter à 1 000 requêtes/jour** : demande d'acheter 10 crédits.
- **DeepSeek, Magpie** : payants.
- **Lecture de tes statistiques TikTok par la page publique** (`stats.source_tiktok: public`,
  avec yt-dlp) : possible et codé, mais non officiel et fragile ; désactivé par défaut.
