# Teatower — B2B Dashboards

Deux vues de l'activité B2B facturée, générées depuis Odoo (`tea-tree`) et
publiées sur GitHub Pages.

| Vue | URL | Rythme |
|---|---|---|
| Morning Dashboard — la veille | **https://nira-solutions.github.io/b2b-dashboard/** | quotidien |
| Weekly Review — la semaine écoulée | **https://nira-solutions.github.io/b2b-dashboard/weekly/** | lundi |

## Périmètre commun

Factures clients **postées**, restreintes aux partenaires tagués B2B,
segmentées par canal :

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

## Morning Dashboard

CA du jour et écart vs la moyenne des 5 derniers mêmes jours de semaine,
répartition par canal, tendance sur 6 points, cumul du mois, top clients, top
produits, détail des factures, pipeline devis (`sale.order` draft/sent) et
factures en brouillon.

## Weekly Review

La semaine ISO écoulée (lundi → dimanche) : CA facturé par canal comparé à S-1,
à la moyenne des 4 semaines précédentes et à la même semaine N-1 ; **prise de
commandes** (`sale.order` confirmées) confrontée à la facturation pour lire
l'effet carnet, et sa ventilation par vendeur ; top clients avec écart à leur
propre moyenne hebdomadaire sur 12 mois ; top produits avec écart à S-1 ;
**mouvement de portefeuille** — nouveaux clients, réactivations, et les clients
dormants (≥ 60 jours sans facture) classés par CA 12 mois ; cumuls mois et
année ; pipeline et brouillons.

> La base Odoo ne remonte pas avant **avril 2025**. Un YTD-vs-YTD brut
> surestime donc mécaniquement la croissance : la page recale automatiquement
> les deux périodes sur le premier mois réellement alimenté et affiche le
> delta comparable.

## Génération

```bash
export ODOO_PWD='...'                 # jamais en clair dans le repo

# quotidien
python extract.py --out data.json
python build.py --data data.json --deploy --deploy-dir . --archive-dir archive

# hebdomadaire
python extract_weekly.py --out weekly/data.json
python build_weekly.py --data weekly/data.json --deploy --deploy-dir weekly \
  --archive-dir archive
```

`extract.py` prend la veille par défaut (`--date 2026-08-06` pour rejouer un
jour) ; `extract_weekly.py` prend la dernière semaine complète
(`--week 2026-08-03` pour rejouer une semaine).

Les briques de rendu partagées vivent dans `b2b_render.py` (formatage, badges,
tableaux) et `b2b_style.py` (CSS) : les deux pages restent visuellement
identiques.

## Automatisation

| Workflow | Quand |
|---|---|
| `.github/workflows/daily.yml` | tous les matins à **07h00 Europe/Brussels** |
| `.github/workflows/weekly.yml` | **lundi 07h30 Europe/Brussels** |

GitHub Actions ne connaît que l'UTC : chaque workflow pose deux crons et un
garde-fou ne laisse passer que celui qui vaut l'heure locale visée. Les deux
sont déclenchables à la main via *Actions → Run workflow*.

Secret requis : **`ODOO_PWD`** (Settings → Secrets and variables → Actions).

## Attention — repo public

Les pages publiées contiennent les **noms de clients et leurs montants
facturés**. C'est un choix assumé ; passer le repo en privé coupe GitHub Pages
sauf plan GitHub Team.

Les archives datées s'accumulent dans `archive/`.
