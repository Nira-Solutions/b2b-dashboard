"""
b2b_dashboard_extract.py — Extraction Odoo pour le B2B Morning Dashboard Teatower.

Produit `reports/b2b_dashboard_data.json` : la photo B2B de la journee ecoulee
(factures postees), segmentee par canal, avec top clients / top produits, le
stock de drafts, le pipeline devis et la tendance sur les 5 derniers memes
jours de semaine.

Segmentation canal — par tag res.partner.category (meme convention que
compta/commission_jerome_*.py) :
  GMS        -> tags 88, 27
  Horeca     -> tags 84, 26
  Revendeurs -> tag  85
Un partenaire sans aucun de ces tags n'est PAS compte comme B2B (c'est du B2C
Shopify / POS), ce qui evite le piege team_id absent avant nov-2025.
Priorite si multi-tag : GMS > Horeca > Revendeurs.

Montants : `amount_untaxed` (HT), avoirs (out_refund) comptes en negatif.

Usage :
  python reports/b2b_dashboard_extract.py                # jour = hier
  python reports/b2b_dashboard_extract.py --date 2026-08-06
  python reports/b2b_dashboard_extract.py --out chemin/data.json

Credentials : ODOO_PWD dans l'environnement (repo public, jamais en clair).
"""
import argparse
import json
import os
import sys
import xmlrpc.client
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

URL = "https://tea-tree.odoo.com"
DB = "tsc-be-tea-tree-main-18515272"
USER = "nicolas.raes@teatower.com"

CHANNELS = [
    ("GMS", [88, 27]),
    ("Horeca", [84, 26]),
    ("Revendeurs", [85]),
]
CHANNEL_ORDER = [c[0] for c in CHANNELS]

TOP_N_CLIENTS = 8
TOP_N_PRODUITS = 10
TREND_POINTS = 5  # nb de memes-jours-de-semaine precedents

MOIS_FR = ["janvier", "fevrier", "mars", "avril", "mai", "juin",
           "juillet", "aout", "septembre", "octobre", "novembre", "decembre"]
JOURS_FR = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def connect():
    pwd = os.environ.get("ODOO_PWD")
    if not pwd:
        raise SystemExit(
            "Definir la variable d'environnement ODOO_PWD avant d'executer ce script "
            "(creds dans 'Materiel TT.xlsx')."
        )
    common = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/common")
    uid = common.authenticate(DB, USER, pwd, {})
    if not uid:
        raise SystemExit("Authentification Odoo refusee — verifier ODOO_PWD.")
    models = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/object")

    def call(model, method, args, kw=None):
        return models.execute_kw(DB, uid, pwd, model, method, args, kw or {})

    return call


def channel_of(cats):
    """Renvoie le canal B2B d'un partenaire d'apres ses tags, ou None si B2C."""
    for name, tag_ids in CHANNELS:
        if any(c in tag_ids for c in cats):
            return name
    return None


def fetch_invoices(call, date_from, date_to):
    """Factures/avoirs clients postes sur [date_from, date_to] (dates incluses)."""
    domain = [
        ("move_type", "in", ["out_invoice", "out_refund"]),
        ("state", "=", "posted"),
        ("invoice_date", ">=", date_from.isoformat()),
        ("invoice_date", "<=", date_to.isoformat()),
    ]
    return call("account.move", "search_read", [domain], {
        "fields": ["id", "name", "move_type", "invoice_date", "partner_id",
                   "amount_untaxed", "amount_total", "invoice_origin"],
    })


def partner_channels(call, partner_ids):
    """{partner_id: (canal|None, nom)} — remonte au parent si l'enfant n'est pas tague."""
    if not partner_ids:
        return {}
    partners = call("res.partner", "read", [list(partner_ids)],
                    {"fields": ["id", "name", "category_id", "parent_id",
                                "commercial_partner_id"]})
    by_id = {p["id"]: p for p in partners}

    # Les adresses de facturation enfants portent rarement les tags : on lit
    # aussi le partenaire commercial (l'entite societe) pour les rattraper.
    extra_ids = set()
    for p in partners:
        cp = p.get("commercial_partner_id")
        if cp and cp[0] not in by_id:
            extra_ids.add(cp[0])
    if extra_ids:
        for p in call("res.partner", "read", [sorted(extra_ids)],
                      {"fields": ["id", "name", "category_id"]}):
            by_id[p["id"]] = p

    out = {}
    for pid in partner_ids:
        p = by_id.get(pid)
        if not p:
            out[pid] = (None, f"#{pid}", pid)
            continue
        ch = channel_of(p.get("category_id") or [])
        cp = p.get("commercial_partner_id")
        cp_id = cp[0] if cp else pid
        if ch is None and cp and cp[0] in by_id:
            ch = channel_of(by_id[cp[0]].get("category_id") or [])
        # Nom regroupe au niveau societe pour ne pas eclater les tops par adresse
        label = by_id[cp_id]["name"] if cp_id in by_id else p["name"]
        out[pid] = (ch, label, cp_id)
    return out


def b2b_lines(invoices, pmap):
    """Filtre les factures B2B et annote canal + libelle client."""
    rows = []
    for inv in invoices:
        if not inv.get("partner_id"):
            continue
        pid = inv["partner_id"][0]
        ch, label, cp_id = pmap.get(pid, (None, inv["partner_id"][1], pid))
        if ch is None:
            continue
        sign = -1 if inv["move_type"] == "out_refund" else 1
        rows.append({
            "id": inv["id"],
            "name": inv["name"],
            "date": inv["invoice_date"],
            "channel": ch,
            "partner_id": cp_id,
            "partner": label,
            "untaxed": round(inv["amount_untaxed"] * sign, 2),
            "total": round(inv["amount_total"] * sign, 2),
            "origin": inv.get("invoice_origin") or "",
            "is_refund": inv["move_type"] == "out_refund",
        })
    return rows


def top_products(call, invoice_ids):
    if not invoice_ids:
        return []
    lines = call("account.move.line", "search_read", [[
        ("move_id", "in", invoice_ids),
        ("display_type", "=", "product"),
        ("product_id", "!=", False),
    ]], {"fields": ["product_id", "quantity", "price_subtotal", "move_id"]})
    agg = defaultdict(lambda: {"qty": 0.0, "ca": 0.0, "code": "", "name": ""})
    refunds = set()
    if lines:
        moves = call("account.move", "read", [sorted({l["move_id"][0] for l in lines})],
                     {"fields": ["id", "move_type"]})
        refunds = {m["id"] for m in moves if m["move_type"] == "out_refund"}
    for l in lines:
        sign = -1 if l["move_id"][0] in refunds else 1
        pid, pname = l["product_id"]
        a = agg[pid]
        a["qty"] += l["quantity"] * sign
        a["ca"] += l["price_subtotal"] * sign
        a["name"] = pname
    out = [{"product_id": k, "label": v["name"],
            "qty": round(v["qty"], 2), "ca": round(v["ca"], 2)}
           for k, v in agg.items()]
    out.sort(key=lambda x: -x["ca"])
    return out[:TOP_N_PRODUITS]


def fetch_drafts(call, pmap_cache, call_partners):
    drafts = call("account.move", "search_read", [[
        ("move_type", "in", ["out_invoice", "out_refund"]),
        ("state", "=", "draft"),
    ]], {"fields": ["id", "name", "partner_id", "amount_untaxed", "invoice_date",
                    "create_date"]})
    pids = {d["partner_id"][0] for d in drafts if d.get("partner_id")}
    pm = call_partners(pids)
    rows = []
    for d in drafts:
        if not d.get("partner_id"):
            continue
        ch, label, _ = pm.get(d["partner_id"][0], (None, "", 0))
        if ch is None:
            continue
        label_name = d.get("name") or ""
        if label_name in ("", "/", "False"):
            label_name = "(brouillon)"
        rows.append({"name": label_name,
                     "partner": label, "channel": ch,
                     "untaxed": round(d["amount_untaxed"], 2),
                     "date": d.get("invoice_date") or (d.get("create_date") or "")[:10]})
    rows.sort(key=lambda r: -r["untaxed"])
    return rows


def fetch_pipeline(call, call_partners):
    """Devis non confirmes (draft/sent) — le pipeline B2B a relancer."""
    quotes = call("sale.order", "search_read", [[
        ("state", "in", ["draft", "sent"]),
    ]], {"fields": ["id", "name", "partner_id", "amount_untaxed", "date_order",
                    "state", "user_id"]})
    pids = {q["partner_id"][0] for q in quotes if q.get("partner_id")}
    pm = call_partners(pids)
    rows = []
    for q in quotes:
        if not q.get("partner_id"):
            continue
        ch, label, _ = pm.get(q["partner_id"][0], (None, "", 0))
        if ch is None:
            continue
        d = (q.get("date_order") or "")[:10]
        age = None
        if d:
            try:
                age = (date.today() - date.fromisoformat(d)).days
            except ValueError:
                age = None
        rows.append({"name": q["name"], "partner": label, "channel": ch,
                     "untaxed": round(q["amount_untaxed"], 2), "date": d,
                     "state": q["state"], "age_days": age,
                     "user": (q.get("user_id") or [None, ""])[1]})
    rows.sort(key=lambda r: -r["untaxed"])
    return rows


def fr_date(d):
    return f"{d.day:02d}/{d.month:02d}/{d.year}"


def fr_long(d):
    return f"{JOURS_FR[d.weekday()]} {d.day} {MOIS_FR[d.month - 1]} {d.year}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="Jour analyse (YYYY-MM-DD). Defaut : hier.")
    ap.add_argument("--out", default=None, help="Chemin du JSON de sortie.")
    args = ap.parse_args()

    target = date.fromisoformat(args.date) if args.date else date.today() - timedelta(days=1)
    out_path = Path(args.out) if args.out else Path(__file__).with_name("b2b_dashboard_data.json")

    call = connect()
    partner_cache = {}

    def call_partners(pids):
        missing = [p for p in pids if p not in partner_cache]
        if missing:
            partner_cache.update(partner_channels(call, missing))
        return {p: partner_cache[p] for p in pids if p in partner_cache}

    # --- Jour cible ---
    inv_day = fetch_invoices(call, target, target)
    pm = call_partners({i["partner_id"][0] for i in inv_day if i.get("partner_id")})
    rows = b2b_lines(inv_day, pm)

    by_channel = {c: {"ca": 0.0, "n": 0} for c in CHANNEL_ORDER}
    by_client = defaultdict(lambda: {"ca": 0.0, "n": 0, "channel": ""})
    for r in rows:
        by_channel[r["channel"]]["ca"] += r["untaxed"]
        by_channel[r["channel"]]["n"] += 1
        c = by_client[r["partner"]]
        c["ca"] += r["untaxed"]
        c["n"] += 1
        c["channel"] = r["channel"]
    for v in by_channel.values():
        v["ca"] = round(v["ca"], 2)

    total_day = round(sum(v["ca"] for v in by_channel.values()), 2)

    clients = [{"partner": k, "ca": round(v["ca"], 2), "n": v["n"], "channel": v["channel"]}
               for k, v in by_client.items()]
    clients.sort(key=lambda x: -x["ca"])

    produits = top_products(call, [r["id"] for r in rows])

    # --- Tendance : memes jours de semaine precedents ---
    trend = []
    for k in range(TREND_POINTS, 0, -1):
        d = target - timedelta(days=7 * k)
        inv = fetch_invoices(call, d, d)
        pmk = call_partners({i["partner_id"][0] for i in inv if i.get("partner_id")})
        rk = b2b_lines(inv, pmk)
        ch = {c: 0.0 for c in CHANNEL_ORDER}
        for r in rk:
            ch[r["channel"]] += r["untaxed"]
        trend.append({"date": d.isoformat(), "label": fr_date(d),
                      "ca": round(sum(ch.values()), 2),
                      "by_channel": {k2: round(v, 2) for k2, v in ch.items()},
                      "n": len(rk)})
    trend.append({"date": target.isoformat(), "label": fr_date(target),
                  "ca": total_day,
                  "by_channel": {k: v["ca"] for k, v in by_channel.items()},
                  "n": len(rows), "is_today": True})

    hist = [t["ca"] for t in trend[:-1]]
    moyenne = round(sum(hist) / len(hist), 2) if hist else 0.0
    delta_pct = round((total_day - moyenne) / moyenne * 100, 1) if moyenne else None

    # --- Mois en cours (MTD) ---
    mtd_start = target.replace(day=1)
    inv_mtd = fetch_invoices(call, mtd_start, target)
    pm_mtd = call_partners({i["partner_id"][0] for i in inv_mtd if i.get("partner_id")})
    rows_mtd = b2b_lines(inv_mtd, pm_mtd)
    mtd = {c: 0.0 for c in CHANNEL_ORDER}
    for r in rows_mtd:
        mtd[r["channel"]] += r["untaxed"]
    mtd = {k: round(v, 2) for k, v in mtd.items()}

    # --- Drafts + pipeline ---
    drafts = fetch_drafts(call, partner_cache, call_partners)
    pipeline = fetch_pipeline(call, call_partners)

    data = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "target_date": target.isoformat(),
        "target_label": fr_long(target),
        "target_short": fr_date(target),
        "channels": CHANNEL_ORDER,
        "jour": {
            "total_ht": total_day,
            "nb_factures": len(rows),
            "by_channel": by_channel,
            "factures": sorted(rows, key=lambda r: -r["untaxed"]),
        },
        "top_clients": clients[:TOP_N_CLIENTS],
        "top_produits": produits,
        "tendance": {
            "points": trend,
            "moyenne_5": moyenne,
            "delta_pct": delta_pct,
        },
        "mtd": {
            "depuis": mtd_start.isoformat(),
            "total_ht": round(sum(mtd.values()), 2),
            "by_channel": mtd,
            "nb_factures": len(rows_mtd),
        },
        "drafts": {
            "nb": len(drafts),
            "total_ht": round(sum(d["untaxed"] for d in drafts), 2),
            "items": drafts[:15],
        },
        "pipeline": {
            "nb": len(pipeline),
            "total_ht": round(sum(p["untaxed"] for p in pipeline), 2),
            "items": pipeline[:15],
        },
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK  {out_path}")
    print(f"    {data['target_label']} — {total_day:,.2f} EUR HT / {len(rows)} factures B2B"
          .replace(",", " "))
    for c in CHANNEL_ORDER:
        v = by_channel[c]
        print(f"    {c:<12} {v['ca']:>10,.2f} EUR  ({v['n']} fact.)".replace(",", " "))
    print(f"    MTD depuis {mtd_start.isoformat()} : {data['mtd']['total_ht']:,.2f} EUR HT"
          .replace(",", " "))
    print(f"    Drafts {data['drafts']['nb']} / Pipeline devis {data['pipeline']['nb']}")


if __name__ == "__main__":
    sys.exit(main())
