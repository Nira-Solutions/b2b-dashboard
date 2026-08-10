"""
b2b_style.py — Feuille de style partagee des dashboards B2B Teatower.

Extraite de `build_b2b_dashboard.py` pour que le daily (`index.html`) et le
weekly (`weekly/index.html`) restent visuellement identiques : meme fond creme
#f8f7f4, meme accent sauge #5b7f5e, meme triade canaux #2f6ba8 / #c0562a /
#1a8f66 (validee chroma / CVD / contraste sur fond creme).

CSS       : le socle commun (header, cartes, kpi-box, tableaux, badges, barres).
CSS_WEEKLY: les quelques regles specifiques a la vue hebdo (bloc alerte,
            listes clients/dormants, sparkline de semaines).

Les deux modules injectent `CSS` (+ `CSS_WEEKLY`) dans leur balise <style> ;
toute retouche visuelle se fait donc ici, une seule fois.
"""

CSS = """  :root {
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
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: var(--bg);
    color: var(--text);
    padding: 24px;
    max-width: 1200px;
    margin: 0 auto;
    font-size: 14px;
    line-height: 1.5;
  }
  header {
    display: flex; justify-content: space-between; align-items: center;
    margin-bottom: 28px; padding-bottom: 16px;
    border-bottom: 2px solid var(--accent);
  }
  header h1 { font-size: 22px; font-weight: 700; color: var(--accent); }
  header .meta { text-align: right; color: var(--muted); font-size: 13px; }

  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 24px; }
  .grid.three { grid-template-columns: 1fr 1fr 1fr; }
  .grid.full { grid-template-columns: 1fr; }

  .card {
    background: var(--card); border: 1px solid var(--border); border-radius: 10px;
    padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.04);
  }
  .card h2 {
    font-size: 14px; font-weight: 600; color: var(--muted);
    text-transform: uppercase; letter-spacing: 0.5px;
    margin-bottom: 14px; padding-bottom: 8px; border-bottom: 1px solid var(--border);
  }
  .section-title {
    font-size: 16px; font-weight: 700; color: var(--text);
    margin: 28px 0 16px; padding-bottom: 8px; border-bottom: 1px solid var(--border);
  }

  .kpi-row { display: flex; justify-content: space-between; gap: 12px; margin-bottom: 16px; }
  .kpi-box { flex: 1; text-align: center; padding: 12px 8px;
              background: var(--accent-light); border-radius: 8px; }
  .kpi-box .value { font-size: 22px; font-weight: 700; color: var(--accent);
                     white-space: nowrap; }
  .kpi-box .value .badge { font-size: 15px; }
  .kpi-box .label { font-size: 11px; color: var(--muted); text-transform: uppercase;
                     letter-spacing: 0.3px; margin-top: 2px; }

  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th { text-align: left; padding: 8px 10px; font-weight: 600; font-size: 11px;
        text-transform: uppercase; letter-spacing: 0.3px; color: var(--muted);
        border-bottom: 2px solid var(--border); white-space: nowrap; }
  th.right, td.right { text-align: right; white-space: nowrap; }
  td { padding: 7px 10px; border-bottom: 1px solid var(--border); vertical-align: middle; }
  tr:last-child td { border-bottom: none; }
  tr:hover td { background: #fafaf8; }
  td.mono, .mono { font-family: 'SF Mono', Menlo, Consolas, monospace; font-size: 12px;
                    white-space: nowrap; }
  td.muted, .muted { color: var(--muted); }
  td.medal, th.medal { width: 34px; }
  .neg { color: var(--down); }

  .badge { display: inline-block; padding: 2px 8px; border-radius: 10px;
            font-size: 12px; font-weight: 600; white-space: nowrap; }
  .badge.up { background: var(--up-bg); color: var(--up); }
  .badge.down { background: var(--down-bg); color: var(--down); }
  .badge.neutral { background: var(--neutral-bg); color: var(--neutral); }

  .rank { display: inline-block; width: 22px; height: 22px; line-height: 22px;
           text-align: center; border-radius: 50%; font-weight: 700; font-size: 12px;
           color: var(--muted); background: var(--neutral-bg); }
  .rank-1 { background: #fff8e1; color: var(--gold); }
  .rank-2 { background: #f5f5f5; color: var(--silver); }
  .rank-3 { background: #fbe9e7; color: var(--bronze); }

  .sku { font-family: 'SF Mono', Menlo, Consolas, monospace; font-size: 11px;
          color: var(--accent); font-weight: 600; }
  .tag { display: inline-block; padding: 1px 8px; border-radius: 10px;
          font-size: 11px; font-weight: 600; color: #fff; white-space: nowrap; }
  .tag.c1 { background: var(--c1); }
  .tag.c2 { background: var(--c2); }
  .tag.c3 { background: var(--c3); }
  .dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%;
          margin-right: 7px; vertical-align: 0; }
  .dot.c1 { background: var(--c1); }
  .dot.c2 { background: var(--c2); }
  .dot.c3 { background: var(--c3); }

  /* ---- cartes canal ---- */
  .chan-card {
    background: var(--card); border: 1px solid var(--border); border-radius: 10px;
    padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.04);
  }
  .chan-card.rank-first { border-left: 4px solid var(--gold); }
  .chan-card.rank-second { border-left: 4px solid var(--silver); }
  .chan-card.rank-third { border-left: 4px solid var(--bronze); }
  .chan-header { display: flex; justify-content: space-between; align-items: center;
                  margin-bottom: 14px; padding-bottom: 10px;
                  border-bottom: 1px solid var(--border); }
  .chan-header h2 { font-size: 16px; font-weight: 700; color: var(--text);
                     margin: 0; padding: 0; border: none; text-transform: none;
                     letter-spacing: 0; display: flex; align-items: center; }
  .chan-rank { font-size: 12px; font-weight: 600; padding: 3px 10px; border-radius: 12px; }
  .chan-rank.r1 { background: #fff8e1; color: var(--gold); }
  .chan-rank.r2 { background: #f5f5f5; color: var(--silver); }
  .chan-rank.r3 { background: #fbe9e7; color: var(--bronze); }
  .chan-foot { font-size: 12px; color: var(--muted); display: flex;
                align-items: center; gap: 8px; }

  /* ---- barres horizontales ---- */
  .legend { display: flex; gap: 16px; margin-bottom: 12px; flex-wrap: wrap; }
  .lg { display: inline-flex; align-items: center; gap: 6px; font-size: 12px;
         color: var(--muted); font-weight: 600; }
  .lg i { width: 10px; height: 10px; border-radius: 50%; }
  .lg i.c1 { background: var(--c1); }
  .lg i.c2 { background: var(--c2); }
  .lg i.c3 { background: var(--c3); }
  .hour-bar { display: flex; align-items: center; gap: 10px; margin-bottom: 7px;
               font-size: 12px; }
  .hour-bar .hour-label { width: 110px; color: var(--muted); flex: none;
                           white-space: nowrap; }
  .hour-bar .hour-label em { font-style: normal; color: var(--accent);
                              font-weight: 700; font-size: 10px;
                              text-transform: uppercase; margin-left: 6px; }
  .hour-bar .bar-track { flex: 1; background: #f2f1ec; border-radius: 3px;
                          height: 16px; overflow: hidden; }
  .hour-bar .bar { display: flex; height: 100%; border-radius: 3px;
                    overflow: hidden; min-width: 2px; }
  .hour-bar .bar span { display: block; height: 100%; }
  .hour-bar .bar .c1 { background: var(--c1); }
  .hour-bar .bar .c2 { background: var(--c2); }
  .hour-bar .bar .c3 { background: var(--c3); }
  .hour-bar .bar-value { min-width: 86px; text-align: right; font-weight: 700;
                          color: var(--text); white-space: nowrap; }
  .hour-bar .bar-count { min-width: 54px; text-align: right; color: var(--muted);
                          white-space: nowrap; }
  .hour-bar.today .hour-label,
  .hour-bar.today .bar-value { color: var(--text); font-weight: 700; }

  .empty { color: var(--muted); font-style: italic; padding: 12px 0; }
  .note { color: var(--muted); font-size: 12px; margin-top: 12px;
           padding-top: 10px; border-top: 1px solid var(--border); }
  footer { margin-top: 32px; padding-top: 16px; border-top: 1px solid var(--border);
            color: var(--muted); font-size: 12px; text-align: center; }

  @media (max-width: 768px) {
    body { padding: 16px; }
    header { flex-direction: column; align-items: flex-start; gap: 8px; }
    header .meta { text-align: left; }
    .grid, .grid.three { grid-template-columns: 1fr; }
    .kpi-row { flex-wrap: wrap; }
    .kpi-box { min-width: 45%; }
    .hour-bar .hour-label { width: 76px; }
    .hour-bar .bar-count { display: none; }
    table { font-size: 12px; }
    td, th { padding: 6px 6px; }
  }"""


CSS_WEEKLY = """  /* ---- specifique weekly ---- */
  .alert {
    background: #fff8e1; border: 1px solid #f0dfae; border-left: 4px solid var(--gold);
    border-radius: 8px; padding: 14px 18px; margin-bottom: 20px; font-size: 13px;
  }
  .alert strong { color: #8a6400; }
  .alert ul { margin: 8px 0 0 18px; }
  .alert li { margin-bottom: 4px; }

  .kpi-box.wide .value { font-size: 19px; }
  .kpi-box.flat { background: #f4f3ef; }
  .kpi-box.flat .value { color: var(--text); }

  .hl { display: flex; gap: 18px; flex-wrap: wrap; }
  .hl > div { flex: 1; min-width: 220px; }

  .lead {
    font-size: 13px; color: var(--text); background: var(--accent-light);
    border-radius: 8px; padding: 12px 16px; margin-bottom: 16px;
  }
  .lead b { color: var(--accent); }

  ul.bullets { margin: 0; padding-left: 18px; font-size: 13px; }
  ul.bullets li { margin-bottom: 7px; }
  ul.bullets li:last-child { margin-bottom: 0; }

  .pill { display: inline-block; padding: 1px 8px; border-radius: 10px;
          font-size: 11px; font-weight: 600; background: var(--neutral-bg);
          color: var(--neutral); white-space: nowrap; }
  .pill.new { background: var(--up-bg); color: var(--up); }
  .pill.back { background: #e3f0fa; color: #1c5c92; }
  .pill.risk { background: var(--down-bg); color: var(--down); }
"""
