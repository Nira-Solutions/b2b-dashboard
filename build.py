"""
build_b2b_dashboard.py — Rend le B2B Morning Dashboard Teatower en HTML statique.

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
import html
import json
import shutil
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Palette categorielle (slots 1-3 de la palette de reference dataviz, validee
# all-pairs en clair et en sombre). Ordre fixe : GMS, Horeca, Revendeurs.
CHANNEL_COLORS = {
    "GMS": ("--series-1", "#2a78d6", "#3987e5"),
    "Horeca": ("--series-2", "#eb6834", "#d95926"),
    "Revendeurs": ("--series-3", "#1baf7a", "#199e70"),
}


def eur(v, decimals=0):
    """3 644.53 -> '3 645' (espace insecable fine comme separateur de milliers)."""
    s = f"{v:,.{decimals}f}".replace(",", " ").replace(".", ",")
    return s


def esc(s):
    return html.escape(str(s if s is not None else ""))


def chan_class(c):
    return {"GMS": "s1", "Horeca": "s2", "Revendeurs": "s3"}.get(c, "s0")


# --------------------------------------------------------------------------
# Composants
# --------------------------------------------------------------------------

def trend_chart(tendance, channels):
    """Barres empilees par canal, 6 points, avec libelles directs et tooltips."""
    pts = tendance["points"]
    totals = [max(p["ca"], 0) for p in pts]
    vmax = max(totals) or 1
    n = len(pts)

    W, H = 680, 200
    PAD_L, PAD_R, PAD_T, PAD_B = 8, 8, 26, 34
    plot_w = W - PAD_L - PAD_R
    plot_h = H - PAD_T - PAD_B
    slot = plot_w / n
    bw = min(56, slot * 0.56)

    bars = []
    for i, p in enumerate(pts):
        cx = PAD_L + slot * i + slot / 2
        x = cx - bw / 2
        total = p["ca"]
        y_cursor = PAD_T + plot_h
        is_today = p.get("is_today")

        if total <= 0:
            # Journee vide ou avoir net : trait de base explicite, pas un blanc muet
            bars.append(
                f'<g class="bar{" today" if is_today else ""}">'
                f'<title>{esc(p["label"])} — {eur(total)} € HT · {p["n"]} facture(s)</title>'
                f'<rect class="empty" x="{x:.1f}" y="{PAD_T + plot_h - 3:.1f}" '
                f'width="{bw:.1f}" height="3" rx="1.5"></rect>'
                f'<rect class="hit" x="{cx - slot/2:.1f}" y="{PAD_T}" '
                f'width="{slot:.1f}" height="{plot_h}"></rect></g>'
            )
        else:
            segs = []
            # Empilement dans l'ordre fixe des canaux (jamais reordonne par rang)
            for ch in channels:
                v = p["by_channel"].get(ch, 0)
                if v <= 0:
                    continue
                h = v / vmax * plot_h
                y = y_cursor - h
                # 2px de respiration entre segments empiles
                segs.append(
                    f'<rect class="seg {chan_class(ch)}" x="{x:.1f}" y="{y:.1f}" '
                    f'width="{bw:.1f}" height="{max(h - 2, 1):.1f}" rx="3">'
                    f'<title>{esc(p["label"])} · {esc(ch)} — {eur(v)} € HT</title></rect>'
                )
                y_cursor = y
            bars.append(
                f'<g class="bar{" today" if is_today else ""}">'
                + "".join(segs)
                + f'<rect class="hit" x="{cx - slot/2:.1f}" y="{PAD_T}" '
                  f'width="{slot:.1f}" height="{plot_h}">'
                  f'<title>{esc(p["label"])} — {eur(total)} € HT · {p["n"]} facture(s)</title>'
                  f'</rect></g>'
            )

        # Libelle direct de la valeur au-dessus de chaque barre
        y_val = PAD_T + plot_h - (max(total, 0) / vmax * plot_h) - 7
        bars.append(
            f'<text class="vlabel{" today" if is_today else ""}" x="{cx:.1f}" '
            f'y="{max(y_val, 12):.1f}">{eur(total)}</text>'
        )
        bars.append(
            f'<text class="xlabel{" today" if is_today else ""}" x="{cx:.1f}" '
            f'y="{H - 16:.1f}">{esc(p["label"][:5])}</text>'
        )
        if is_today:
            bars.append(
                f'<text class="xsub" x="{cx:.1f}" y="{H - 4:.1f}">hier</text>'
            )

    legend = "".join(
        f'<span class="lg"><i class="{chan_class(c)}"></i>{esc(c)}</span>'
        for c in channels
    )

    return f"""
<section class="card">
  <div class="card-head">
    <h2>Tendance — 5 derniers memes jours de semaine</h2>
    <div class="legend">{legend}</div>
  </div>
  <div class="chart-scroll">
    <svg class="chart" viewBox="0 0 {W} {H}" role="img"
         aria-label="Chiffre d'affaires B2B HT par jour, empile par canal">
      <line class="baseline" x1="{PAD_L}" y1="{PAD_T + plot_h}"
            x2="{W - PAD_R}" y2="{PAD_T + plot_h}"></line>
      {''.join(bars)}
    </svg>
  </div>
</section>"""


def table(title, cols, rows, empty="Rien a afficher.", note=None):
    if not rows:
        return f"""
<section class="card">
  <div class="card-head"><h2>{esc(title)}</h2></div>
  <p class="empty-msg">{esc(empty)}</p>
</section>"""
    head = "".join(
        f'<th class="{c.get("cls","")}">{esc(c["label"])}</th>' for c in cols
    )
    body = []
    for r in rows:
        tds = []
        for c in cols:
            tds.append(f'<td class="{c.get("cls","")}">{c["get"](r)}</td>')
        body.append("<tr>" + "".join(tds) + "</tr>")
    note_html = f'<p class="note">{esc(note)}</p>' if note else ""
    return f"""
<section class="card">
  <div class="card-head"><h2>{esc(title)}</h2></div>
  <div class="table-scroll">
    <table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>
  </div>
  {note_html}
</section>"""


def chip(ch):
    return f'<span class="chip {chan_class(ch)}">{esc(ch)}</span>'


# --------------------------------------------------------------------------
# Page
# --------------------------------------------------------------------------

def render(d):
    channels = d["channels"]
    jour = d["jour"]
    tend = d["tendance"]
    delta = tend["delta_pct"]

    if delta is None:
        delta_html = '<span class="delta flat">pas de base de comparaison</span>'
    elif delta >= 0:
        delta_html = (f'<span class="delta up">&#9650; +{eur(delta,1)} %</span>'
                      f'<span class="delta-ctx">vs moyenne {eur(tend["moyenne_5"])} €</span>')
    else:
        delta_html = (f'<span class="delta down">&#9660; {eur(delta,1)} %</span>'
                      f'<span class="delta-ctx">vs moyenne {eur(tend["moyenne_5"])} €</span>')

    tiles = []
    total = jour["total_ht"] or 1
    for c in channels:
        cell = jour["by_channel"][c]
        v, n = cell["ca"], cell["n"]
        share = (v / total * 100) if jour["total_ht"] else 0
        tiles.append(f"""
    <div class="tile {chan_class(c)}">
      <div class="tile-lab"><i></i>{esc(c)}</div>
      <div class="tile-val">{eur(v)} €</div>
      <div class="tile-sub">{eur(share,0)} % du jour · {n} fact.</div>
    </div>""")

    mtd = d["mtd"]
    mtd_since = date.fromisoformat(mtd["depuis"])
    mtd_tiles = "".join(
        f'<div class="mini {chan_class(c)}"><i></i><span class="mini-lab">{esc(c)}</span>'
        f'<span class="mini-val">{eur(mtd["by_channel"][c])} €</span></div>'
        for c in channels
    )

    clients_tbl = table(
        "Top clients du jour",
        [
            {"label": "Client", "get": lambda r: esc(r["partner"])},
            {"label": "Canal", "get": lambda r: chip(r["channel"])},
            {"label": "Fact.", "cls": "num", "get": lambda r: str(r["n"])},
            {"label": "CA HT", "cls": "num strong", "get": lambda r: eur(r["ca"], 2) + " €"},
        ],
        d["top_clients"],
        empty="Aucune facture B2B postee sur la journee.",
    )

    prod_tbl = table(
        "Top produits du jour",
        [
            {"label": "Produit", "get": lambda r: esc(r["label"])},
            {"label": "Qte", "cls": "num", "get": lambda r: eur(r["qty"], 0)},
            {"label": "CA HT", "cls": "num strong", "get": lambda r: eur(r["ca"], 2) + " €"},
        ],
        d["top_produits"],
        empty="Aucune ligne produit sur la journee.",
    )

    def age_cell(r):
        a = r.get("age_days")
        if a is None:
            return "—"
        cls = "old" if a >= 30 else ("mid" if a >= 14 else "fresh")
        return f'<span class="age {cls}">{a} j</span>'

    pipe = d["pipeline"]
    pipe_tbl = table(
        f'Pipeline devis — {pipe["nb"]} devis / {eur(pipe["total_ht"])} € HT',
        [
            {"label": "Devis", "get": lambda r: esc(r["name"])},
            {"label": "Client", "get": lambda r: esc(r["partner"])},
            {"label": "Canal", "get": lambda r: chip(r["channel"])},
            {"label": "Age", "cls": "num", "get": age_cell},
            {"label": "Montant HT", "cls": "num strong", "get": lambda r: eur(r["untaxed"], 2) + " €"},
        ],
        pipe["items"],
        empty="Aucun devis B2B ouvert.",
        note="Devis en brouillon ou envoyes, non confirmes. Age = depuis la date du devis.",
    )

    dr = d["drafts"]
    draft_tbl = table(
        f'Factures en brouillon — {dr["nb"]} / {eur(dr["total_ht"])} € HT',
        [
            {"label": "Piece", "get": lambda r: esc(r["name"])},
            {"label": "Client", "get": lambda r: esc(r["partner"])},
            {"label": "Canal", "get": lambda r: chip(r["channel"])},
            {"label": "Montant HT", "cls": "num strong", "get": lambda r: eur(r["untaxed"], 2) + " €"},
        ],
        dr["items"],
        empty="Aucune facture B2B en brouillon.",
        note="A poster ou a arbitrer. Les brouillons a 0,00 € attendent une decision manuelle.",
    )

    fact_tbl = table(
        f'Detail des {jour["nb_factures"]} factures du jour',
        [
            {"label": "Piece", "get": lambda r: esc(r["name"])},
            {"label": "Client", "get": lambda r: esc(r["partner"])},
            {"label": "Canal", "get": lambda r: chip(r["channel"])},
            {"label": "Origine", "get": lambda r: esc(r["origin"]) or "—"},
            {"label": "HT", "cls": "num strong",
             "get": lambda r: ('<span class="refund">' if r["is_refund"] else "<span>")
                              + eur(r["untaxed"], 2) + " €</span>"},
        ],
        jour["factures"],
        empty="Aucune facture B2B postee sur la journee.",
    )

    gen = datetime.fromisoformat(d["generated_at"])

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="robots" content="noindex, nofollow">
<title>B2B Morning Dashboard — Teatower</title>
<style>
  :root {{
    color-scheme: light dark;
    --bg: #f5f7f6; --card: #ffffff; --line: #e3e8e5;
    --ink: #16211c; --ink-2: #55635c; --ink-3: #869089;
    --brand: #2d6a4f; --brand-soft: #eef6f1;
    --up: #1b7f4b; --down: #c0392b;
    --s1: #2a78d6; --s2: #eb6834; --s3: #1baf7a;
    --shadow: 0 1px 2px rgba(16,32,24,.06), 0 4px 14px rgba(16,32,24,.05);
  }}
  @media (prefers-color-scheme: dark) {{
    :root:where(:not([data-theme="light"])) {{
      --bg: #12140f; --card: #1a1c18; --line: #2c302a;
      --ink: #f2f4f0; --ink-2: #b6bdb4; --ink-3: #7d857b;
      --brand: #6fbb92; --brand-soft: #1f2b24;
      --up: #57c98a; --down: #e8756a;
      --s1: #3987e5; --s2: #d95926; --s3: #199e70;
      --shadow: 0 1px 2px rgba(0,0,0,.4), 0 4px 14px rgba(0,0,0,.3);
    }}
  }}
  :root[data-theme="dark"] {{
    color-scheme: dark;
    --bg: #12140f; --card: #1a1c18; --line: #2c302a;
    --ink: #f2f4f0; --ink-2: #b6bdb4; --ink-3: #7d857b;
    --brand: #6fbb92; --brand-soft: #1f2b24;
    --up: #57c98a; --down: #e8756a;
    --s1: #3987e5; --s2: #d95926; --s3: #199e70;
    --shadow: 0 1px 2px rgba(0,0,0,.4), 0 4px 14px rgba(0,0,0,.3);
  }}

  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 1rem .9rem 3rem;
    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
    background: var(--bg); color: var(--ink);
    max-width: 860px; margin-inline: auto;
    -webkit-text-size-adjust: 100%;
  }}
  header {{ margin-bottom: 1.1rem; }}
  .kicker {{ font-size: .72rem; letter-spacing: .09em; text-transform: uppercase;
             color: var(--brand); font-weight: 700; }}
  h1 {{ font-size: 1.35rem; margin: .15rem 0 .1rem; letter-spacing: -.01em; }}
  .sub {{ color: var(--ink-2); font-size: .86rem; }}

  .hero {{
    background: var(--card); border: 1px solid var(--line); border-radius: 14px;
    padding: 1.1rem 1.15rem; box-shadow: var(--shadow); margin-bottom: .8rem;
  }}
  .hero-lab {{ font-size: .78rem; color: var(--ink-2); text-transform: uppercase;
               letter-spacing: .06em; font-weight: 600; }}
  .hero-val {{ font-size: 2.6rem; font-weight: 700; line-height: 1.05;
               letter-spacing: -.025em; margin: .2rem 0 .35rem;
               font-variant-numeric: tabular-nums; }}
  .hero-val small {{ font-size: 1.1rem; font-weight: 600; color: var(--ink-2); }}
  .delta {{ font-size: .85rem; font-weight: 700; margin-right: .5rem; }}
  .delta.up {{ color: var(--up); }} .delta.down {{ color: var(--down); }}
  .delta.flat {{ color: var(--ink-3); font-weight: 600; }}
  .delta-ctx {{ font-size: .8rem; color: var(--ink-2); }}
  .hero-n {{ font-size: .82rem; color: var(--ink-2); margin-top: .45rem; }}

  .tiles {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: .6rem;
            margin-bottom: .8rem; }}
  @media (max-width: 520px) {{ .tiles {{ grid-template-columns: 1fr; }} }}
  .tile {{ background: var(--card); border: 1px solid var(--line); border-radius: 12px;
           padding: .75rem .85rem; box-shadow: var(--shadow); }}
  .tile-lab {{ display: flex; align-items: center; gap: .4rem; font-size: .78rem;
               color: var(--ink-2); font-weight: 600; }}
  .tile-lab i {{ width: 10px; height: 10px; border-radius: 3px; flex: none; }}
  .tile.s1 .tile-lab i {{ background: var(--s1); }}
  .tile.s2 .tile-lab i {{ background: var(--s2); }}
  .tile.s3 .tile-lab i {{ background: var(--s3); }}
  .tile-val {{ font-size: 1.35rem; font-weight: 700; margin: .25rem 0 .1rem;
               font-variant-numeric: tabular-nums; letter-spacing: -.015em; }}
  .tile-sub {{ font-size: .75rem; color: var(--ink-3); }}

  .card {{ background: var(--card); border: 1px solid var(--line); border-radius: 14px;
           box-shadow: var(--shadow); margin-bottom: .8rem; overflow: hidden; }}
  .card-head {{ display: flex; justify-content: space-between; align-items: baseline;
                gap: .6rem; flex-wrap: wrap; padding: .8rem .95rem .55rem; }}
  .card-head h2 {{ font-size: .95rem; margin: 0; letter-spacing: -.005em; }}
  .legend {{ display: flex; gap: .7rem; flex-wrap: wrap; }}
  .lg {{ display: inline-flex; align-items: center; gap: .3rem;
         font-size: .74rem; color: var(--ink-2); font-weight: 600; }}
  .lg i {{ width: 10px; height: 10px; border-radius: 3px; }}
  .lg i.s1 {{ background: var(--s1); }} .lg i.s2 {{ background: var(--s2); }}
  .lg i.s3 {{ background: var(--s3); }}

  .chart-scroll {{ overflow-x: auto; padding: 0 .5rem .5rem; }}
  .chart {{ width: 100%; min-width: 460px; height: auto; display: block; }}
  .chart .baseline {{ stroke: var(--line); stroke-width: 1; }}
  .chart .seg.s1 {{ fill: var(--s1); }} .chart .seg.s2 {{ fill: var(--s2); }}
  .chart .seg.s3 {{ fill: var(--s3); }}
  .chart .empty {{ fill: var(--ink-3); opacity: .45; }}
  .chart .hit {{ fill: transparent; }}
  .chart .bar:hover .seg {{ opacity: .78; }}
  .chart .vlabel {{ font-size: 11px; font-weight: 600; fill: var(--ink-2);
                    text-anchor: middle; font-variant-numeric: tabular-nums; }}
  .chart .vlabel.today {{ fill: var(--ink); font-weight: 700; }}
  .chart .xlabel {{ font-size: 10.5px; fill: var(--ink-3); text-anchor: middle; }}
  .chart .xlabel.today {{ fill: var(--ink); font-weight: 700; }}
  .chart .xsub {{ font-size: 9px; fill: var(--brand); text-anchor: middle;
                  font-weight: 700; text-transform: uppercase; letter-spacing: .05em; }}

  .mtd {{ display: flex; gap: .5rem; flex-wrap: wrap; padding: 0 .95rem .9rem; }}
  .mini {{ display: inline-flex; align-items: center; gap: .35rem;
           background: var(--bg); border: 1px solid var(--line); border-radius: 999px;
           padding: .3rem .7rem; font-size: .78rem; }}
  .mini i {{ width: 9px; height: 9px; border-radius: 2px; }}
  .mini.s1 i {{ background: var(--s1); }} .mini.s2 i {{ background: var(--s2); }}
  .mini.s3 i {{ background: var(--s3); }}
  .mini-lab {{ color: var(--ink-2); }}
  .mini-val {{ font-weight: 700; font-variant-numeric: tabular-nums; }}

  .table-scroll {{ overflow-x: auto; }}
  table {{ width: 100%; border-collapse: collapse; font-size: .84rem; }}
  th {{ text-align: left; font-size: .7rem; text-transform: uppercase;
        letter-spacing: .05em; color: var(--ink-3); font-weight: 700;
        padding: .35rem .95rem .45rem; border-bottom: 1px solid var(--line);
        white-space: nowrap; }}
  td {{ padding: .5rem .95rem; border-bottom: 1px solid var(--line);
        vertical-align: middle; }}
  tr:last-child td {{ border-bottom: none; }}
  td.num, th.num {{ text-align: right; font-variant-numeric: tabular-nums;
                    white-space: nowrap; }}
  td.strong {{ font-weight: 700; }}
  .refund {{ color: var(--down); }}
  .chip {{ display: inline-block; padding: 1px 7px; border-radius: 5px;
           font-size: .68rem; font-weight: 700; color: #fff; white-space: nowrap; }}
  .chip.s1 {{ background: var(--s1); }} .chip.s2 {{ background: var(--s2); }}
  .chip.s3 {{ background: var(--s3); }}
  .age {{ font-weight: 700; font-size: .78rem; }}
  .age.fresh {{ color: var(--up); }}
  .age.mid {{ color: var(--ink-2); }}
  .age.old {{ color: var(--down); }}
  .note {{ font-size: .74rem; color: var(--ink-3); padding: .55rem .95rem .75rem;
           margin: 0; }}
  .empty-msg {{ font-size: .84rem; color: var(--ink-3); padding: 0 .95rem 1rem;
                margin: 0; }}
  footer {{ margin-top: 1.4rem; font-size: .74rem; color: var(--ink-3);
            text-align: center; line-height: 1.6; }}
</style>
</head>
<body>

<header>
  <div class="kicker">Teatower &middot; B2B Morning Dashboard</div>
  <h1>{esc(d["target_label"].capitalize())}</h1>
  <div class="sub">Factures B2B postees — GMS, Horeca, Revendeurs</div>
</header>

<div class="hero">
  <div class="hero-lab">Chiffre d'affaires du jour</div>
  <div class="hero-val">{eur(jour["total_ht"], 2)} <small>€ HT</small></div>
  <div>{delta_html}</div>
  <div class="hero-n">{jour["nb_factures"]} facture(s) B2B postee(s)</div>
</div>

<div class="tiles">{''.join(tiles)}</div>

{trend_chart(tend, channels)}

<section class="card">
  <div class="card-head">
    <h2>Mois en cours — depuis le {mtd_since.day:02d}/{mtd_since.month:02d}</h2>
    <div class="lg" style="font-weight:700;color:var(--ink)">
      {eur(mtd["total_ht"], 2)} € HT · {mtd["nb_factures"]} fact.
    </div>
  </div>
  <div class="mtd">{mtd_tiles}</div>
</section>

{clients_tbl}
{prod_tbl}
{fact_tbl}
{pipe_tbl}
{draft_tbl}

<footer>
  Genere le {gen.day:02d}/{gen.month:02d}/{gen.year} a {gen.hour:02d}h{gen.minute:02d}
  depuis Odoo (tea-tree).<br>
  Montants HT. Avoirs comptes en negatif. Segmentation par tag client
  GMS / Horeca / Revendeurs.
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
        shutil.copyfile(data_path, dd / "data.json")
        print(f"OK  {dd / 'index.html'}")
        print(f"OK  {dd / 'data.json'}")


if __name__ == "__main__":
    main()
