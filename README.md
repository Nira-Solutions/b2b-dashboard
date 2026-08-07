# Teatower — B2B Morning Dashboard

Photo quotidienne de l'activité B2B facturée, générée depuis Odoo (`tea-tree`)
et publiée sur GitHub Pages.

**→ https://nira-solutions.github.io/b2b-dashboard/**

## Ce que la page montre

Les factures clients **postées la veille**, restreintes aux partenaires tagués
B2B, segmentées par canal :

| Canal | Tags `res.partner.category` |
|---|---|
| GMS | 88, 27 |
| Horeca | 84, 26 |
| Revendeurs | 85 |

Un partenaire sans aucun de ces tags n'est pas compté — c'est du B2C
(Shopify / POS). Priorité si multi-tag : GMS > Horeca > Revendeurs. Les adresses
de facturation enfants héritent des tags de leur `commercial_partner_id`, et les
tops sont regroupés au niveau société.

Montants en **HT** (`amount_untaxed`). Les avoirs (`out_refund`) sont comptés en
négatif.

Blocs : CA du jour et écart vs la moyenne des 5 derniers mêmes jours de semaine,
répartition par canal, tendance sur 6 points, cumul du mois, top clients, top
produits, détail des factures, pipeline devis (`sale.order` draft/sent) et
factures en brouillon.

## Génération

```bash
export ODOO_PWD='...'                 # jamais en clair dans le repo
python extract.py --out data.json     # Odoo -> data.json
python build.py --data data.json --deploy --deploy-dir . --archive-dir archive
```

`extract.py` prend la veille par défaut ; `--date 2026-08-06` pour rejouer un
jour précis.

## Automatisation

`.github/workflows/daily.yml` tourne tous les matins à **07h00 Europe/Brussels**
(deux crons UTC, un garde-fou laisse passer celui qui correspond à l'heure
locale), puis commit et push. Déclenchable à la main via *Actions →
B2B Morning Dashboard → Run workflow*.

Secret requis : **`ODOO_PWD`** (Settings → Secrets and variables → Actions).

## Attention — repo public

La page publiée contient les **noms de clients et leurs montants facturés**.
C'est un choix assumé ; passer le repo en privé coupe GitHub Pages sauf plan
GitHub Team.

Les archives datées s'accumulent dans `archive/`.
