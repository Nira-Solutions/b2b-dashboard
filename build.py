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
import html
import json
import re
import shutil
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent

CHANNEL_SLOT = {"GMS": "c1", "Horeca": "c2", "Revendeurs": "c3"}
RE_CODE = re.compile(r"^\[([^\]]+)\]\s*(.*)$")


def eur(v, decimals=2):
    return f"{v:,.{decimals}f}".replace(",", " ").replace(".", ",")


def esc(s):
    return html.escape(str(s if s is not None else ""))


def slot(ch):
    return CHANNEL_SLOT.get(ch, "c0")


def split_code(label):
    m = RE_CODE.match(label or "")
    return (m.group(1), m.group(2)) if m else ("", label or "")


def trunc(s, n=52):
    s = s or ""
    return s if len(s) <= n else s[: n - 1] + "…"


def badge(pct, neutral_if_none=True):
    """Badge d'evolution facon vilnagaon : ↑ vert / ↓ rouge / — gris."""
    if pct is None:
        return '<span class="badge neutral">&mdash;</span>' if neutral_if_none else "&mdash;"
    if pct == float("inf"):
        return '<span class="badge up">+&infin;</span>'
    if pct >= 0:
        return f'<span class="badge up">&uarr; {eur(pct, 1)}%</span>'
    return f'<span class="badge down">&darr; {eur(abs(pct), 1)}%</span>'


def rank_medal(i):
    cls = f" rank-{i + 1}" if i < 3 else ""
    return f'<span class="rank{cls}">{i + 1}</span>'


def pct_change(now, before):
    if before is None or before == 0:
        return float("inf") if now > 0 else None
    return (now - before) / abs(before) * 100


def kpi(value, label, tone=""):
    return (f'<div class="kpi-box{" " + tone if tone else ""}">'
            f'<div class="value">{value}</div>'
            f'<div class="label">{esc(label)}</div></div>')


def card(title, body, extra_class=""):
    return (f'<div class="card{" " + extra_class if extra_class else ""}">'
            f'<h2>{esc(title)}</h2>{body}</div>')


def section(title):
    return f'<div class="section-title">{esc(title)}</div>'


def empty(msg):
    return f'<p class="empty">{esc(msg)}</p>'


def name_list(items, limit=4):
    names = [x["partner"] for x in items[:limit]]
    return ", ".join(names) + (f" et {len(items) - limit} autre(s)"
                               if len(items) > limit else "")


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


def table(head_cells, rows, cols):
    head = "".join(f'<th class="{c.get("cls","")}">{h}</th>'
                   for h, c in zip(head_cells, cols))
    body = "".join(
        "<tr>" + "".join(f'<td class="{c.get("cls","")}">{c["get"](r, i)}</td>'
                         for c in cols) + "</tr>"
        for i, r in enumerate(rows)
    )
    return f"<table><tr>{head}</tr>{body}</table>"


def note(txt):
    return f'<p class="note">{esc(txt)}</p>' if txt else ""


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
  :root {{
    --bg: #f8f7f4;
    --card: #ffffff;
    --border: #e8e5df;
    --text: #2c2c2c;
    --muted: #7a7a7a;
    --accent: #5b7f5e;
    --accent-light: #e8f0e8;
    --up: #2e7d32;
    --up-bg: #e8f5e9;
    --down: #c62828;
    --down-bg: #ffebee;
    --neutral: #666;
    --neutral-bg: #f5f5f5;
    --gold: #c6930a;
    --silver: #757575;
    --bronze: #a0522d;
    /* Canaux : triade validee sur fond creme (chroma, CVD, vision normale,
       contraste >= 3:1). La sauge --accent lit gris en aplat, elle reste
       reservee aux titres et aux kpi-box. */
    --c1: #2f6ba8;
    --c2: #c0562a;
    --c3: #1a8f66;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: var(--bg);
    color: var(--text);
    padding: 24px;
    max-width: 1200px;
    margin: 0 auto;
    font-size: 14px;
    line-height: 1.5;
  }}
  header {{
    display: flex; justify-content: space-between; align-items: center;
    margin-bottom: 28px; padding-bottom: 16px;
    border-bottom: 2px solid var(--accent);
  }}
  header h1 {{ font-size: 22px; font-weight: 700; color: var(--accent); }}
  header .meta {{ text-align: right; color: var(--muted); font-size: 13px; }}

  .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 24px; }}
  .grid.three {{ grid-template-columns: 1fr 1fr 1fr; }}
  .grid.full {{ grid-template-columns: 1fr; }}

  .card {{
    background: var(--card); border: 1px solid var(--border); border-radius: 10px;
    padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.04);
  }}
  .card h2 {{
    font-size: 14px; font-weight: 600; color: var(--muted);
    text-transform: uppercase; letter-spacing: 0.5px;
    margin-bottom: 14px; padding-bottom: 8px; border-bottom: 1px solid var(--border);
  }}
  .section-title {{
    font-size: 16px; font-weight: 700; color: var(--text);
    margin: 28px 0 16px; padding-bottom: 8px; border-bottom: 1px solid var(--border);
  }}

  .kpi-row {{ display: flex; justify-content: space-between; gap: 12px; margin-bottom: 16px; }}
  .kpi-box {{ flex: 1; text-align: center; padding: 12px 8px;
              background: var(--accent-light); border-radius: 8px; }}
  .kpi-box .value {{ font-size: 22px; font-weight: 700; color: var(--accent);
                     white-space: nowrap; }}
  .kpi-box .value .badge {{ font-size: 15px; }}
  .kpi-box .label {{ font-size: 11px; color: var(--muted); text-transform: uppercase;
                     letter-spacing: 0.3px; margin-top: 2px; }}

  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th {{ text-align: left; padding: 8px 10px; font-weight: 600; font-size: 11px;
        text-transform: uppercase; letter-spacing: 0.3px; color: var(--muted);
        border-bottom: 2px solid var(--border); white-space: nowrap; }}
  th.right, td.right {{ text-align: right; white-space: nowrap; }}
  td {{ padding: 7px 10px; border-bottom: 1px solid var(--border); vertical-align: middle; }}
  tr:last-child td {{ border-bottom: none; }}
  tr:hover td {{ background: #fafaf8; }}
  td.mono, .mono {{ font-family: 'SF Mono', Menlo, Consolas, monospace; font-size: 12px;
                    white-space: nowrap; }}
  td.muted, .muted {{ color: var(--muted); }}
  td.medal, th.medal {{ width: 34px; }}
  .neg {{ color: var(--down); }}

  .badge {{ display: inline-block; padding: 2px 8px; border-radius: 10px;
            font-size: 12px; font-weight: 600; white-space: nowrap; }}
  .badge.up {{ background: var(--up-bg); color: var(--up); }}
  .badge.down {{ background: var(--down-bg); color: var(--down); }}
  .badge.neutral {{ background: var(--neutral-bg); color: var(--neutral); }}

  .rank {{ display: inline-block; width: 22px; height: 22px; line-height: 22px;
           text-align: center; border-radius: 50%; font-weight: 700; font-size: 12px;
           color: var(--muted); background: var(--neutral-bg); }}
  .rank-1 {{ background: #fff8e1; color: var(--gold); }}
  .rank-2 {{ background: #f5f5f5; color: var(--silver); }}
  .rank-3 {{ background: #fbe9e7; color: var(--bronze); }}

  .sku {{ font-family: 'SF Mono', Menlo, Consolas, monospace; font-size: 11px;
          color: var(--accent); font-weight: 600; }}
  .tag {{ display: inline-block; padding: 1px 8px; border-radius: 10px;
          font-size: 11px; font-weight: 600; color: #fff; white-space: nowrap; }}
  .tag.c1 {{ background: var(--c1); }}
  .tag.c2 {{ background: var(--c2); }}
  .tag.c3 {{ background: var(--c3); }}
  .dot {{ display: inline-block; width: 10px; height: 10px; border-radius: 50%;
          margin-right: 7px; vertical-align: 0; }}
  .dot.c1 {{ background: var(--c1); }}
  .dot.c2 {{ background: var(--c2); }}
  .dot.c3 {{ background: var(--c3); }}

  /* ---- cartes canal ---- */
  .chan-card {{
    background: var(--card); border: 1px solid var(--border); border-radius: 10px;
    padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.04);
  }}
  .chan-card.rank-first {{ border-left: 4px solid var(--gold); }}
  .chan-card.rank-second {{ border-left: 4px solid var(--silver); }}
  .chan-card.rank-third {{ border-left: 4px solid var(--bronze); }}
  .chan-header {{ display: flex; justify-content: space-between; align-items: center;
                  margin-bottom: 14px; padding-bottom: 10px;
                  border-bottom: 1px solid var(--border); }}
  .chan-header h2 {{ font-size: 16px; font-weight: 700; color: var(--text);
                     margin: 0; padding: 0; border: none; text-transform: none;
                     letter-spacing: 0; display: flex; align-items: center; }}
  .chan-rank {{ font-size: 12px; font-weight: 600; padding: 3px 10px; border-radius: 12px; }}
  .chan-rank.r1 {{ background: #fff8e1; color: var(--gold); }}
  .chan-rank.r2 {{ background: #f5f5f5; color: var(--silver); }}
  .chan-rank.r3 {{ background: #fbe9e7; color: var(--bronze); }}
  .chan-foot {{ font-size: 12px; color: var(--muted); display: flex;
                align-items: center; gap: 8px; }}

  /* ---- barres horizontales ---- */
  .legend {{ display: flex; gap: 16px; margin-bottom: 12px; flex-wrap: wrap; }}
  .lg {{ display: inline-flex; align-items: center; gap: 6px; font-size: 12px;
         color: var(--muted); font-weight: 600; }}
  .lg i {{ width: 10px; height: 10px; border-radius: 50%; }}
  .lg i.c1 {{ background: var(--c1); }}
  .lg i.c2 {{ background: var(--c2); }}
  .lg i.c3 {{ background: var(--c3); }}
  .hour-bar {{ display: flex; align-items: center; gap: 10px; margin-bottom: 7px;
               font-size: 12px; }}
  .hour-bar .hour-label {{ width: 110px; color: var(--muted); flex: none;
                           white-space: nowrap; }}
  .hour-bar .hour-label em {{ font-style: normal; color: var(--accent);
                              font-weight: 700; font-size: 10px;
                              text-transform: uppercase; margin-left: 6px; }}
  .hour-bar .bar-track {{ flex: 1; background: #f2f1ec; border-radius: 3px;
                          height: 16px; overflow: hidden; }}
  .hour-bar .bar {{ display: flex; height: 100%; border-radius: 3px;
                    overflow: hidden; min-width: 2px; }}
  .hour-bar .bar span {{ display: block; height: 100%; }}
  .hour-bar .bar .c1 {{ background: var(--c1); }}
  .hour-bar .bar .c2 {{ background: var(--c2); }}
  .hour-bar .bar .c3 {{ background: var(--c3); }}
  .hour-bar .bar-value {{ min-width: 86px; text-align: right; font-weight: 700;
                          color: var(--text); white-space: nowrap; }}
  .hour-bar .bar-count {{ min-width: 54px; text-align: right; color: var(--muted);
                          white-space: nowrap; }}
  .hour-bar.today .hour-label,
  .hour-bar.today .bar-value {{ color: var(--text); font-weight: 700; }}

  .empty {{ color: var(--muted); font-style: italic; padding: 12px 0; }}
  .note {{ color: var(--muted); font-size: 12px; margin-top: 12px;
           padding-top: 10px; border-top: 1px solid var(--border); }}
  footer {{ margin-top: 32px; padding-top: 16px; border-top: 1px solid var(--border);
            color: var(--muted); font-size: 12px; text-align: center; }}

  @media (max-width: 768px) {{
    body {{ padding: 16px; }}
    header {{ flex-direction: column; align-items: flex-start; gap: 8px; }}
    header .meta {{ text-align: left; }}
    .grid, .grid.three {{ grid-template-columns: 1fr; }}
    .kpi-row {{ flex-wrap: wrap; }}
    .kpi-box {{ min-width: 45%; }}
    .hour-bar .hour-label {{ width: 76px; }}
    .hour-bar .bar-count {{ display: none; }}
    table {{ font-size: 12px; }}
    td, th {{ padding: 6px 6px; }}
  }}
</style>
</head>
<body>

<header>
  <h1>B2B Morning Dashboard &mdash; Teatower</h1>
  <div class="meta">
    <div><strong>{gen.strftime("%Y-%m-%d")}</strong> &middot; Donn&eacute;es du {d["target_date"]}</div>
    <div>G&eacute;n&eacute;r&eacute; le {gen.strftime("%Y-%m-%d %H:%M")}</div>
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
        shutil.copyfile(data_path, dd / "data.json")
        print(f"OK  {dd / 'index.html'}")
        print(f"OK  {dd / 'data.json'}")


if __name__ == "__main__":
    main()
