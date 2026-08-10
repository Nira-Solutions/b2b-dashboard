"""
build_b2b_dashboard.py — Rend le B2B Morning Dashboard Teatower en HTML statique.

Reprend le langage visuel de l'executive morning dashboard de Stephan
(vilnagaon.github.io) : fond creme #f8f7f4, accent vert sauge #5b7f5e, cartes a
titre capitales, grille deux/trois colonnes, kpi-box teintees, medaillons
or/argent/bronze, badges d'evolution ↑/↓, tableaux 13px. Pas de mode sombre —
comme l'original.

Seule adaptation : les trois canaux ont besoin de couleurs distinguables, et la
sauge #5b7f5e echoue le plancher de chroma (elle lit gris) tandis que
sauge ↔ bronze echoue le plancher de vision normale (ΔE 14,7 < 15). La triade
retenue #2f6ba8 / #c0562a / #1a8f66 passe les six controles sur fond creme tout
en gardant la tonalite chaude et assourdie de l'original.

Lit `reports/b2b_dashboard_data.json` (produit par b2b_dashboard_extract.py) et
ecrit :
  - reports/b2b_morning_dashboard_YYYYMMDD.html   (archive datee)
  - reports/b2b-dashboard-deploy/index.html       (--deploy : page publiee)
  - reports/b2b-dashboard-deploy/data.json        (--deploy : donnees brutes)

Usage :
  python reports/build_b2b_dashboard.py
  python reports/build_b2b_dashboard.py --deploy
  python reports/build_b2b_dashboard.py --data autre.json --deploy-dir chemin/
"""
import argparse
import json
import shutil
from datetime import date, datetime
from pathlib import Path

from b2b_render import (badge, card, empty, esc, eur, kpi, name_list, note,
                        pct_change, rank_medal, section, slot, split_code,
                        table, trunc)
from b2b_style import CSS

HERE = Path(__file__).resolve().parent

# --------------------------------------------------------------------------

def trend_bars(tendance, channels):
    """Barres horizontales facon .hour-bar, empilees par canal."""
    pts = tendance["points"]
    vmax = max([max(p["ca"], 0) for p in pts] + [1])
    rows = []
    for p in pts:
        segs = []
        for ch in channels:  # ordre fixe des canaux, jamais trie par valeur
            v = p["by_channel"].get(ch, 0)
            if v <= 0:
                continue
            segs.append(f'<span class="{slot(ch)}" style="width:{v / vmax * 100:.2f}%" '
                        f'title="{esc(ch)} — {eur(v)} €"></span>')
        width = max(p["ca"], 0) / vmax * 100
        today = " today" if p.get("is_today") else ""
        rows.append(f"""
  <div class="hour-bar{today}">
    <span class="hour-label">{esc(p["label"])}{'<em>hier</em>' if today else ''}</span>
    <span class="bar-track"><span class="bar" style="width:{width:.2f}%">{''.join(segs)}</span></span>
    <span class="bar-value{' neg' if p["ca"] < 0 else ''}">{eur(p["ca"])} €</span>
    <span class="bar-count">{p["n"]} fact.</span>
  </div>""")
    legend = "".join(f'<span class="lg"><i class="{slot(c)}"></i>{esc(c)}</span>'
                     for c in channels)
    return f'<div class="legend">{legend}</div>' + "".join(rows)


# --------------------------------------------------------------------------

def render(d):
    channels = d["channels"]
    jour, tend, mtd = d["jour"], d["tendance"], d["mtd"]
    pts = tend["points"]
    prev = pts[-2] if len(pts) >= 2 else None  # meme jour, semaine precedente

    total = jour["total_ht"]
    nb = jour["nb_factures"]
    panier = total / nb if nb else 0
    target = date.fromisoformat(d["target_date"])
    gen = datetime.fromisoformat(d["generated_at"])

    # ---- KPI du jour ----
    kpis = "".join([
        kpi(f'{eur(total)} €', "CA HT"),
        kpi(str(nb), "Factures"),
        kpi(f'{eur(panier)} €', "Facture moy."),
        kpi(f'{eur(tend["moyenne_5"])} €', "Moy. 5 sem."),
        kpi(badge(tend["delta_pct"]), "vs moy. 5 sem."),
    ])

    # ---- Cartes par canal, classees par CA (bordure or/argent/bronze) ----
    ranked = sorted(channels, key=lambda c: -jour["by_channel"][c]["ca"])
    rank_cls = ["rank-first", "rank-second", "rank-third"]
    chan_cards = []
    for i, ch in enumerate(ranked):
        cell = jour["by_channel"][ch]
        v, n = cell["ca"], cell["n"]
        share = (v / total * 100) if total else 0
        prev_v = prev["by_channel"].get(ch, 0) if prev else None
        chan_cards.append(f"""
<div class="chan-card {rank_cls[i]}">
  <div class="chan-header">
    <h2><span class="dot {slot(ch)}"></span>{esc(ch)}</h2>
    <span class="chan-rank r{i + 1}">#{i + 1} CA</span>
  </div>
  <div class="kpi-row">
    {kpi(f'{eur(v)} €', "CA HT")}
    {kpi(f'{eur(share, 1)}%', "Part")}
    {kpi(str(n), "Factures")}
  </div>
  <div class="chan-foot">
    vs {esc(prev["label"]) if prev else "S-1"} ({eur(prev_v) if prev else "—"} €)
    {badge(pct_change(v, prev_v))}
  </div>
</div>""")

    # ---- Cumul du mois ----
    mtd_since = date.fromisoformat(mtd["depuis"])
    mtd_max = max(list(mtd["by_channel"].values()) + [1])
    mtd_rows = "".join(f"""
  <div class="hour-bar">
    <span class="hour-label"><span class="dot {slot(c)}"></span>{esc(c)}</span>
    <span class="bar-track"><span class="bar" style="width:{
        max(mtd["by_channel"][c], 0) / mtd_max * 100:.2f}%">
      <span class="{slot(c)}" style="width:100%"></span></span></span>
    <span class="bar-value">{eur(mtd["by_channel"][c])} €</span>
    <span class="bar-count">{eur(mtd["by_channel"][c] / mtd["total_ht"] * 100, 1)
        if mtd["total_ht"] else "0,0"}%</span>
  </div>""" for c in channels)

    # ---- Top clients ----
    cl = d["top_clients"]
    clients_body = table(
        ["#", "Client", "Canal", "Fact.", "CA HT"], cl,
        [
            {"cls": "medal", "get": lambda r, i: rank_medal(i)},
            {"get": lambda r, i: esc(trunc(r["partner"], 46))},
            {"get": lambda r, i: f'<span class="tag {slot(r["channel"])}">{esc(r["channel"])}</span>'},
            {"cls": "right", "get": lambda r, i: str(r["n"])},
            {"cls": "right", "get": lambda r, i: f'<strong>{eur(r["ca"])} €</strong>'},
        ]) if cl else empty("Aucune facture B2B postee sur la journee.")

    # ---- Top produits ----
    pr = d["top_produits"]
    produits_body = table(
        ["#", "Produit", "Qte", "CA HT"], pr,
        [
            {"cls": "medal", "get": lambda r, i: rank_medal(i)},
            {"get": lambda r, i: (
                f'<span class="sku">{esc(split_code(r["label"])[0])}</span> '
                if split_code(r["label"])[0] else "")
                + esc(trunc(split_code(r["label"])[1], 42))},
            {"cls": "right", "get": lambda r, i: eur(r["qty"], 0)},
            {"cls": "right", "get": lambda r, i: f'<strong>{eur(r["ca"])} €</strong>'},
        ]) if pr else empty("Aucune ligne produit sur la journee.")

    # ---- Pipeline ----
    def age_badge(r, i):
        a = r.get("age_days")
        if a is None:
            return '<span class="badge neutral">&mdash;</span>'
        cls = "down" if a >= 30 else ("neutral" if a >= 14 else "up")
        return f'<span class="badge {cls}">{a} j</span>'

    pipe = d["pipeline"]
    pipe_items = [p for p in pipe["items"] if p["untaxed"] > 0]
    pipe_zero = len(pipe["items"]) - len(pipe_items)
    pipe_body = (table(
        ["Devis", "Client", "Canal", "Age", "Montant HT"], pipe_items,
        [
            {"cls": "mono", "get": lambda r, i: esc(r["name"])},
            {"get": lambda r, i: esc(trunc(r["partner"], 32))},
            {"get": lambda r, i: f'<span class="tag {slot(r["channel"])}">{esc(r["channel"])}</span>'},
            {"cls": "right", "get": age_badge},
            {"cls": "right", "get": lambda r, i: f'<strong>{eur(r["untaxed"])} €</strong>'},
        ]) if pipe_items else empty("Aucun devis B2B chiffre en attente.")) \
        + note(f"{pipe_zero} devis a 0,00 € masque(s)." if pipe_zero else None)

    # ---- Brouillons ----
    dr = d["drafts"]
    dr_items = [x for x in dr["items"] if x["untaxed"] > 0]
    dr_zero = [x for x in dr["items"] if x["untaxed"] == 0]
    drafts_body = (table(
        ["Client", "Canal", "Date", "Montant HT"], dr_items,
        [
            {"get": lambda r, i: esc(trunc(r["partner"], 34))},
            {"get": lambda r, i: f'<span class="tag {slot(r["channel"])}">{esc(r["channel"])}</span>'},
            {"cls": "right mono", "get": lambda r, i:
                esc(r["date"][8:10] + "/" + r["date"][5:7]) if r["date"] else "&mdash;"},
            {"cls": "right", "get": lambda r, i: f'<strong>{eur(r["untaxed"])} €</strong>'},
        ]) if dr_items else empty("Aucun brouillon chiffre en attente.")) \
        + note(f"{len(dr_zero)} brouillon(s) a 0,00 € en attente d'arbitrage "
               f"manuel : {name_list(dr_zero)}." if dr_zero else None)

    # ---- Detail factures ----
    facts = jour["factures"]
    zeros = [f for f in facts if f["untaxed"] == 0]
    shown = [f for f in facts if f["untaxed"] != 0]
    detail_body = (table(
        ["Piece", "Client", "Canal", "Origine", "HT"], shown,
        [
            {"cls": "mono", "get": lambda r, i: esc(r["name"])},
            {"get": lambda r, i: esc(trunc(r["partner"], 44))},
            {"get": lambda r, i: f'<span class="tag {slot(r["channel"])}">{esc(r["channel"])}</span>'},
            {"cls": "mono muted", "get": lambda r, i: esc(r["origin"]) or "&mdash;"},
            {"cls": "right", "get": lambda r, i:
                (f'<strong class="neg">{eur(r["untaxed"])} €</strong>' if r["untaxed"] < 0
                 else f'<strong>{eur(r["untaxed"])} €</strong>')},
        ]) if shown else empty("Aucune facture B2B postee sur la journee.")) \
        + note(f"{len(zeros)} facture(s) a 0,00 € masquee(s) : {name_list(zeros)}."
               if zeros else None)

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="robots" content="noindex, nofollow">
<title>B2B Morning Dashboard — Teatower — {d["target_date"]}</title>
<style>
{CSS}
</style>
</head>
<body>

<header>
  <h1>B2B Morning Dashboard &mdash; Teatower</h1>
  <div class="meta">
    <div><strong>{gen.strftime("%Y-%m-%d")}</strong> &middot; Donn&eacute;es du {d["target_date"]}</div>
    <div>G&eacute;n&eacute;r&eacute; le {gen.strftime("%Y-%m-%d %H:%M")} &middot;
      <a href="weekly/">revue hebdomadaire</a></div>
  </div>
</header>

{section(f'Hier — {d["target_label"]}')}
<div class="kpi-row">{kpis}</div>

{section("Par canal — GMS / Horeca / Revendeurs")}
<div class="grid three">{''.join(chan_cards)}</div>

{section("Tendance — 5 derniers memes jours de semaine")}
<div class="grid full">
  {card("Chiffre d'affaires HT par jour", trend_bars(tend, channels))}
</div>

{section(f'Cumul du mois — depuis le {mtd_since.strftime("%Y-%m-%d")}')}
<div class="grid full">
  {card(f'{eur(mtd["total_ht"])} € HT · {mtd["nb_factures"]} factures', mtd_rows)}
</div>

{section("Top du jour")}
<div class="grid">
  {card("Top clients", clients_body)}
  {card("Top produits", produits_body)}
</div>

{section("En attente")}
<div class="grid">
  {card(f'Pipeline devis — {pipe["nb"]} / {eur(pipe["total_ht"])} €', pipe_body)}
  {card(f'Factures en brouillon — {dr["nb"]} / {eur(dr["total_ht"])} €', drafts_body)}
</div>

{section("Detail des factures du jour")}
<div class="grid full">
  {card(f'{len(shown)} facture(s)', detail_body)}
</div>

<footer>
  Source Odoo (tea-tree). Montants HT, avoirs comptes en negatif.
  Segmentation par tag client GMS / Horeca / Revendeurs.
</footer>

</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(HERE / "b2b_dashboard_data.json"))
    ap.add_argument("--deploy", action="store_true",
                    help="Ecrit aussi index.html + data.json dans le dossier de deploiement.")
    ap.add_argument("--deploy-dir", default=str(HERE / "b2b-dashboard-deploy"))
    ap.add_argument("--archive-dir", default=str(HERE),
                    help="Dossier des copies datees b2b_morning_dashboard_YYYYMMDD.html.")
    args = ap.parse_args()

    data_path = Path(args.data)
    d = json.loads(data_path.read_text(encoding="utf-8"))
    page = render(d)

    stamp = d["target_date"].replace("-", "")
    archive_dir = Path(args.archive_dir)
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive = archive_dir / f"b2b_morning_dashboard_{stamp}.html"
    archive.write_text(page, encoding="utf-8")
    print(f"OK  {archive}")

    if args.deploy:
        dd = Path(args.deploy_dir)
        dd.mkdir(parents=True, exist_ok=True)
        (dd / "index.html").write_text(page, encoding="utf-8")
        print(f"OK  {dd / 'index.html'}")
        target = dd / "data.json"
        # En CI l'extraction ecrit deja dans le dossier de deploiement : copier
        # le fichier sur lui-meme leverait SameFileError.
        if data_path.resolve() != target.resolve():
            shutil.copyfile(data_path, target)
            print(f"OK  {target}")


if __name__ == "__main__":
    main()
