"""
b2b_render.py — Briques de rendu partagees des dashboards B2B Teatower.

Formatage (euros, echappement, troncature), badges d'evolution, medaillons,
kpi-box, cartes, titres de section et generateur de tableau. Utilise par
`build_b2b_dashboard.py` (daily) et `build_b2b_weekly.py` (weekly) pour que les
deux pages parlent exactement le meme langage visuel.

La feuille de style correspondante vit dans `b2b_style.py`.
"""
import html
import re

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
