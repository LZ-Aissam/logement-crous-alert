# Alerte Logement CROUS

Service d'alerte email sur les dispos de logement CROUS.
Site statique (Netlify) + Netlify Functions + scripts Python lancés par GitHub Actions.
Pas de build step, pas de framework : `public/` est servi tel quel.

## Commandes

```bash
pytest                                          # tests Python
npm test                                        # tests Netlify Functions
python -m http.server 8765 --directory public   # prévisualiser le site
```

## Structure

- `check_logement.py` — scraping + envoi des alertes (job GitHub Actions)
- `add_search.py`, `confirm_email.py`, `unsubscribe.py` — traitent les issues GitHub
- `search_criteria.py` — parsing des critères, **miroir Python de `netlify/functions/_criteria.js`**
- `netlify/functions/` — endpoints du formulaire public
- `public/` — 5 pages HTML statiques, Bootstrap 5.3.3 + Bootstrap Icons via CDN
- `searches.json` / `seen.json` — état persisté

## Règles projet

- **Parité critères** : toute modif de `search_criteria.py` ou `_criteria.js` doit être
  répercutée dans l'autre, avec le cas ajouté à `tests/fixtures/criteria_parity_cases.json`.
- **Pas de templating** : un changement de nav ou de footer se réplique à la main
  dans les 5 fichiers de `public/`.
- **Mentions légales pseudonymes** : jamais de nom réel ni d'adresse postale.
- Contact affiché : `logementcrousalert@gmail.com` (= `FROM_EMAIL`).
- Gabarit HTML : celui de `confirmer.html` (`<!doctype html>`, `lang="fr"`,
  même `<head>`, badges `.stamp` / `.stamp-teal`).
- Secrets uniquement en variables d'env. La site key Turnstile dans `index.html`
  est la vraie clé (`0x4AAAAAAEAvnluSg9sdeEtR`, widget "Logement Crous Alerte"
  dans le dashboard Cloudflare) — pas une clé de test. Si le domaine du site
  change, penser à ajouter le nouveau hostname aux domaines autorisés du
  widget côté Cloudflare, sinon Turnstile échoue avec l'erreur 110200.
- Specs et plans : `docs/superpowers/{specs,plans}/`.
