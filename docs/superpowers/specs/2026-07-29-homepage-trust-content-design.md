# Contenu de confiance sur la page d'accueil

## Contexte

La page d'accueil (`public/index.html`) est jugée trop "vide" et manque de
signaux qui rassurent et retiennent l'attention d'un·e étudiant·e pressé·e.
Aucune vraie statistique d'usage n'est exploitable côté site statique
(pas de `searches.json`/`seen.json` public, pas d'API) : le contenu ajouté
doit donc rester honnête (pas de faux chiffres, pas de faux témoignages) et
s'appuyer uniquement sur des faits déjà vrais et documentés dans
`mentions-legales.html`.

## Objectif

Ajouter deux blocs de contenu à `index.html` uniquement (nav/footer partagés
non touchés) pour :
1. rassurer immédiatement après l'accroche (bandeau de confiance) ;
2. humaniser et rassurer avant la conversion finale (section narrative avant
   la FAQ).

## Contenu

### 1. Bandeau de confiance

Remplace le bloc à 2 items existant (`index.html:199-216`, section
`<section class="py-4">` avec 2 `col-md-6`). Nouvel emplacement : juste
après le `<header>` hero, avant la section "Le constat" (actuellement
ligne 149).

4 items en grille responsive (`row g-4`, `col-6 col-md-3`), chacun avec
une icône Bootstrap Icons, un titre gras court, une sous-ligne :

| Icône | Titre | Sous-ligne |
|---|---|---|
| `bi-gift` | 100% gratuit | Aucune carte bancaire, aucun compte à créer |
| `bi-shield-check` | Email protégé | Jamais revendu ni partagé, conforme RGPD |
| `bi-clock-history` | Vérifié 24h/24 | Contrôle automatique toutes les 5 minutes |
| `bi-x-circle` | Désinscription en 1 clic | Disponible à tout moment, dans chaque email |

Ces 4 faits sont déjà vrais et documentés (RGPD/non-revente et
désinscription en 1 clic : `mentions-legales.html:63,67` ; gratuit/sans
compte : hero et FAQ actuels ; vérification 5 min : FAQ actuelle
`index.html` faq-2).

### 2. Section "Pourquoi ce site existe"

Nouvelle `<section>` insérée juste avant la section FAQ (avant la ligne
353 actuelle). Style cohérent avec les autres sections (carte ou bloc
`section-eyebrow` + `h2`, pas de nouvelle classe CSS).

Texte (validé avec l'utilisateur) :

> Ce site est né d'une frustration très simple : rafraîchir la page du
> CROUS à la main, en boucle, en espérant tomber sur le bon logement avant
> tout le monde. Alerte Logement CROUS automatise cette surveillance pour
> que tu n'aies plus à le faire. C'est un projet indépendant et non
> commercial, non affilié au CROUS : pas de publicité, pas de revente de
> données, juste un robot qui travaille pour toi.

Contraintes : pas de nom réel, pas d'adresse postale, cohérent avec la
règle "mentions légales pseudonymes" déjà en vigueur sur le projet.

## Portée

- Fichier modifié : `public/index.html` uniquement.
- Aucune nouvelle dépendance (Bootstrap Icons déjà chargé).
- Pas de modification de `_criteria.js` / `search_criteria.py` (hors sujet).
- Pas de nouvelle section dans les 4 autres pages HTML (nav/footer
  partagés non affectés par ce changement).

## Vérification

- `python -m http.server 8765 --directory public` puis vérification
  visuelle des deux nouveaux blocs (desktop + mobile, via redimensionnement
  navigateur).
- `pytest` et `npm test` doivent continuer à passer (aucun changement
  Python/JS attendu).
- Revalidation PageSpeed Insights optionnelle pour confirmer qu'aucune
  régression de score n'est introduite (nouvelles icônes seulement, pas de
  nouvelle requête réseau).
