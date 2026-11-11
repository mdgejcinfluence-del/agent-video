# La pile gratuite — services, quotas, et ce que chaque gratuité coûte vraiment

Relevé du 11 novembre 2026. « Essayé ici » = exécuté pendant la mise au point. « D'après la documentation » = lu, pas exécuté
(il faut tes clés). Les paliers gratuits changent souvent : l'agent ne suppose rien, il lit les réponses des services.

Besoin réel : **2 vidéos par jour**, soit environ 6 à 10 appels de modèle, 14 synthèses vocales, 4 à 6 téléchargements de séquences,
2 rendus de 1 à 3 minutes et 6 publications.

## 1. Le cerveau : l'API Gemini de Google

| Tâche | Modèle choisi par l'agent | Appels par vidéo |
|---|---|---|
| Écrire le storyboard (et le corriger si un contrôle le refuse) | le Gemini **Flash** le plus récent du catalogue | 1 à 3 |
| Regarder les rushs (3 images par séquence candidate) | le Gemini **Flash-Lite** le plus récent | 1 |
| Proposer de nouveaux faits à vérifier | Flash-Lite | 2 par semaine |
| Rédiger le bilan | Flash | 1 tous les 3 jours |

- Clé : https://aistudio.google.com/apikey — un compte Google suffit, sans carte bancaire. **Crée la clé dans un projet sans facturation** :
  c'est ce qui garantit qu'aucun appel ne peut être facturé.
- Appel direct en REST (`generativelanguage.googleapis.com/v1beta`), essayé ici contre un faux serveur qui en reproduit la forme ;
  **jamais essayé avec une vraie clé** (aucune n'était en place).
- Les quotas gratuits ont baissé en 2026 et ne sont plus tous publiés. Des relevés indépendants (septembre 2026) donnent environ
  20 requêtes par jour sur les modèles Flash et 500 sur Flash-Lite. C'est pourquoi l'agent : lit le catalogue à chaque exécution,
  réserve Flash à l'écriture, passe au modèle suivant dès qu'un quota est atteint et s'en souvient jusqu'au lendemain,
  plafonne ses appels (`llm.max_par_jour`).
- La recherche Google intégrée (« grounding ») n'est plus gratuite sur les modèles récents : l'agent ne s'en sert pas.
  Il vérifie lui-même ses faits en rouvrant les pages officielles.
- Secours facultatif pour le texte : Groq (`GROQ_API_KEY`).

## 2. Les séquences filmées

| Banque | Accès | Limites annoncées | Licence |
|---|---|---|---|
| Pexels | API officielle `api.pexels.com/v1/videos/search`, clé gratuite immédiate | 200 requêtes/heure, 20 000/mois | usage gratuit, attribution non exigée (lue le 11/11/2026) |
| Pixabay | API officielle `pixabay.com/api/videos/`, clé gratuite | 100 requêtes/minute ; résultats à garder en mémoire 24 h | usage gratuit, attribution non exigée (lue le 11/11/2026) |

- L'agent fait 1 à 3 recherches par vidéo et garde chaque résultat 24 h, comme Pixabay le demande.
- La forme des réponses des deux API est essayée ici contre des réponses conformes à leur documentation ; **aucune recherche réelle
  n'a été faite** (pas de clé). Les téléchargements, eux, ont été essayés pour de vrai sur les 14 séquences de la bibliothèque de départ.
- Wikimedia Commons a été essayé puis écarté : résultats hors sujet, licences à partage obligatoire, contenus pour adultes.
- Les pages de licence de Pexels et de Pixabay refusent les robots : les deux faits « licence » sont lus à la main et valables 90 jours.

## 3. La voix, le son, le rendu

| Brique | Outil | Coût | Statut |
|---|---|---|---|
| Voix | edge-tts (voix neuronales de Microsoft, service en ligne non officiel, sans clé) ; secours local Piper | 0 | essayé ici et sur GitHub |
| Musique et bruitages | générés par l'agent (aucun morceau du commerce) | 0 | essayé ici |
| Rendu | page HTML rendue image par image par Chromium (Playwright), assemblée par ffmpeg | 0 | essayé ici : 16 images/s sur 2 cœurs |
| Polices | Montserrat (licence SIL Open Font) | 0 | dans le dépôt |

## 4. Le serveur et la publication

| Brique | Outil | Limite |
|---|---|---|
| Réveils | GitHub Actions (dépôt public : minutes gratuites) | un réveil peut être retardé ou sauté ; le suivant rattrape dans les 4 heures |
| Mémoire | fichiers `state/` enregistrés dans le dépôt | — |
| Hébergement des vidéos | GitHub Pages (branche `studio-media`) | 30 vidéos conservées |
| Publication et statistiques | Buffer (offre gratuite : 3 canaux) ou API officielles de Meta et de TikTok | TikTok en direct demande l'audit de ton application |

## Ligne éditoriale « prompts et commandes d'IA » (11 novembre 2026)

- **Essai des prompts** : Gemini, par la même clé gratuite que l'écriture (un appel au modèle Flash par prompt, deux appels au modèle Flash-Lite
  pour choisir l'extrait affiché). L'instruction est envoyée seule, sans consigne ajoutée ; la vidéo dit que la réponse vient de Gemini.
  Tester sur ChatGPT ou Claude demanderait leurs clés, qui sont payantes : non retenu.
- **Commandes et réglages** : vérifiés sur les pages officielles (centre d'aide d'OpenAI, documentation de ChatGPT et de Claude Code, centre d'aide de
  Claude), rouvertes chaque jour. L'agent ne peut pas cliquer dans une application : il ne montre que ce qu'une page officielle décrit.
- **Images** : au 11/11/2026, l'API Gemini ne crée pas d'image avec une clé gratuite (les modèles d'image sont facturés à l'image). La famille
  « Images et création graphique » reste donc en attente (`actif: false` dans `data/sujets.yaml`) : une vidéo qui promet « voici le résultat »
  sans montrer une image réellement obtenue serait une fausse démonstration.

