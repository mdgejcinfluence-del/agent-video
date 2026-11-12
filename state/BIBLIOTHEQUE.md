# Bibliothèque de prompts

2 fiche(s) : 1 validée(s), 0 testée(s), 1 à vérifier, 0 rejetée(s).

- **validé** : vérifiée, et montrée dans une vidéo qui a passé tous ses contrôles. C'est ce qui peut entrer dans l'e-book.
- **testé** : vérifiée aujourd'hui (essai réel sur Gemini pour un prompt ; page officielle relue pour une commande ou un réglage).
- **à vérifier** : écrite, pas encore vérifiée (pas de clé Gemini, ou page officielle non confirmée). Jamais publiée dans cet état.
- **rejeté** : l'essai a échoué ou la réponse était inutilisable.

| Identifiant | Titre | Catégorie | Outil | Type | Statut | Vérification | Date | Vidéos |
|---|---|---|---|---|---|---|---|---|
| P-0002 | Tes consignes permanentes pour ChatGPT | Commandes et fonctions méconnues | ChatGPT | reglage | validé | page officielle relue | 2026-11-11 | demo-p2_consignes |
| P-0001 | Cinq idées de business adaptées à ton budget | Business et entrepreneuriat | ChatGPT | prompt | à vérifier | non testé (aucune clé GEMINI_API_KEY) | — | demo-p1_business, 20261112-1458-business |

## P-0002 — Tes consignes permanentes pour ChatGPT

- **Catégorie** : Commandes et fonctions méconnues · **Outil** : ChatGPT · **Type** : reglage
- **Fonction recherchée** : Texte à coller une fois dans les instructions personnalisées : ChatGPT en tient compte dans toutes les discussions
- **Statut** : validé — page officielle relue (help.openai.com — ChatGPT Custom Instructions), le 2026-11-11
- **Vidéo(s)** : demo-p2_consignes (essai)

**Prompt complet**

```
Je m'appelle [prénom] et je vis à [ville]. Je suis [métier]. Réponds-moi toujours en français simple, avec des phrases courtes. Donne-moi des étapes numérotées et un exemple concret. Si ma demande n'est pas claire, pose-moi une question avant de répondre.
```

**Exemple d'utilisation** : [prénom] = Awa, [ville] = Cotonou, [métier] = vendeuse de tissus en ligne

**Résultat attendu** : ChatGPT applique ces consignes à toutes les discussions, sans que tu les répètes.

**Personnalisation** : Remplace [prénom], [ville] et [métier], puis ajoute tes préférences : le ton, la longueur des réponses, la langue.

## P-0001 — Cinq idées de business adaptées à ton budget

- **Catégorie** : Business et entrepreneuriat · **Outil** : ChatGPT · **Type** : prompt
- **Fonction recherchée** : Obtenir cinq activités possibles avec un petit capital : investissement, clients, risques, prix, premières étapes
- **Statut** : à vérifier — non testé (aucune clé GEMINI_API_KEY)
- **Vidéo(s)** : demo-p1_business (essai), 20261112-1458-business (essai)

**Prompt complet**

```
Agis comme un consultant spécialisé dans la création de petites entreprises en Afrique de l'Ouest. Je vis à [ville] et je dispose d'un capital de [montant]. Propose-moi 5 activités adaptées à mon budget et à mon environnement. Pour chacune, détaille les investissements nécessaires, les clients potentiels, les risques, les prix possibles et les premières étapes pour démarrer. Ne propose pas de revenus garantis.
```

**Exemple d'utilisation** : [ville] = Cotonou, [montant] = 50 000 FCFA

**Résultat attendu** : Une liste de cinq activités, chacune détaillée : investissement, clients, risques, prix possibles, premières étapes.

**Personnalisation** : Remplace [ville] et [montant]. Tu peux ajouter ce que tu sais faire, le temps dont tu disposes et ce que tu ne veux pas vendre.
