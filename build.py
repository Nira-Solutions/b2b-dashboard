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
import re
import shutil
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Palette categorielle : slots 1-3 de la palette de reference dataviz, validee
# all-pairs en clair et en sombre. Ordre fixe GMS > Horeca > Revendeurs, jamais
# reordonne par rang — la couleur suit le canal, pas sa place au classement.
CHANNEL_SLOT = {"GMS": "s1", "Horeca": "s2", "Revendeurs": "s3"}

# Code produit en tete de libelle Odoo : "[GI0735] Peche de Vigne - BIO glacee"
RE_CODE = re.compile(r"^\[([^\]]+)\]\s*(.*)$")


def eur(v, decimals=0):
    """3644.53 -> '3 644,53' — espace fin en milliers, virgule decimale."""
    return f"{v:,.{decimals}f}".replace(",", " ").replace(".", ",")


def esc(s):
    return html.escape(str(s if s is not None else ""))


def chan_class(c):
    return CHANNEL_SLOT.get(c, "s0")


def chip(ch):
    return f'<span class="chip {chan_class(ch)}">{esc(ch)}</span>'


def split_code(label):
    """'[GI0735] Peche de Vigne' -> ('GI0735', 'Peche de Vigne')."""
    m = RE_CODE.match(label or "")
    return (m.group(1), m.group(2)) if m else ("", label or "")


def name_cell(txt, extra=""):
    """Libelle long : tronque proprement en CSS, texte complet en infobulle."""
    return (f'<span class="nm" title="{esc(txt)}">{esc(txt)}</span>'
            + (f'<span class="nm-sub">{extra}</span>' if extra else ""))


def bar(value, vmax, slot="neutral"):
    """Barre de poids en ligne — magnitude pure, ancree a gauche."""
    if vmax <= 0 or value <= 0:
        return '<span class="wbar"></span>'
    pct = max(value / vmax * 100, 2)
    return f'<span class="wbar {slot}"><i style="width:{pct:.1f}%"></i></span>'


# --------------------------------------------------------------------------
# Composants
# --------------------------------------------------------------------------

def trend_chart(tendance, channels):
    """Barres empilees par canal, 6 points, libelles directs + infobulles."""
    pts = tendance["points"]
    vmax = max([max(p["ca"], 0) for p in pts]) or 1
    n = len(pts)

    W, H = 680, 208
    PAD_L, PAD_R, PAD_T, PAD_B = 10, 10, 28, 36
    plot_w, plot_h = W - PAD_L - PAD_R, H - PAD_T - PAD_B
    slot = plot_w / n
    bw = min(52, slot * 0.5)
    base_y = PAD_T + plot_h

    out = []
    for i, p in enumerate(pts):
        cx = PAD_L + slot * i + slot / 2
        x = cx - bw / 2
        total = p["ca"]
        today = p.get("is_today")
        tip = f'{p["label"]} — {eur(total)} € HT · {p["n"]} facture(s)'

        if total <= 0:
            out.append(
                f'<rect class="empty" x="{x:.1f}" y="{base_y - 3:.1f}" '
                f'width="{bw:.1f}" height="3" rx="1.5"></rect>'
            )
        else:
            y_cursor = base_y
            for ch in channels:  # empilement dans l'ordre fixe des canaux
                v = p["by_channel"].get(ch, 0)
                if v <= 0:
                    continue
                h = v / vmax * plot_h
                y = y_cursor - h
                out.append(
                    f'<rect class="seg {chan_class(ch)}" x="{x:.1f}" y="{y:.1f}" '
                    f'width="{bw:.1f}" height="{max(h - 2, 1.5):.1f}" rx="3">'
                    f'<title>{esc(p["label"])} · {esc(ch)} — {eur(v)} € HT</title></rect>'
                )
                y_cursor = y

        y_val = base_y - (max(total, 0) / vmax * plot_h) - 8
        out.append(
            f'<text class="vlabel{" today" if today else ""}" x="{cx:.1f}" '
            f'y="{max(y_val, 13):.1f}">{eur(total)}</text>'
        )
        out.append(
            f'<text class="xlabel{" today" if today else ""}" x="{cx:.1f}" '
            f'y="{H - 17:.1f}">{esc(p["label"][:5])}</text>'
        )
        if today:
            out.append(f'<text class="xsub" x="{cx:.1f}" y="{H - 4:.1f}">hier</text>')
        # Zone de survol pleine hauteur, plus large que la barre
        out.append(
            f'<rect class="hit" x="{cx - slot / 2:.1f}" y="{PAD_T}" '
            f'width="{slot:.1f}" height="{plot_h}"><title>{esc(tip)}</title></rect>'
        )

    legend = "".join(
        f'<span class="lg"><i class="{chan_class(c)}"></i>{esc(c)}</span>'
        for c in channels
    )
    return f"""
<section class="card">
  <div class="card-head">
    <h2>Tendance</h2>
    <div class="legend">{legend}</div>
  </div>
  <p class="sub-head">5 derniers memes jours de semaine, cumul HT par canal</p>
  <div class="chart-scroll">
    <svg class="chart" viewBox="0 0 {W} {H}" role="img"
         aria-label="Chiffre d'affaires B2B HT par jour, empile par canal">
      <line class="baseline" x1="{PAD_L}" y1="{base_y}" x2="{W - PAD_R}" y2="{base_y}"></line>
      {''.join(out)}
    </svg>
  </div>
</section>"""


def card(title, body, sub=None, meta=None, note=None, collapsed=False):
    head = f"""<div class="card-head">
    <h2>{esc(title)}</h2>{f'<div class="card-meta">{meta}</div>' if meta else ''}
  </div>{f'<p class="sub-head">{esc(sub)}</p>' if sub else ''}"""
    note_html = f'<p class="note">{esc(note)}</p>' if note else ""
    if collapsed:
        return f"""
<section class="card">
  <details>
    <summary>
      <span class="sum-title">{esc(title)}</span>
      {f'<span class="card-meta">{meta}</span>' if meta else ''}
      <span class="sum-caret" aria-hidden="true"></span>
    </summary>
    {body}{note_html}
  </details>
</section>"""
    return f"""
<section class="card">
  {head}{body}{note_html}
</section>"""


def rows_table(cols, rows):
    head = "".join(f'<th class="{c.get("cls","")}">{esc(c["label"])}</th>' for c in cols)
    body = "".join(
        "<tr>" + "".join(f'<td class="{c.get("cls","")}">{c["get"](r, i)}</td>'
                         for c in cols) + "</tr>"
        for i, r in enumerate(rows)
    )
    return (f'<div class="table-scroll"><table><thead><tr>{head}</tr></thead>'
            f'<tbody>{body}</tbody></table></div>')


def empty(msg):
    return f'<p class="empty-msg">{esc(msg)}</p>'


def name_list(items, limit=4):
    """'A, B, C…' — pas de point final, l'appelant ponctue."""
    names = [x["partner"] for x in items[:limit]]
    return ", ".join(names) + (f" et {len(items) - limit} autre(s)"
                               if len(items) > limit else "")


# --------------------------------------------------------------------------
# Page
# --------------------------------------------------------------------------

def render(d):
    channels = d["channels"]
    jour, tend = d["jour"], d["tendance"]
    delta = tend["delta_pct"]

    if delta is None:
        delta_html = '<span class="delta flat">pas de base de comparaison</span>'
    else:
        cls, sign = ("up", "+") if delta >= 0 else ("down", "")
        arrow = "&#9650;" if delta >= 0 else "&#9660;"
        delta_html = (
            f'<span class="delta {cls}">{arrow} {sign}{eur(delta, 1)} %</span>'
            f'<span class="delta-ctx">vs {eur(tend["moyenne_5"])} € de moyenne '
            f'sur 5 semaines</span>'
        )

    total = jour["total_ht"] or 1
    tiles = "".join(
        f"""
    <div class="tile {chan_class(c)}">
      <div class="tile-lab"><i></i>{esc(c)}</div>
      <div class="tile-val">{eur(jour["by_channel"][c]["ca"])} <small>€</small></div>
      <div class="tile-bar"><i style="width:{
          max(jour["by_channel"][c]["ca"] / total * 100, 0):.1f}%"></i></div>
      <div class="tile-sub">{eur(jour["by_channel"][c]["ca"] / total * 100) if jour["total_ht"] else "0"} %
        · {jour["by_channel"][c]["n"]} fact.</div>
    </div>"""
        for c in channels
    )

    mtd = d["mtd"]
    mtd_since = date.fromisoformat(mtd["depuis"])
    mtd_max = max(list(mtd["by_channel"].values()) + [1])
    mtd_rows = "".join(
        f"""<div class="mrow {chan_class(c)}">
      <span class="mrow-lab"><i></i>{esc(c)}</span>
      <span class="wbar {chan_class(c)}"><i style="width:{
          max(mtd["by_channel"][c] / mtd_max * 100, 0):.1f}%"></i></span>
      <span class="mrow-val">{eur(mtd["by_channel"][c])} €</span>
    </div>"""
        for c in channels
    )

    # --- Top clients ---
    cl = d["top_clients"]
    cl_max = max([c["ca"] for c in cl] + [1])
    clients_card = card(
        "Top clients du jour",
        rows_table([
            {"label": "", "cls": "rank", "get": lambda r, i: f"{i + 1}"},
            {"label": "Client", "cls": "wide",
             "get": lambda r, i: name_cell(r["partner"]) + " " + chip(r["channel"])},
            {"label": "Fact.", "cls": "num dim", "get": lambda r, i: str(r["n"])},
            {"label": "", "cls": "barcol",
             "get": lambda r, i: bar(r["ca"], cl_max, chan_class(r["channel"]))},
            {"label": "CA HT", "cls": "num strong",
             "get": lambda r, i: eur(r["ca"], 2) + " €"},
        ], cl) if cl else empty("Aucune facture B2B postee sur la journee."),
        sub=f"{len(cl)} client(s) facture(s)" if cl else None,
    )

    # --- Top produits ---
    pr = d["top_produits"]
    pr_max = max([p["ca"] for p in pr] + [1])
    produits_card = card(
        "Top produits du jour",
        rows_table([
            {"label": "", "cls": "rank", "get": lambda r, i: f"{i + 1}"},
            {"label": "Produit", "cls": "wide",
             "get": lambda r, i: (f'<span class="code">{esc(split_code(r["label"])[0])}</span>'
                                  if split_code(r["label"])[0] else "")
                                 + name_cell(split_code(r["label"])[1])},
            {"label": "Qte", "cls": "num dim", "get": lambda r, i: eur(r["qty"])},
            {"label": "", "cls": "barcol", "get": lambda r, i: bar(r["ca"], pr_max)},
            {"label": "CA HT", "cls": "num strong",
             "get": lambda r, i: eur(r["ca"], 2) + " €"},
        ], pr) if pr else empty("Aucune ligne produit sur la journee."),
        sub="Classement par CA HT" if pr else None,
    )

    # --- Detail factures (replie : c'est le niveau de zoom, pas la synthese) ---
    facts = jour["factures"]
    refunds = [f for f in facts if f["is_refund"] or f["untaxed"] < 0]
    zeros = [f for f in facts if f["untaxed"] == 0]
    shown = [f for f in facts if f["untaxed"] != 0]
    detail_note = None
    if zeros:
        detail_note = f"{len(zeros)} facture(s) a 0,00 € masquee(s) : {name_list(zeros)}."
    detail_card = card(
        f"Detail des factures",
        rows_table([
            {"label": "Piece", "cls": "mono", "get": lambda r, i: esc(r["name"])},
            {"label": "Client", "cls": "wide",
             "get": lambda r, i: name_cell(r["partner"]) + " " + chip(r["channel"])},
            {"label": "Origine", "cls": "mono dim",
             "get": lambda r, i: esc(r["origin"]) or "—"},
            {"label": "HT", "cls": "num strong",
             "get": lambda r, i: (f'<span class="refund">{eur(r["untaxed"], 2)} €</span>'
                                  if r["untaxed"] < 0 else f'{eur(r["untaxed"], 2)} €')},
        ], shown) if shown else empty("Aucune facture B2B postee sur la journee."),
        meta=f'<span class="pill">{len(shown)}</span>'
             + (f'<span class="pill neg">{len(refunds)} avoir(s)</span>' if refunds else ""),
        note=detail_note,
        collapsed=True,
    )

    # --- Pipeline devis ---
    def age_cell(r, i):
        a = r.get("age_days")
        if a is None:
            return '<span class="dim">—</span>'
        cls = "old" if a >= 30 else ("mid" if a >= 14 else "fresh")
        return f'<span class="age {cls}">{a} j</span>'

    pipe = d["pipeline"]
    pipe_items = [p for p in pipe["items"] if p["untaxed"] > 0]
    pipe_zero = len(pipe["items"]) - len(pipe_items)
    pipeline_card = card(
        "Pipeline devis",
        rows_table([
            {"label": "Devis", "cls": "mono", "get": lambda r, i: esc(r["name"])},
            {"label": "Client", "cls": "wide",
             "get": lambda r, i: name_cell(r["partner"]) + " " + chip(r["channel"])},
            {"label": "Age", "cls": "num", "get": age_cell},
            {"label": "Montant HT", "cls": "num strong",
             "get": lambda r, i: eur(r["untaxed"], 2) + " €"},
        ], pipe_items) if pipe_items else empty("Aucun devis B2B chiffre en attente."),
        sub="Devis en brouillon ou envoyes, non confirmes",
        meta=f'<span class="pill">{pipe["nb"]}</span>'
             f'<span class="pill val">{eur(pipe["total_ht"])} €</span>',
        note=(f"{pipe_zero} devis a 0,00 € masque(s)." if pipe_zero else None),
    )

    # --- Brouillons ---
    dr = d["drafts"]
    dr_items = [x for x in dr["items"] if x["untaxed"] > 0]
    dr_zero = [x for x in dr["items"] if x["untaxed"] == 0]
    drafts_card = card(
        "Factures en brouillon",
        rows_table([
            {"label": "Client", "cls": "wide",
             "get": lambda r, i: name_cell(r["partner"]) + " " + chip(r["channel"])},
            {"label": "Date", "cls": "num dim mono",
             "get": lambda r, i: esc(r["date"][8:10] + "/" + r["date"][5:7]) if r["date"] else "—"},
            {"label": "Montant HT", "cls": "num strong",
             "get": lambda r, i: eur(r["untaxed"], 2) + " €"},
        ], dr_items) if dr_items else empty("Aucun brouillon chiffre en attente."),
        sub="A poster ou a arbitrer",
        meta=f'<span class="pill">{dr["nb"]}</span>'
             f'<span class="pill val">{eur(dr["total_ht"])} €</span>',
        note=(f"{len(dr_zero)} brouillon(s) a 0,00 € en attente d'arbitrage "
              f"manuel : {name_list(dr_zero)}.") if dr_zero else None,
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
    --bg: #f4f6f5; --card: #fff; --line: #e6ebe8; --line-soft: #f0f4f2;
    --ink: #14201b; --ink-2: #5a6862; --ink-3: #8d968f;
    --brand: #2d6a4f; --hover: #f7faf8;
    --up: #197f49; --down: #c0392b;
    --s1: #2a78d6; --s2: #eb6834; --s3: #1baf7a;
    --shadow: 0 1px 2px rgba(16,32,24,.05), 0 6px 18px -8px rgba(16,32,24,.12);
  }}
  @media (prefers-color-scheme: dark) {{
    :root:where(:not([data-theme="light"])) {{
      --bg: #101210; --card: #191c19; --line: #2a2e2a; --line-soft: #212521;
      --ink: #f1f4f1; --ink-2: #b3bbb4; --ink-3: #7b837c;
      --brand: #6fbb92; --hover: #1f231f;
      --up: #57c98a; --down: #e8756a;
      --s1: #3987e5; --s2: #d95926; --s3: #199e70;
      --shadow: 0 1px 2px rgba(0,0,0,.4), 0 6px 18px -8px rgba(0,0,0,.6);
    }}
  }}
  :root[data-theme="dark"] {{
    color-scheme: dark;
    --bg: #101210; --card: #191c19; --line: #2a2e2a; --line-soft: #212521;
    --ink: #f1f4f1; --ink-2: #b3bbb4; --ink-3: #7b837c;
    --brand: #6fbb92; --hover: #1f231f;
    --up: #57c98a; --down: #e8756a;
    --s1: #3987e5; --s2: #d95926; --s3: #199e70;
    --shadow: 0 1px 2px rgba(0,0,0,.4), 0 6px 18px -8px rgba(0,0,0,.6);
  }}

  * {{ box-sizing: border-box; }}
  html {{ -webkit-text-size-adjust: 100%; }}
  body {{
    margin: 0 auto; padding: 1.4rem 1rem 3.5rem; max-width: 880px;
    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
    background: var(--bg); color: var(--ink); line-height: 1.45;
  }}

  header {{ margin-bottom: 1.2rem; }}
  .kicker {{ font-size: .7rem; letter-spacing: .12em; text-transform: uppercase;
             color: var(--brand); font-weight: 700; }}
  h1 {{ font-size: 1.4rem; margin: .2rem 0 .15rem; letter-spacing: -.015em;
        font-weight: 700; }}
  .sub {{ color: var(--ink-2); font-size: .85rem; }}

  /* ---- hero ---- */
  .hero {{ background: var(--card); border: 1px solid var(--line);
           border-radius: 16px; padding: 1.2rem 1.25rem; box-shadow: var(--shadow);
           margin-bottom: .7rem; }}
  .hero-lab {{ font-size: .72rem; color: var(--ink-2); text-transform: uppercase;
               letter-spacing: .09em; font-weight: 700; }}
  .hero-val {{ font-size: 2.7rem; font-weight: 700; line-height: 1.02;
               letter-spacing: -.03em; margin: .3rem 0 .4rem;
               font-variant-numeric: tabular-nums; }}
  .hero-val small {{ font-size: 1.05rem; font-weight: 600; color: var(--ink-2);
                     letter-spacing: 0; }}
  .delta {{ font-size: .85rem; font-weight: 700; margin-right: .45rem; }}
  .delta.up {{ color: var(--up); }} .delta.down {{ color: var(--down); }}
  .delta.flat {{ color: var(--ink-3); font-weight: 600; }}
  .delta-ctx {{ font-size: .8rem; color: var(--ink-2); }}
  .hero-n {{ font-size: .8rem; color: var(--ink-3); margin-top: .5rem;
             padding-top: .5rem; border-top: 1px solid var(--line-soft); }}

  /* ---- tuiles canal ---- */
  .tiles {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: .55rem;
            margin-bottom: .7rem; }}
  @media (max-width: 540px) {{ .tiles {{ grid-template-columns: 1fr; }} }}
  .tile {{ background: var(--card); border: 1px solid var(--line);
           border-radius: 13px; padding: .8rem .9rem; box-shadow: var(--shadow); }}
  .tile-lab {{ display: flex; align-items: center; gap: .42rem; font-size: .76rem;
               color: var(--ink-2); font-weight: 600; }}
  .tile-lab i {{ width: 9px; height: 9px; border-radius: 3px; flex: none; }}
  .tile.s1 .tile-lab i, .tile.s1 .tile-bar i {{ background: var(--s1); }}
  .tile.s2 .tile-lab i, .tile.s2 .tile-bar i {{ background: var(--s2); }}
  .tile.s3 .tile-lab i, .tile.s3 .tile-bar i {{ background: var(--s3); }}
  .tile-val {{ font-size: 1.4rem; font-weight: 700; margin: .3rem 0 .4rem;
               font-variant-numeric: tabular-nums; letter-spacing: -.02em; }}
  .tile-val small {{ font-size: .85rem; font-weight: 600; color: var(--ink-2); }}
  .tile-bar {{ height: 4px; border-radius: 2px; background: var(--line);
               overflow: hidden; }}
  .tile-bar i {{ display: block; height: 100%; border-radius: 2px; }}
  .tile-sub {{ font-size: .73rem; color: var(--ink-3); margin-top: .35rem; }}

  /* ---- cartes ---- */
  .card {{ background: var(--card); border: 1px solid var(--line);
           border-radius: 16px; box-shadow: var(--shadow); margin-bottom: .7rem;
           overflow: hidden; }}
  .card-head {{ display: flex; justify-content: space-between; align-items: center;
                gap: .6rem; flex-wrap: wrap; padding: .85rem 1rem .1rem; }}
  .card-head h2 {{ font-size: .95rem; margin: 0; font-weight: 700;
                   letter-spacing: -.01em; }}
  .sub-head {{ font-size: .76rem; color: var(--ink-3); margin: .1rem 0 .6rem;
               padding: 0 1rem; }}
  .card-meta {{ display: flex; gap: .35rem; align-items: center; }}
  .pill {{ font-size: .7rem; font-weight: 700; padding: 2px 8px; border-radius: 999px;
           background: var(--bg); color: var(--ink-2); border: 1px solid var(--line);
           font-variant-numeric: tabular-nums; white-space: nowrap; }}
  .pill.val {{ color: var(--ink); }}
  .pill.neg {{ color: var(--down); }}

  details > summary {{ display: flex; align-items: center; gap: .6rem;
                       padding: .85rem 1rem; cursor: pointer; list-style: none;
                       user-select: none; }}
  details > summary::-webkit-details-marker {{ display: none; }}
  .sum-title {{ font-size: .95rem; font-weight: 700; margin-right: auto; }}
  .sum-caret {{ width: 7px; height: 7px; border-right: 2px solid var(--ink-3);
                border-bottom: 2px solid var(--ink-3); transform: rotate(45deg);
                transition: transform .15s; margin-left: .1rem; }}
  details[open] .sum-caret {{ transform: rotate(-135deg); }}
  details > summary:hover {{ background: var(--hover); }}

  /* ---- graphique ---- */
  .legend {{ display: flex; gap: .65rem; flex-wrap: wrap; }}
  .lg {{ display: inline-flex; align-items: center; gap: .3rem; font-size: .73rem;
         color: var(--ink-2); font-weight: 600; }}
  .lg i {{ width: 9px; height: 9px; border-radius: 3px; }}
  .lg i.s1 {{ background: var(--s1); }} .lg i.s2 {{ background: var(--s2); }}
  .lg i.s3 {{ background: var(--s3); }}
  .chart-scroll {{ overflow-x: auto; padding: 0 .55rem .55rem; }}
  .chart {{ width: 100%; min-width: 440px; height: auto; display: block; }}
  .chart .baseline {{ stroke: var(--line); stroke-width: 1; }}
  .chart .seg.s1 {{ fill: var(--s1); }} .chart .seg.s2 {{ fill: var(--s2); }}
  .chart .seg.s3 {{ fill: var(--s3); }}
  .chart .empty {{ fill: var(--ink-3); opacity: .4; }}
  .chart .hit {{ fill: transparent; }}
  .chart .hit:hover {{ fill: var(--ink); opacity: .04; }}
  .chart .vlabel {{ font-size: 11px; font-weight: 600; fill: var(--ink-3);
                    text-anchor: middle; font-variant-numeric: tabular-nums; }}
  .chart .vlabel.today {{ fill: var(--ink); font-weight: 700; font-size: 12px; }}
  .chart .xlabel {{ font-size: 10.5px; fill: var(--ink-3); text-anchor: middle; }}
  .chart .xlabel.today {{ fill: var(--ink); font-weight: 700; }}
  .chart .xsub {{ font-size: 8.5px; fill: var(--brand); text-anchor: middle;
                  font-weight: 700; text-transform: uppercase; letter-spacing: .08em; }}

  /* ---- cumul mois ---- */
  .mtd {{ padding: 0 1rem .9rem; display: grid; gap: .4rem; }}
  .mrow {{ display: grid; grid-template-columns: 6.5rem 1fr auto; align-items: center;
           gap: .6rem; font-size: .8rem; }}
  .mrow-lab {{ display: inline-flex; align-items: center; gap: .4rem;
               color: var(--ink-2); font-weight: 600; }}
  .mrow-lab i {{ width: 9px; height: 9px; border-radius: 3px; flex: none; }}
  .mrow.s1 .mrow-lab i {{ background: var(--s1); }}
  .mrow.s2 .mrow-lab i {{ background: var(--s2); }}
  .mrow.s3 .mrow-lab i {{ background: var(--s3); }}
  .mrow-val {{ font-weight: 700; font-variant-numeric: tabular-nums;
               white-space: nowrap; }}

  /* ---- barres de poids en ligne ---- */
  .wbar {{ display: block; width: 100%; height: 5px; border-radius: 3px;
           background: var(--line); overflow: hidden; }}
  .wbar i {{ display: block; height: 100%; border-radius: 3px; background: var(--ink-3);
             opacity: .55; }}
  .wbar.s1 i {{ background: var(--s1); opacity: .85; }}
  .wbar.s2 i {{ background: var(--s2); opacity: .85; }}
  .wbar.s3 i {{ background: var(--s3); opacity: .85; }}

  /* ---- tableaux ---- */
  .table-scroll {{ overflow-x: auto; }}
  table {{ width: 100%; border-collapse: collapse; font-size: .84rem; }}
  th {{ text-align: left; font-size: .67rem; text-transform: uppercase;
        letter-spacing: .07em; color: var(--ink-3); font-weight: 700;
        padding: .3rem 1rem .5rem; border-bottom: 1px solid var(--line);
        white-space: nowrap; }}
  td {{ padding: .55rem 1rem; border-bottom: 1px solid var(--line-soft);
        vertical-align: middle; }}
  tbody tr:last-child td {{ border-bottom: none; }}
  tbody tr:hover td {{ background: var(--hover); }}
  th.num, td.num {{ text-align: right; font-variant-numeric: tabular-nums;
                    white-space: nowrap; }}
  td.strong {{ font-weight: 700; }}
  td.dim, .dim {{ color: var(--ink-3); }}
  td.mono, .mono {{ font-family: ui-monospace, 'Cascadia Mono', Consolas, monospace;
                    font-size: .78rem; white-space: nowrap; }}
  th.rank, td.rank {{ width: 1.6rem; padding-right: 0; color: var(--ink-3);
                      font-size: .74rem; font-weight: 700;
                      font-variant-numeric: tabular-nums; }}
  th.wide, td.wide {{ width: 100%; }}
  /* min-width, pas width : la colonne voisine est en width:100% et ecraserait
     sinon la barre a la largeur de son contenu */
  th.barcol, td.barcol {{ min-width: 6.5rem; padding-left: .4rem; padding-right: .6rem; }}
  @media (max-width: 560px) {{ th.barcol, td.barcol {{ display: none; }} }}
  .nm {{ display: inline-block; max-width: 24rem; overflow: hidden;
         text-overflow: ellipsis; white-space: nowrap; vertical-align: bottom; }}
  .code {{ font-family: ui-monospace, 'Cascadia Mono', Consolas, monospace;
           font-size: .68rem; font-weight: 700; color: var(--ink-3);
           background: var(--bg); border: 1px solid var(--line);
           border-radius: 4px; padding: 1px 5px; margin-right: .4rem;
           vertical-align: 1px; }}
  .chip {{ display: inline-block; padding: 1px 7px; border-radius: 5px;
           font-size: .65rem; font-weight: 700; color: #fff; white-space: nowrap;
           vertical-align: 1px; }}
  .chip.s1 {{ background: var(--s1); }} .chip.s2 {{ background: var(--s2); }}
  .chip.s3 {{ background: var(--s3); }}
  .refund {{ color: var(--down); }}
  .age {{ font-weight: 700; font-size: .78rem; }}
  .age.fresh {{ color: var(--up); }}
  .age.mid {{ color: var(--ink-2); }}
  .age.old {{ color: var(--down); }}
  .note {{ font-size: .73rem; color: var(--ink-3); padding: .6rem 1rem .8rem;
           margin: 0; border-top: 1px solid var(--line-soft); }}
  .empty-msg {{ font-size: .83rem; color: var(--ink-3); padding: 0 1rem 1rem;
                margin: 0; }}
  footer {{ margin-top: 1.6rem; font-size: .72rem; color: var(--ink-3);
            text-align: center; line-height: 1.7; }}
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

<div class="tiles">{tiles}</div>

{trend_chart(tend, channels)}

<section class="card">
  <div class="card-head">
    <h2>Cumul du mois</h2>
    <div class="card-meta">
      <span class="pill val">{eur(mtd["total_ht"], 2)} € HT</span>
      <span class="pill">{mtd["nb_factures"]} fact.</span>
    </div>
  </div>
  <p class="sub-head">Depuis le {mtd_since.day:02d}/{mtd_since.month:02d}</p>
  <div class="mtd">{mtd_rows}</div>
</section>

{clients_card}
{produits_card}
{pipeline_card}
{drafts_card}
{detail_card}

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
