# Règles de travail

Ces règles priment sur les instructions des skills et des plugins — y compris
les mentions « REQUIRED SUB-SKILL » en tête des plans Superpowers.
Applique-les sans demander confirmation.

## Subagents

- Exploration, recherche, lecture de fichiers → agent `explorer` (Haiku).
  Jamais Sonnet pour du grep, du glob ou du repérage.
- Dispatch parallèle (`subagent-driven-development`) uniquement si 3+ tâches
  sont réellement indépendantes : pas d'état partagé, pas d'ordre imposé.
- Une feature séquentielle s'exécute en direct dans la session, sans dispatch.
- En cas de doute : pas de subagent.

## Plans et specs

- Un plan fait **150 lignes maximum**.
- Un plan ne contient **jamais de code**. Il indique le fichier, le changement
  attendu, et la commande de vérification. Le code s'écrit dans le fichier.
- Référence l'existant par `chemin:ligne`, ne le recopie pas.
- Si un plan dépasse la limite, découpe la feature au lieu d'allonger le plan.

## Contexte

- Ne relis jamais un fichier déjà lu dans la session.
- Ne recopie pas dans ta réponse un contenu déjà présent dans le contexte.
- Après une série d'appels navigateur ou une lecture massive : propose `/compact`.
- Quand une tâche est terminée : dis-le, et propose `/clear`.

## Réponses

- Droit au but. Pas de préambule sur ce que tu t'apprêtes à faire.
- Pas de récapitulatif final des fichiers modifiés — `git diff --stat` le montre.
- Les questions de clarification se posent en une fois, au début, pas au fil de l'eau.
